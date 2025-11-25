import os
import json
import uuid
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
CORS(app)

# --- 資料持久化設定 ---
DB_FILE = 'database.json'

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_db(data):
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"存檔失敗: {e}")

# 初始化資料庫
fake_db = load_db()

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

        # 準備圖片
        image_part = {
            "mime_type": mime_type,
            "data": image_data
        }

        # 定義 Prompt
        prompt = """
        你是一個專業的菜單辨識助手。請分析這張菜單圖片。
        
        【任務】
        1. 找出圖片中的「餐廳名稱」。如果沒有明確店名，請根據菜色創造一個好聽的店名（例如：阿嬤古早味、巷口麵攤）。
        2. 辨識所有的「菜色名稱」與「價格」(數字)。
        3. 請忽略無關的文字。
        
        【重要】直接輸出純 JSON 格式，不要 markdown 標記。格式如下：
        {
            "name": "店名",
            "phone": "電話",
            "menu": [
                { "name": "菜名", "price": 100 }
            ]
        }
        """

        # --- 優化：動態抓取並排序可用模型 ---
        # 目的：不寫死模型名稱，自動抓取最新版本 (符合 2025 年後只支援新版的需求)
        def get_sorted_models():
            try:
                found_models = []
                # 列出所有可用模型
                for m in genai.list_models():
                    # 必須支援內容生成 (generateContent) 且是 gemini 系列
                    if 'generateContent' in m.supported_generation_methods:
                        name = m.name.replace('models/', '') # 去掉前綴，只留名稱
                        if 'gemini' in name.lower():
                            found_models.append(name)
                
                # 排序邏輯：優先使用版本號高的 (例如 2.5 > 2.0 > 1.5)
                def model_sort_key(name):
                    version = 0.0
                    # 使用正則表達式抓取版本號 (如 1.5, 2.0)
                    match = re.search(r'(\d+(?:\.\d+)+)', name)
                    if match:
                        version = float(match.group(1))
                    return version

                # 降冪排序 (版本號大者在前)
                found_models.sort(key=model_sort_key, reverse=True)
                return found_models
            except Exception as ex:
                print(f"⚠️ 無法動態取得模型列表: {ex}")
                return []

        # 執行抓取
        candidate_models = get_sorted_models()
        
        # 如果 API 抓不到任何模型 (可能是 Key 權限問題)，則使用保底清單
        if not candidate_models:
            print("⚠️ 使用預設保底模型清單")
            candidate_models = ["gemini-1.5-flash", "gemini-1.5-pro"]
            
        print(f"🤖 系統將依序嘗試以下模型: {candidate_models}")

        response = None
        used_model = ""
        last_error = ""

        for model_name in candidate_models:
            try:
                print(f"嘗試使用模型: {model_name}")
                model = genai.GenerativeModel(model_name)
                # 這裡不使用 stream，直接 generate_content
                response = model.generate_content([prompt, image_part])
                used_model = model_name
                print(f"✅ 成功使用 {model_name}！")
                break 
            except Exception as e:
                print(f"❌ {model_name} 失敗: {e}")
                last_error = str(e)
                # 繼續嘗試下一個模型
                continue

        if not response:
            raise Exception(f"所有 AI 模型嘗試皆失敗。最後錯誤: {last_error}")
        
        # 解析結果
        text = response.text
        # 清理可能存在的 Markdown code block
        clean_json = text.replace('```json', '').replace('```', '').strip()
        
        try:
            # 嘗試用正則表達式抓取 JSON 區塊，避免 AI 廢話
            match = re.search(r'\{.*\}', clean_json, re.DOTALL)
            if match:
                ai_data = json.loads(match.group())
            else:
                ai_data = json.loads(clean_json)
        except json.JSONDecodeError:
            print(f"JSON 解析失敗，原始回傳: {text}")
            # 發生錯誤時的回退資料
            ai_data = {
                "name": f"辨識資料格式錯誤 ({used_model})",
                "phone": "",
                "menu": [{"name": "無法自動辨識，請手動輸入", "price": 0}]
            }

        # 補上 ID 並確保資料結構正確
        final_menu = []
        for idx, item in enumerate(ai_data.get('menu', [])):
            final_menu.append({
                "id": idx + 1,
                "name": str(item.get('name', '未命名')),
                "price": int(item.get('price', 0))
            })
            
        result = {
            "name": ai_data.get('name', '未命名餐廳'),
            "phone": ai_data.get('phone', ''),
            "minDelivery": 0,
            "menu": final_menu
        }
            
        return jsonify(result)

    except Exception as e:
        error_str = str(e)
        print(f"❌ 系統錯誤: {error_str}")
        return jsonify({
            "name": "系統發生錯誤",
            "phone": "",
            "menu": [{"id": 1, "name": f"錯誤: {error_str}", "price": 0}]
        })

# --- 群組與訂單 API (含自動存檔) ---

@app.route("/api/create_group", methods=['POST'])
def create_group():
    data = request.json
    group_id = str(uuid.uuid4())[:8]
    fake_db[group_id] = {
        "id": group_id, 
        "restaurant": data['restaurant'], 
        "orders": [], 
        "status": "OPEN",
        "created_at": str(uuid.uuid1()) # 簡單時間戳記
    }
    save_db(fake_db) # 存檔
    return jsonify({"group_id": group_id})

@app.route("/api/group/<group_id>", methods=['GET'])
def get_group(group_id):
    return jsonify(fake_db.get(group_id) or {})

@app.route("/api/group/<group_id>/order", methods=['POST'])
def submit_order(group_id):
    if group_id in fake_db:
        order_data = request.json
        # 確保每個訂單有唯一 ID
        order_data['id'] = order_data.get('id') or int(uuid.uuid4().int >> 64)
        fake_db[group_id]['orders'].append(order_data)
        save_db(fake_db) # 存檔
        return jsonify({"success": True})
    return jsonify({"error": "Not found"}), 404

@app.route("/api/group/<group_id>/status", methods=['POST'])
def update_status(group_id):
    if group_id in fake_db:
        fake_db[group_id]['status'] = request.json.get('status')
        save_db(fake_db) # 存檔
        return jsonify({"success": True})
    return jsonify({"error": "Not found"}), 404

@app.route("/api/group/<group_id>/update_payment", methods=['POST'])
def update_payment(group_id):
    if group_id not in fake_db:
        return jsonify({"error": "Group not found"}), 404
    
    data = request.json
    order_id = data.get('orderId')
    amount = data.get('amount')
    
    updated = False
    for order in fake_db[group_id]['orders']:
        if str(order['id']) == str(order_id):
            order['paidAmount'] = int(amount) if amount and str(amount).isdigit() else 0
            updated = True
            break
    
    if updated:
        save_db(fake_db) # 存檔
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Order not found"}), 404

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))