import os
import json
import uuid
import requests
import urllib.parse
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
    
    # 步驟 A: 嘗試多種方式抓取餐廳名稱 (更強的抓取邏輯)
    try:
        # 偽裝成瀏覽器
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        # allow_redirects=True 會自動轉址到長網址
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        
        # 方法 1: 從長網址解析 (最準確，不受營業時間影響)
        # 格式通常是: https://www.google.com/maps/place/店名/@座標...
        final_url = response.url
        if "/place/" in final_url:
            # 擷取 /place/ 後面的字串
            path_parts = final_url.split("/place/")
            if len(path_parts) > 1:
                raw_name = path_parts[1].split("/")[0]
                # URL 解碼 (例如 %E9%BC%8E -> 鼎)
                decoded_name = urllib.parse.unquote(raw_name).replace("+", " ")
                if decoded_name:
                    restaurant_name = decoded_name

        # 方法 2: 如果網址抓不到，才試著抓網頁標題 (Fallback)
        if restaurant_name == "未知餐廳":
            soup = BeautifulSoup(response.text, 'html.parser')
            og_title = soup.find('meta', property="og:title")
            if og_title and og_title.get('content'):
                # 移除多餘的後綴
                clean_title = og_title['content'].replace(" - Google 地圖", "").replace(" - Google Maps", "")
                restaurant_name = clean_title

    except Exception as e:
        print(f"爬蟲失敗 (正常現象，Google 防禦很強): {e}")
        restaurant_name = "神秘餐廳 (請手動修改名稱)"

    # 步驟 B: 呼叫 Gemini AI 生成菜單 (更新提示詞)
    try:
        if not GEMINI_API_KEY:
            raise Exception("No API Key")

        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 加強版提示詞：忽略營業時間，強制讀取
        prompt = f"""
        你是一個專業的台灣團購小幫手。
        
        使用者貼了一個餐廳網址，經過解析，這家餐廳的名稱是：「{restaurant_name}」。
        
        【重要任務】
        我們是為了「稍後用餐」做預先點餐統計，所以：
        1. 請「完全忽略」該餐廳目前的營業狀態（即使顯示休息中或已打烊）。
        2. 請根據你的知識庫，列出這家「{restaurant_name}」的真實菜單或熱門品項。
        3. 如果是不知名的餐廳，請根據店名推測可能販售的餐點（例如有'排骨'就出排骨飯）。

        【輸出格式要求】
        請直接回傳純 JSON 格式 (不要 Markdown)，欄位如下：
        1. menu 至少包含 6-10 項餐點。
        2. price 請填寫具體的台幣價格 (數字)。
        3. 必須包含主食類 (便當/麵/飯) 與單點類。
        
        JSON 範例：
        {{
            "name": "{restaurant_name}",
            "address": "請嘗試填寫地址",
            "phone": "請嘗試填寫電話",
            "minDelivery": 500,
            "menu": [
                {{"id": 1, "name": "招牌排骨飯", "price": 100}},
                {{"id": 2, "name": "雞腿飯", "price": 110}}
            ]
        }}
        """
        
        response = model.generate_content(prompt)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        ai_data = json.loads(clean_json)
        
        return jsonify(ai_data)

    except Exception as e:
        print(f"AI 生成失敗: {e}")
        return jsonify({
            "name": restaurant_name,
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