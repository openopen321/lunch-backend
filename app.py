import os
import json
import uuid
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

app = Flask(__name__)
CORS(app)

# 1. 設定 AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("⚠️ 警告：找不到 GEMINI_API_KEY，AI 功能將無法運作！")

# 記憶體資料庫
fake_db = {} 

@app.route("/")
def home():
    return "Real AI Lunch API (with Google Search) is Running!"

# 核心功能：用 AI + Google 搜尋 分析餐廳
@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    data = request.json
    url = data.get('url')
    
    print(f"收到分析請求: {url}")

    try:
        if not GEMINI_API_KEY:
            raise Exception("No API Key")

        # 設定 AI 模型，並啟用「Google 搜尋」工具
        # 這讓 AI 可以真正去網路上查資料，而不是只靠訓練數據
        tools = {'google_search': {}}
        model = genai.GenerativeModel('gemini-1.5-flash', tools=tools)
        
        # 強大的提示詞
        prompt = f"""
        請使用 Google 搜尋功能來調查這個 Google Maps 連結的餐廳：
        {url}

        【任務目標】
        1. 找出這家餐廳的「正確名稱」。
        2. 搜尋這家餐廳最新的「菜單」或「熱門餐點」與「價格」。
        3. 即使 Google Maps 顯示暫停營業，也請忽略狀態，找出它過去販售的餐點。

        【輸出格式】
        請直接回傳純 JSON 字串 (不要 Markdown 標記，不要 ```json)，格式如下：
        {{
            "name": "餐廳名稱",
            "address": "餐廳地址",
            "phone": "餐廳電話",
            "minDelivery": 500,
            "menu": [
                {{"id": 1, "name": "招牌排骨飯", "price": 100}},
                {{"id": 2, "name": "雞腿飯", "price": 110}},
                {{"id": 3, "name": "餐點3", "price": 80}},
                {{"id": 4, "name": "餐點4", "price": 50}},
                {{"id": 5, "name": "餐點5", "price": 40}},
                {{"id": 6, "name": "餐點6", "price": 30}}
            ]
        }}
        """
        
        # 呼叫 AI (這可能會花 5-10 秒，因為它在搜尋)
        response = model.generate_content(prompt)
        
        # 處理 AI 回傳的文字，確保是乾淨的 JSON
        text_response = response.text
        # 移除可能存在的 Markdown 符號
        clean_json = text_response.replace('```json', '').replace('```', '').strip()
        
        # 嘗試解析 JSON
        try:
            ai_data = json.loads(clean_json)
        except json.JSONDecodeError:
            # 如果 AI 回傳的不是標準 JSON，嘗試用正則表達式抓取 JSON 部分
            match = re.search(r'\{.*\}', clean_json, re.DOTALL)
            if match:
                ai_data = json.loads(match.group())
            else:
                raise Exception("AI 回傳格式錯誤")

        # 補上 id (以防 AI 沒給)
        for idx, item in enumerate(ai_data.get('menu', [])):
            if 'id' not in item:
                item['id'] = idx + 1
        
        return jsonify(ai_data)

    except Exception as e:
        print(f"AI 分析失敗: {e}")
        # 萬一失敗，回傳一個友善的錯誤訊息
        return jsonify({
            "name": "無法讀取餐廳 (請手動輸入)",
            "address": "",
            "phone": "",
            "minDelivery": 0,
            "menu": [
                {"id": 1, "name": "請點擊這裡手動新增餐點", "price": 0}
            ]
        })

# --- 以下 API 保持不變 ---

@app.route("/api/create_group", methods=['POST'])
def create_group():
    data = request.json
    group_id = str(uuid.uuid4())[:8]
    fake_db[group_id] = {
        "id": group_id,
        "restaurant": data['restaurant'],
        "orders": [],
        "status": "OPEN",
    }
    return jsonify({"group_id": group_id})

@app.route("/api/group/<group_id>", methods=['GET'])
def get_group(group_id):
    group = fake_db.get(group_id)
    if not group: return jsonify({"error": "Not found"}), 404
    return jsonify(group)

@app.route("/api/group/<group_id>/order", methods=['POST'])
def submit_order(group_id):
    if group_id not in fake_db: return jsonify({"error": "Not found"}), 404
    fake_db[group_id]['orders'].append(request.json)
    return jsonify({"success": True})

@app.route("/api/group/<group_id>/status", methods=['POST'])
def update_status(group_id):
    if group_id not in fake_db: return jsonify({"error": "Not found"}), 404
    fake_db[group_id]['status'] = request.json.get('status')
    return jsonify({"success": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)