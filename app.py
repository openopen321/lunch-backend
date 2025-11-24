import os
import json
import uuid
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# 設定 AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# 記憶體資料庫
fake_db = {} 

@app.route("/")
def home():
    return "Simple AI Lunch API is Running!"

# 核心功能：AI 分析
@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    data = request.json
    url = data.get('url')
    print(f"收到網址: {url}")

    try:
        if not GEMINI_API_KEY:
            raise Exception("No API Key")

        # 啟用 Google 搜尋工具
        tools = {'google_search': {}}
        model = genai.GenerativeModel('gemini-1.5-flash', tools=tools)
        
        # 直接請 AI 搜尋這個網址的相關資訊
        prompt = f"""
        請幫我調查這個 Google Maps 連結：{url}

        【任務】
        1. 利用 Google 搜尋找出這家餐廳的「正確店名」。
        2. 搜尋這家店的「最新菜單」和「價格」。
        3. 如果連結失效或找不到，請隨機推薦一家台灣熱門午餐餐廳的資料給我。

        【輸出 JSON 格式】
        {{
            "name": "店名",
            "address": "地址",
            "phone": "電話",
            "minDelivery": 0,
            "menu": [
                {{"id": 1, "name": "招牌便當", "price": 100}},
                {{"id": 2, "name": "雞腿飯", "price": 110}}
            ]
        }}
        """
        
        response = model.generate_content(prompt)
        
        # 清理並解析 JSON
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        # 有時候 AI 會回傳多餘文字，嘗試抓取大括號內的內容
        match = re.search(r'\{.*\}', clean_json, re.DOTALL)
        if match:
            ai_data = json.loads(match.group())
        else:
            ai_data = json.loads(clean_json)

        # 補 ID
        for idx, item in enumerate(ai_data.get('menu', [])):
            item['id'] = idx + 1
            
        return jsonify(ai_data)

    except Exception as e:
        print(f"AI 失敗: {e}")
        # 失敗時的回傳
        return jsonify({
            "name": "無法讀取 (請檢查 Render Logs)",
            "address": "請手動輸入",
            "phone": "",
            "minDelivery": 0,
            "menu": [{"id": 1, "name": "手動輸入餐點", "price": 0}]
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