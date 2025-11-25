import os
import json
import uuid
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
# 增加傳輸限制，因為圖片比較大 (預設可能只有幾MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
CORS(app)

# 設定 AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

fake_db = {} 

@app.route("/")
def home():
    return "Menu Image Analysis API Running!"

@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    try:
        data = request.json
        image_data = data.get('image') # Base64 字串
        mime_type = data.get('mime_type', 'image/jpeg')
        
        print("收到圖片分析請求...")

        if not GEMINI_API_KEY:
            raise Exception("Render 環境變數中找不到 GEMINI_API_KEY")

        if not image_data:
            raise Exception("未收到圖片資料")

        # 建立模型：Gemini 1.5 Flash (讀圖速度快且便宜)
        # 如果 Flash 失敗，也可以換成 Pro
        model = genai.GenerativeModel('gemini-1.5-flash')

        prompt = """
        請分析這張菜單圖片。
        
        【任務】
        1. 找出圖片中的「餐廳名稱」(如果圖中沒寫，就叫"未知名稱餐廳")。
        2. 辨識所有的「菜色名稱」與「價格」(數字)。
        3. 如果圖片模糊或無法辨識，請回傳一個空的菜單。

        【輸出 JSON 格式】
        {
            "name": "店名",
            "address": "地址(如果圖中有寫)",
            "phone": "電話(如果圖中有寫)",
            "minDelivery": 0,
            "menu": [
                { "id": 1, "name": "菜名", "price": 100 }
            ]
        }
        """
        
        # 準備圖片物件
        image_part = {
            "mime_type": mime_type,
            "data": image_data
        }

        # 發送給 AI
        response = model.generate_content([prompt, image_part])
        
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
                "name": "圖片讀取失敗",
                "address": "",
                "phone": "",
                "minDelivery": 0,
                "menu": [{"id": 1, "name": "無法辨識文字，請手動輸入", "price": 0}]
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
            "address": "",
            "phone": "",
            "minDelivery": 0,
            "menu": [{"id": 1, "name": "系統發生錯誤", "price": 0}]
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