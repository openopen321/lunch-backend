import os
import json
import uuid
import re
import urllib.parse
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
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
    return "Ultimate AI Lunch API is Running!"

# --- 強力解析函式：從 Google Maps 網址挖出店名 ---
def extract_place_name(url):
    try:
        # 1. 偽裝瀏覽器，還原短網址 (例如 maps.app.goo.gl/...)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        long_url = response.url
        print(f"解析長網址: {long_url}")

        # 2. 嘗試從長網址擷取 /place/店名/
        # 格式通常是: https://www.google.com/maps/place/鼎泰豐/...
        if "/place/" in long_url:
            parts = long_url.split("/place/")
            if len(parts) > 1:
                raw_name = parts[1].split("/")[0]
                # URL 解碼 (把 %E9%BC... 轉回中文字)
                name = urllib.parse.unquote(raw_name).replace("+", " ")
                return name
        
        # 3. 如果不是 /place/ 格式，嘗試找尋 query=店名
        parsed = urllib.parse.urlparse(long_url)
        qs = urllib.parse.parse_qs(parsed.query)
        if 'q' in qs:
            return qs['q'][0]
            
    except Exception as e:
        print(f"網址解析失敗: {e}")
    
    return None

# 核心功能：分析餐廳
@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    data = request.json
    url = data.get('url')
    
    print(f"收到分析請求: {url}")

    # 第一階段：先用 Python 硬解出店名
    detected_name = extract_place_name(url)
    if not detected_name:
        detected_name = "未知餐廳"
    
    print(f"偵測到的店名: {detected_name}")

    try:
        if not GEMINI_API_KEY:
            raise Exception("No API Key")

        # 啟用 Google 搜尋工具
        tools = {'google_search': {}}
        model = genai.GenerativeModel('gemini-1.5-flash', tools=tools)
        
        # 第二階段：根據店名，精準搜尋菜單
        # 關鍵：我們不只給網址，我們直接給它「店名 + 菜單」作為關鍵字
        search_query = f"{detected_name} 菜單 價格"
        if detected_name == "未知餐廳":
            search_query = f"分析這個網址的餐廳菜單: {url}"

        prompt = f"""
        請幫我搜尋：「{search_query}」

        【任務目標】
        1. 確認這家餐廳的正確名稱 (我們偵測到可能是: {detected_name})。
        2. 搜尋它最新的「菜單品項」與「價格」(TWD)。
        3. 請忽略「休息中」或「已打烊」的狀態，我們要預訂明天的午餐。
        4. 如果找不到確切菜單，請根據該店類型 (例如便當店、麵店) 推薦 5-8 個常見的品項與預估價格。

        【輸出格式】
        請直接回傳純 JSON 字串 (不要 Markdown，不要 ```json)，格式如下：
        {{
            "name": "{detected_name if detected_name != '未知餐廳' else '請填入正確店名'}",
            "address": "請填入地址",
            "phone": "請填入電話",
            "minDelivery": 500,
            "menu": [
                {{"id": 1, "name": "招牌飯", "price": 100}},
                {{"id": 2, "name": "雞腿飯", "price": 110}},
                {{"id": 3, "name": "排骨飯", "price": 100}},
                {{"id": 4, "name": "滷肉飯", "price": 40}},
                {{"id": 5, "name": "貢丸湯", "price": 30}}
            ]
        }}
        """
        
        response = model.generate_content(prompt)
        text_response = response.text
        clean_json = text_response.replace('```json', '').replace('```', '').strip()
        
        # 嘗試解析 JSON
        try:
            ai_data = json.loads(clean_json)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', clean_json, re.DOTALL)
            if match:
                ai_data = json.loads(match.group())
            else:
                raise Exception("AI 回傳格式錯誤")

        # 補上 ID
        for idx, item in enumerate(ai_data.get('menu', [])):
            item['id'] = idx + 1
        
        return jsonify(ai_data)

    except Exception as e:
        print(f"AI 分析失敗: {e}")
        # 即使 AI 失敗，至少回傳我們剛剛抓到的店名
        return jsonify({
            "name": detected_name if detected_name else "無法讀取餐廳",
            "address": "請手動輸入地址",
            "phone": "",
            "minDelivery": 0,
            "menu": [
                {"id": 1, "name": "AI 暫時無法讀取，請手動輸入", "price": 0}
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