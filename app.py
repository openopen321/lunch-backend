import os
import json
import uuid
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
# 設定最大上傳限制為 16MB
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
CORS(app)

# --- 資料持久化設定 (防止資料遺失) ---
DB_FILE = 'database.json'        # 存團購訂單
RESTAURANT_FILE = 'restaurants.json' # 存餐廳菜單

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_json(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"存檔失敗 {filename}: {e}")

# 初始化資料庫
fake_db = load_json(DB_FILE)
restaurants_db = load_json(RESTAURANT_FILE)

# --- Gemini AI 設定 ---
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

@app.route("/")
def home():
    try:
        import importlib.metadata
        ver = importlib.metadata.version("google-generativeai")
    except:
        ver = "未知"
    return f"Bento System API Running! (GenAI Ver: {ver})"

# --- 1. AI 辨識 API ---
@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    try:
        data = request.json
        image_data = data.get('image')
        mime_type = data.get('mime_type', 'image/jpeg')
        
        print("收到圖片分析請求...")

        if not GEMINI_API_KEY:
            raise Exception("環境變數中找不到 GEMINI_API_KEY")
        if not image_data:
            raise Exception("未收到圖片資料")

        image_part = {"mime_type": mime_type, "data": image_data}

        # Prompt：要求擷取 description
        prompt = """
        你是一個專業的菜單辨識助手。請分析這張菜單圖片。
        
        【任務】
        1. 找出「餐廳名稱」。若無明確店名，請根據菜色創造一個好聽的店名。
        2. 辨識所有「菜色名稱」、「價格」(數字) 以及「副標題/描述」。
           - 副標題範例：(含蛋)、(豬肉產地：台灣)、(招牌推薦)、(大/中/小)
           - 如果該菜色沒有副標題，則該欄位留空字串。
        3. 請忽略無關的文字。
        
        【輸出 JSON 格式】
        {
            "name": "店名",
            "phone": "電話",
            "menu": [
                { "name": "菜名", "price": 100, "description": "副標題或描述" }
            ]
        }
        """

        # 動態抓取並排序模型 (版本號新 -> 舊)
        def get_sorted_models():
            try:
                found_models = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        name = m.name.replace('models/', '')
                        if 'gemini' in name.lower():
                            found_models.append(name)
                # 使用正則表達式抓取版本號進行排序
                found_models.sort(key=lambda x: float(re.search(r'(\d+(?:\.\d+)+)', x).group(1)) if re.search(r'(\d+(?:\.\d+)+)', x) else 0, reverse=True)
                return found_models
            except: return []

        candidate_models = get_sorted_models()
        # 保底清單
        if not candidate_models: candidate_models = ["gemini-1.5-flash", "gemini-1.5-pro"]
            
        response = None
        used_model = ""
        last_error = ""

        for model_name in candidate_models:
            try:
                print(f"嘗試使用模型: {model_name}")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content([prompt, image_part])
                used_model = model_name
                print(f"✅ 成功使用 {model_name}")
                break 
            except Exception as e:
                last_error = str(e)
                continue

        if not response:
            raise Exception(f"AI 模型嘗試皆失敗: {last_error}")
        
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        try:
            match = re.search(r'\{.*\}', clean_json, re.DOTALL)
            ai_data = json.loads(match.group() if match else clean_json)
        except:
            ai_data = {"name": f"辨識失敗 ({used_model})", "menu": [{"name": "無法辨識", "price": 0}]}

        # 資料整理
        final_menu = []
        for idx, item in enumerate(ai_data.get('menu', [])):
            final_menu.append({
                "id": idx + 1,
                "name": str(item.get('name', '未命名')),
                "price": int(item.get('price', 0)),
                "description": str(item.get('description', ''))
            })
            
        return jsonify({
            "name": ai_data.get('name', '未命名餐廳'),
            "phone": ai_data.get('phone', ''),
            "menu": final_menu
        })

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return jsonify({"name": "系統錯誤", "menu": [{"id":1, "name": str(e), "price": 0}]})

# --- 2. 餐廳資料庫 API ---
@app.route("/api/restaurants", methods=['GET'])
def get_restaurants():
    r_list = sorted(list(restaurants_db.values()), key=lambda x: x['name'])
    return jsonify(r_list)

# --- 3. 團購功能 API ---
@app.route("/api/create_group", methods=['POST'])
def create_group():
    data = request.json
    restaurant_data = data['restaurant']
    restaurant_name = restaurant_data.get('name', '未命名餐廳')

    # 儲存餐廳資料
    restaurants_db[restaurant_name] = restaurant_data
    save_json(RESTAURANT_FILE, restaurants_db)

    group_id = str(uuid.uuid4())[:8]
    fake_db[group_id] = {
        "id": group_id, 
        "restaurant": restaurant_data, 
        "orders": [], 
        "status": "OPEN",
        "created_at": str(uuid.uuid1())
    }
    save_json(DB_FILE, fake_db)
    return jsonify({"group_id": group_id})

@app.route("/api/group/<group_id>", methods=['GET'])
def get_group(group_id):
    group = fake_db.get(group_id)
    if group:
        return jsonify(group)
    # 重要：回傳 404 讓前端知道資料遺失
    return jsonify({"error": "Group not found"}), 404

@app.route("/api/group/<group_id>/order", methods=['POST'])
def submit_order(group_id):
    if group_id in fake_db:
        if fake_db[group_id]['status'] == 'CLOSED':
             return jsonify({"error": "Already closed"}), 400
        
        order_data = request.json
        order_data['id'] = order_data.get('id') or int(uuid.uuid4().int >> 64)
        fake_db[group_id]['orders'].append(order_data)
        save_json(DB_FILE, fake_db)
        return jsonify({"success": True})
    return jsonify({"error": "Not found"}), 404

@app.route("/api/group/<group_id>/order/<order_id>", methods=['DELETE'])
def delete_order(group_id, order_id):
    if group_id in fake_db:
        orders = fake_db[group_id]['orders']
        new_orders = [o for o in orders if str(o['id']) != str(order_id)]
        
        if len(orders) == len(new_orders):
             return jsonify({"error": "Order not found"}), 404
             
        fake_db[group_id]['orders'] = new_orders
        save_json(DB_FILE, fake_db)
        return jsonify({"success": True})
    return jsonify({"error": "Group not found"}), 404

@app.route("/api/group/<group_id>/status", methods=['POST'])
def update_status(group_id):
    if group_id in fake_db:
        fake_db[group_id]['status'] = request.json.get('status')
        save_json(DB_FILE, fake_db)
        return jsonify({"success": True})
    return jsonify({"error": "Not found"}), 404

@app.route("/api/group/<group_id>/update_payment", methods=['POST'])
def update_payment(group_id):
    if group_id not in fake_db: return jsonify({"error": "Group not found"}), 404
    data = request.json
    order_id, amount = data.get('orderId'), data.get('amount')
    updated = False
    for order in fake_db[group_id]['orders']:
        if str(order['id']) == str(order_id):
            order['paidAmount'] = int(amount) if amount and str(amount).isdigit() else 0
            updated = True; break
    if updated:
        save_json(DB_FILE, fake_db)
        return jsonify({"success": True})
    return jsonify({"error": "Order not found"}), 404

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))