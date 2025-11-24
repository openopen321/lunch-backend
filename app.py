import os
import json
import re
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# 設定 AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

fake_db = {} 

@app.route("/")
def home():
    return "Gemini 1.5 Pro Backend is Running!"

@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    data = request.json
    url = data.get('url')
    print(f"收到網址: {url}")

    try:
        if not GEMINI_API_KEY:
            raise Exception("Render 環境變數中找不到 GEMINI_API_KEY")

        # 建立模型 (嘗試多種可能)
        model = None
        try:
            # 首選：Gemini 1.5 Pro + 搜尋工具 (更聰明)
            tools = {'google_search': {}}
            model = genai.GenerativeModel('gemini-1.5-pro', tools=tools)
            print("使用模型: Gemini 1.5 Pro (含搜尋)")
        except:
            # 備案：如果 Pro 失敗，嘗試 Flash
            print("Pro 模式失敗，降級為 Flash")
            model = genai.GenerativeModel('gemini-1.5-flash')

        prompt = f"""
        請調查這個餐廳網址：{url}
        這是一個 Google Maps 連結。
        請利用 Google 搜尋找出這家店的「正確店名」以及最新的「菜單」。
        
        【輸出格式 JSON】
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
        
        response = model.generate_content(prompt)
        
        # 清理並解析 JSON
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        try:
            match = re.search(r'\{.*\}', clean_json, re.DOTALL)
            if match:
                ai_data = json.loads(match.group())
            else:
                ai_data = json.loads(clean_json)
        except:
            # 如果 AI 還是沒給 JSON，手動構造一個
            ai_data = {
                "name": "AI 讀取失敗",
                "address": "",
                "phone": "",
                "minDelivery": 0,
                "menu": [{"id": 1, "name": "請手動輸入", "price": 0}]
            }

        # 補 ID
        for idx, item in enumerate(ai_data.get('menu', [])):
            item['id'] = idx + 1
            
        return jsonify(ai_data)

    except Exception as e:
        error_str = str(e)
        print(f"❌ 發生錯誤: {error_str}")
        
        if "404" in error_str and "not found" in error_str:
            error_str = "請確認 requirements.txt 已更新，並且 Render 已重新部署"

        return jsonify({
            "name": f"錯誤: {error_str}",
            "address": "請檢查後端設定",
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