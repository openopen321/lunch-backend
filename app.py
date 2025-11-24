import os
import json
import re
import uuid  # <--- 剛剛就是少了這個！
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# 1. 檢查並設定 AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if GEMINI_API_KEY:
    print(f"API Key 載入成功: {GEMINI_API_KEY[:4]}******")
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("❌ 嚴重錯誤：找不到 GEMINI_API_KEY 環境變數")

fake_db = {} 

@app.route("/")
def home():
    return "Fixed AI Lunch API is Running!"

@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    data = request.json
    url = data.get('url')
    print(f"收到網址: {url}")

    try:
        if not GEMINI_API_KEY:
            raise Exception("Render 環境變數中找不到 GEMINI_API_KEY")

        try:
            tools = {'google_search': {}}
            model = genai.GenerativeModel('gemini-1.5-flash', tools=tools)
        except Exception as model_err:
            print(f"模型建立失敗: {model_err}")
            model = genai.GenerativeModel('gemini-1.5-flash')

        prompt = f"""
        請分析這個餐廳連結：{url}
        找出「店名」與「菜單」。
        如果無法上網搜尋，請根據網址結構猜測店名。
        
        回傳 JSON 格式：
        {{
            "name": "店名",
            "address": "地址",
            "phone": "電話",
            "minDelivery": 0,
            "menu": [{{"id": 1, "name": "範例餐點", "price": 100}}]
        }}
        """
        
        response = model.generate_content(prompt)
        
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        try:
            match = re.search(r'\{.*\}', clean_json, re.DOTALL)
            if match:
                ai_data = json.loads(match.group())
            else:
                ai_data = json.loads(clean_json)
        except:
            raise Exception(f"AI 回傳格式錯誤: {clean_json[:50]}...")

        for idx, item in enumerate(ai_data.get('menu', [])):
            item['id'] = idx + 1
            
        return jsonify(ai_data)

    except Exception as e:
        error_msg = str(e)
        print(f"❌ 發生錯誤: {error_msg}")
        return jsonify({
            "name": f"錯誤: {error_msg}",
            "address": "請截圖這個畫面",
            "phone": "000",
            "minDelivery": 0,
            "menu": [{"id": 1, "name": "發生錯誤，請看上方店名欄位", "price": 0}]
        })

# --- 其他 API ---
@app.route("/api/create_group", methods=['POST'])
def create_group():
    data = request.json
    # 這裡就是剛剛報錯的地方，現在修好了
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