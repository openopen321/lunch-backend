import os
import json
import re
import uuid
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# 設定 AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- 關鍵功能：自動尋找可用模型 ---
def get_best_available_model():
    """
    不猜測模型名稱，直接詢問 API 有哪些模型可用，
    並優先選擇含有 'flash' 或 'pro' 的生成模型。
    """
    try:
        print("正在查詢可用模型清單...")
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        print(f"找到的模型: {available_models}")

        # 策略 1: 優先找 Flash (速度快)
        for name in available_models:
            if 'flash' in name.lower() and 'legacy' not in name.lower():
                return name
        
        # 策略 2: 其次找 Pro (性能強)
        for name in available_models:
            if 'pro' in name.lower() and 'legacy' not in name.lower():
                return name
                
        # 策略 3: 隨便回傳第一個能用的
        if available_models:
            return available_models[0]
            
    except Exception as e:
        print(f"查詢模型失敗: {e}")
    
    # 如果連查詢都失敗，只好回傳一個最通用的預設值
    return "models/gemini-1.5-flash"

fake_db = {} 

@app.route("/")
def home():
    return "Auto-Discovery AI Lunch API is Running!"

@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    data = request.json
    url = data.get('url')
    print(f"收到網址: {url}")

    try:
        if not GEMINI_API_KEY:
            raise Exception("Render 環境變數中找不到 GEMINI_API_KEY")

        # 動態取得最佳模型
        model_name = get_best_available_model()
        print(f"決定使用的模型: {model_name}")

        try:
            # 嘗試啟用搜尋工具
            tools = {'google_search': {}}
            model = genai.GenerativeModel(model_name, tools=tools)
        except:
            print("搜尋工具不可用，降級為普通模式")
            model = genai.GenerativeModel(model_name)

        prompt = f"""
        你是一個專業的台灣團購小幫手。請調查這個 Google Maps 餐廳連結：{url}
        
        【任務】
        1. 找出「正確店名」。
        2. 找出最新的「菜單」與「價格」(台幣)。
        3. 請忽略營業時間（即使休息中也要找出菜單）。

        【輸出 JSON 格式】
        {{
            "name": "店名",
            "address": "地址",
            "phone": "電話",
            "minDelivery": 0,
            "menu": [
                {{ "id": 1, "name": "餐點名稱", "price": 100 }}
            ]
        }}
        """
        
        # 執行 AI
        try:
            response = model.generate_content(prompt)
        except Exception as api_error:
            # 如果這裡還錯，代表 API Key 可能有問題 (例如沒有權限存取該模型)
            raise Exception(f"模型 {model_name} 執行失敗: {api_error}")

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
                "name": f"讀取失敗 ({model_name})",
                "address": "請手動輸入",
                "phone": "",
                "minDelivery": 0,
                "menu": [{"id": 1, "name": "請手動輸入餐點", "price": 0}]
            }

        # 補 ID
        for idx, item in enumerate(ai_data.get('menu', [])):
            item['id'] = idx + 1
            
        return jsonify(ai_data)

    except Exception as e:
        error_str = str(e)
        print(f"❌ 發生錯誤: {error_str}")
        
        return jsonify({
            "name": f"錯誤: {error_str}",
            "address": "請檢查後端 Logs", 
            "phone": "",
            "minDelivery": 0,
            "menu": [{"id": 1, "name": "無法載入", "price": 0}]
        })

# --- 其他 API ---
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