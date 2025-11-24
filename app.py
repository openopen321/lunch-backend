import os
import json
import uuid
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
import google.generativeai as genai

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
    return "Real AI Lunch API is Running!"

# 核心功能：用 AI 分析餐廳
@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    data = request.json
    url = data.get('url')
    
    restaurant_name = "未知餐廳"
    
    # 步驟 A: 嘗試從網址抓取餐廳名稱
    try:
        # 偽裝成瀏覽器，避免被 Google Maps 直接擋下
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 抓取 og:title (通常是 "餐廳名稱 - Google 地圖")
        og_title = soup.find('meta', property="og:title")
        if og_title and og_title.get('content'):
            restaurant_name = og_title['content'].replace(" - Google 地圖", "").replace(" - Google Maps", "")
    except Exception as e:
        print(f"爬蟲失敗 (正常現象，Google 防禦很強): {e}")
        # 如果爬蟲失敗，還是可以繼續，讓 AI 根據網址或是隨機生成
        restaurant_name = "神秘餐廳 (請手動修改名稱)"

    # 步驟 B: 呼叫 Gemini AI 生成菜單
    try:
        if not GEMINI_API_KEY:
            raise Exception("No API Key")

        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # AI 的提示詞 (Prompt)
        prompt = f"""
        你是一個專業的台灣團購小幫手。
        
        使用者貼了一個餐廳網址，我們偵測到的名稱可能是：「{restaurant_name}」。
        (如果是 '未知餐廳'，請根據上下文或隨機創造一個熱門的台灣午餐餐廳)

        請幫我生成這家餐廳可能販售的菜單，條件如下：
        1. 包含 5-8 項熱門餐點。
        2. 價格要是合理的台幣價格 (TWD)。
        3. 如果是便當店要有排骨/雞腿；如果是飲料店要有珍奶。
        
        請直接回傳純 JSON 格式 (不要 Markdown)，格式如下：
        {{
            "name": "{restaurant_name}",
            "address": "地址由 AI 根據店名推測或留空",
            "phone": "電話由 AI 根據店名推測或留空",
            "minDelivery": 500,
            "menu": [
                {{"id": 1, "name": "餐點名稱", "price": 100}}
            ]
        }}
        """
        
        response = model.generate_content(prompt)
        # 清理 AI 可能回傳的 Markdown 符號
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        ai_data = json.loads(clean_json)
        
        return jsonify(ai_data)

    except Exception as e:
        print(f"AI 生成失敗: {e}")
        # 萬一 AI 掛了，回傳備用資料
        return jsonify({
            "name": restaurant_name,
            "address": "請手動輸入地址",
            "phone": "",
            "minDelivery": 0,
            "menu": [
                {"id": 1, "name": "AI 暫時休息中，請手動輸入餐點", "price": 0}
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