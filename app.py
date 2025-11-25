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

# 取得版本號 (確認用)
try:
    import importlib.metadata
    LIB_VERSION = importlib.metadata.version("google-generativeai")
except:
    LIB_VERSION = "未知"

fake_db = {} 

@app.route("/")
def home():
    return f"Gemini 2.5 Backend Running! (Lib: {LIB_VERSION})"

@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    data = request.json
    url = data.get('url')
    print(f"收到網址: {url}")

    try:
        if not GEMINI_API_KEY:
            raise Exception("Render 環境變數中找不到 GEMINI_API_KEY")

        # --- 2025年版模型切換邏輯 ---
        model = None
        used_model_name = ""
        
        # 1. 優先嘗試：Gemini 2.5 Pro (2025年旗艦模型，具備強大搜尋與推理)
        try:
            print("嘗試模型 1: gemini-2.5-pro")
            tools = {'google_search': {}}
            model = genai.GenerativeModel('gemini-2.5-pro', tools=tools)
            used_model_name = "gemini-2.5-pro"
        except:
            pass

        # 2. 次要嘗試：Gemini 2.5 Flash (2025年快速模型)
        if not model:
            try:
                print("嘗試模型 2: gemini-2.5-flash")
                model = genai.GenerativeModel('gemini-2.5-flash', tools={'google_search': {}})
                used_model_name = "gemini-2.5-flash"
            except:
                pass

        # 3. 舊版備援：如果 2.5 都還沒開放，回退到 1.5 系列 (Legacy)
        if not model:
            try:
                print("嘗試模型 3: gemini-1.5-pro (Legacy)")
                model = genai.GenerativeModel('gemini-1.5-pro', tools={'google_search': {}})
                used_model_name = "gemini-1.5-pro"
            except:
                pass

        # 4. 最後防線
        if not model:
            print("嘗試模型 4: gemini-pro (Classic)")
            model = genai.GenerativeModel('gemini-pro')
            used_model_name = "gemini-pro"

        # --- 開始分析 ---
        prompt = f"""
        你是一個專業的台灣團購小幫手。請調查這個 Google Maps 餐廳連結：{url}
        
        【任務】
        1. 利用 Google 搜尋找出「正確店名」。
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
            print(f"模型 {used_model_name} 執行失敗: {api_error}")
            # 遇到 404 Not Found 代表該模型真的沒了，自動降級重試
            if "404" in str(api_error) or "not found" in str(api_error):
                print("模型不存在，降級使用 gemini-pro 重試")
                model = genai.GenerativeModel('gemini-pro')
                used_model_name = "gemini-pro (Fallback)"
                response = model.generate_content(prompt)
            else:
                raise api_error

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
                "name": f"讀取失敗 ({used_model_name})",
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
            "address": f"Model: {used_model_name}", 
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