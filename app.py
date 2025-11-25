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

# 取得當前安裝的套件版本
try:
    import importlib.metadata
    LIB_VERSION = importlib.metadata.version("google-generativeai")
except:
    LIB_VERSION = "未知"

fake_db = {} 

@app.route("/")
def home():
    return f"Detective API Running! Lib Version: {LIB_VERSION}"

@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    data = request.json
    url = data.get('url')
    print(f"收到網址: {url}")

    try:
        if not GEMINI_API_KEY:
            raise Exception("Render 環境變數中找不到 GEMINI_API_KEY")

        # --- 嘗試建立模型 (多重備援機制) ---
        model = None
        used_model_name = ""
        
        # 方案 A: 最新版 Gemini 1.5 Flash
        try:
            print(f"嘗試使用 gemini-1.5-flash (Lib: {LIB_VERSION})")
            model = genai.GenerativeModel('gemini-1.5-flash')
            used_model_name = "gemini-1.5-flash"
            # 測試性呼叫 (確認模型存在)
            # model.generate_content("test") 
        except Exception as e:
            print(f"Flash 失敗: {e}")
            
            # 方案 B: 舊版 Gemini Pro (相容性最高)
            try:
                print("降級嘗試 gemini-pro")
                model = genai.GenerativeModel('gemini-pro')
                used_model_name = "gemini-pro"
            except Exception as e2:
                raise Exception(f"所有模型都失敗。Lib版本: {LIB_VERSION}, 錯誤: {e2}")

        # --- 開始分析 ---
        prompt = f"""
        請調查這個餐廳網址：{url}
        請找出「店名」與「菜單」。
        如果無法上網，請根據網址猜測店名，並隨機生成一份合理的台灣午餐菜單。
        
        回傳 JSON 格式：
        {{
            "name": "店名",
            "address": "地址",
            "phone": "電話",
            "minDelivery": 0,
            "menu": [{{ "id": 1, "name": "範例餐點", "price": 100 }}]
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
            ai_data = {
                "name": f"AI 回傳格式錯誤 ({used_model_name})",
                "address": "請手動輸入",
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
        
        # 回傳詳細的除錯資訊給前端
        debug_info = f"錯誤: {error_str} (Lib: {LIB_VERSION})"

        return jsonify({
            "name": debug_info,
            "address": "請截圖給 AI 看",
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