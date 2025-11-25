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

# 設定 AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# 取得版本號
try:
    import importlib.metadata
    LIB_VERSION = importlib.metadata.version("google-generativeai")
except:
    LIB_VERSION = "未知"

fake_db = {} 

@app.route("/")
def home():
    return f"Auto-Detect Vision API Running! Lib: {LIB_VERSION}"

def get_usable_models():
    """
    直接詢問 Google 帳號目前可用的模型列表
    """
    models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # 移除 'models/' 前綴，只留名稱
                name = m.name.replace("models/", "")
                models.append(name)
    except Exception as e:
        print(f"無法列出模型: {e}")
    return models

@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    try:
        data = request.json
        image_data = data.get('image')
        mime_type = data.get('mime_type', 'image/jpeg')
        
        print("收到圖片分析請求...")

        if not GEMINI_API_KEY:
            raise Exception("Render 環境變數中找不到 GEMINI_API_KEY")

        if not image_data:
            raise Exception("未收到圖片資料")

        image_part = {"mime_type": mime_type, "data": image_data}
        
        prompt = """
        你是一個專業的菜單辨識助手。請分析這張圖片。
        
        【任務】
        1. 找出圖片中的「餐廳名稱」(如果沒寫，請根據菜色推測一個合理的店名)。
        2. 辨識所有的「菜色名稱」與「價格」(數字)。
        3. 請忽略無關的文字。

        【輸出 JSON 格式】
        {
            "name": "店名",
            "address": "地址(若有)",
            "phone": "電話(若有)",
            "minDelivery": 0,
            "menu": [
                { "id": 1, "name": "菜名", "price": 100 }
            ]
        }
        """

        # --- 步驟 1: 獲取所有可用模型 ---
        available_models = get_usable_models()
        print(f"帳號可用模型: {available_models}")

        # --- 步驟 2: 排序策略 ---
        # 我們優先嘗試名字裡有 'flash' (快) 或 'vision' (視覺) 的模型
        # 如果都沒有，就嘗試 'pro'
        def sort_priority(name):
            score = 0
            if 'flash' in name: score += 3
            if 'vision' in name: score += 2
            if 'pro' in name: score += 1
            if 'legacy' in name: score -= 5 # 舊版最後試
            return score

        # 將模型依優先順序排列
        candidate_models = sorted(available_models, key=sort_priority, reverse=True)
        
        # 如果列表是空的 (API Key 權限問題)，手動加入幾個常見的試試看
        if not candidate_models:
            candidate_models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro-vision"]

        response = None
        used_model = ""
        errors = []

        # --- 步驟 3: 逐一嘗試 ---
        for model_name in candidate_models:
            try:
                print(f"正在嘗試模型: {model_name}")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content([prompt, image_part])
                used_model = model_name
                print(f"🎉 成功使用 {model_name}！")
                break # 成功就跳出
            except Exception as e:
                print(f"{model_name} 失敗: {e}")
                errors.append(f"{model_name}: {str(e)[:20]}...")
                continue

        if not response:
            error_summary = "; ".join(errors)
            raise Exception(f"所有模型都失敗。可用模型: {available_models}。錯誤: {error_summary}")
        
        # 解析結果
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        try:
            match = re.search(r'\{.*\}', clean_json, re.DOTALL)
            if match:
                ai_data = json.loads(match.group())
            else:
                ai_data = json.loads(clean_json)
        except:
            ai_data = {
                "name": f"辨識失敗 ({used_model})",
                "address": "",
                "phone": "",
                "minDelivery": 0,
                "menu": [{"id": 1, "name": "無法辨識文字，請手動輸入", "price": 0}]
            }

        # 補 ID
        for idx, item in enumerate(ai_data.get('menu', [])):
            item['id'] = idx + 1
            
        return jsonify(ai_data)

    except Exception as e:
        error_str = str(e)
        print(f"❌ 發生錯誤: {error_str}")
        return jsonify({
            "name": f"錯誤: {error_str[:100]}...", 
            "address": f"Lib: {LIB_VERSION}",
            "phone": "",
            "minDelivery": 0,
            "menu": [{"id": 1, "name": "系統發生錯誤", "price": 0}]
        })

# --- 其他 API (保持不變) ---
@app.route("/api/create_group", methods=['POST'])
def create_group():
    data = request.json
    group_id = str(uuid.uuid4())[:8]
    fake_db[group_id] = {"id": group_id, "restaurant": data['restaurant'], "orders": [], "status": "OPEN"}
    return jsonify({"group_id": group_id})

@app.route("/api/group/<group_id>", methods=['GET'])
def get_group(group_id):
    return jsonify(fake_db.get(group_id) or {})

@app.route("/api/group/<group_id>/order", methods=['POST'])
def submit_order(group_id):
    if group_id in fake_db:
        fake_db[group_id]['orders'].append(request.json)
        return jsonify({"success": True})
    return jsonify({"error": "Not found"}), 404

@app.route("/api/group/<group_id>/status", methods=['POST'])
def update_status(group_id):
    if group_id in fake_db:
        fake_db[group_id]['status'] = request.json.get('status')
        return jsonify({"success": True})
    return jsonify({"error": "Not found"}), 404

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))