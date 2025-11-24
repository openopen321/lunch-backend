import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup # 用來抓 Google Maps 標題 (簡單版)

app = Flask(__name__)
CORS(app) # 允許 React 前端呼叫

# 環境變數 (只剩這個需要設定)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# 簡易記憶體資料庫 (重啟會消失，實際建議用 MongoDB Free Tier)
fake_db = {} 

@app.route("/")
def home():
    return "Lunch Order API is Running!"

# API: AI 分析菜單 (Mocking logic for stability in demo)
@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    data = request.json
    url = data.get('url')
    
    # 這裡我們模擬 AI 回傳的結果
    # 實際上你會在這裡加入 requests.get(url) 抓圖片 -> 傳給 Gemini
    
    # 模擬回傳資料
    mock_response = {
        "name": "AI 辨識出的美味便當 (來自 Google Maps)",
        "address": "台北市科技大樓旁",
        "phone": "02-1234-5678",
        "minDelivery": 500,
        "menu": [
            {"id": 1, "name": "招牌排骨飯", "price": 100},
            {"id": 2, "name": "酥炸雞腿飯", "price": 110},
            {"id": 3, "name": "魚排飯", "price": 120},
            {"id": 4, "name": "滷肉飯 (小)", "price": 40}
        ]
    }
    return jsonify(mock_response)

# API: 建立團購
@app.route("/api/create_group", methods=['POST'])
def create_group():
    data = request.json
    # 產生一個簡單的 Group ID
    import uuid
    group_id = str(uuid.uuid4())[:8]
    
    fake_db[group_id] = {
        "id": group_id,
        "restaurant": data['restaurant'],
        "orders": [],
        "status": "OPEN",
        "created_at": "2023-..."
    }
    return jsonify({"group_id": group_id})

# API: 取得團購資料 (讓使用者進入頁面時呼叫)
@app.route("/api/group/<group_id>", methods=['GET'])
def get_group(group_id):
    group = fake_db.get(group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    return jsonify(group)

# API: 送出訂單
@app.route("/api/group/<group_id>/order", methods=['POST'])
def submit_order(group_id):
    if group_id not in fake_db:
        return jsonify({"error": "Group not found"}), 404
    
    order_data = request.json
    # 將訂單加入資料庫
    fake_db[group_id]['orders'].append(order_data)
    
    return jsonify({"success": True, "current_orders": fake_db[group_id]['orders']})

# API: 結單/更新狀態
@app.route("/api/group/<group_id>/status", methods=['POST'])
def update_status(group_id):
    if group_id not in fake_db:
        return jsonify({"error": "Group not found"}), 404
        
    status = request.json.get('status')
    fake_db[group_id]['status'] = status
    return jsonify({"success": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)