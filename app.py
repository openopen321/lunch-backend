import os
import json
import uuid
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
# 設定最大上傳限制為 16MB (避免圖片太大報錯)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
CORS(app)

# 設定 AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# 取得版本號 (除錯用)
try:
    import importlib.metadata
    LIB_VERSION = importlib.metadata.version("google-generativeai")
except:
    LIB_VERSION = "未知"

fake_db = {} 

@app.route("/")
def home():
    return f"Universal Vision API Running! (Lib: {LIB_VERSION})"

@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    try:
        data = request.json
        image_data = data.get('image')
        mime_type = data.get('mime_type', 'image/jpeg')
        
        print("收到圖片分析請求...")

        if not GEMINI_API_KEY:
            raise Exception("Render 環境變數中找不到 GEMINI_API_KEY")

        if not image_data:
            raise Exception("未收到圖片資料")

        # 準備圖片物件
        image_part = {
            "mime_type": mime_type,
            "data": image_data
        }

        # 定義提示詞
        prompt = """
        你是一個專業的菜單辨識助手。請分析這張圖片。
        
        【任務】
        1. 找出圖片中的「餐廳名稱」(如果沒寫，請根據菜色推測一個合理的店名，例如"巷口麵店")。
        2. 辨識所有的「菜色名稱」與「價格」(數字)。
        3. 請忽略無關的文字。

        【輸出 JSON 格式】
        {
            "name": "店名",
            "address": "地址(若有)",
            "phone": "電話(若有)",
            "minDelivery": 0,
            "menu": [
                { "id": 1, "name": "菜名", "price": 100 }
            ]
        }
        """

        # --- 自動嘗試多種視覺模型 ---
        # 依序嘗試，直到成功為止
        candidate_models = [
            "gemini-1.5-flash",       # 首選：快且便宜
            "gemini-1.5-pro",         # 次選：強大
            "gemini-2.0-flash-exp",   # 嘗鮮：最新版
            "gemini-pro-vision"       # 保底：舊版視覺模型
        ]

        response = None
        used_model = ""
        last_error = ""

        for model_name in candidate_models:
            try:
                print(f"嘗試使用模型: {model_name}")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content([prompt, image_part])
                used_model = model_name
                print(f"成功使用 {model_name}！")
                break # 成功就跳出迴圈
            except Exception as e:
                print(f"{model_name} 失敗: {e}")
                last_error = str(e)
                continue # 失敗就換下一個

        if not response:
            raise Exception(f"所有視覺模型都失敗。最後錯誤: {last_error}")
        
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
                "name": f"辨識失敗 ({used_model})",
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
            "name": f"錯誤: {error_str[:50]}...", # 顯示簡短錯誤
            "address": f"Lib: {LIB_VERSION}",
            "phone": "",
            "minDelivery": 0,
            "menu": [{"id": 1, "name": "系統發生錯誤", "price": 0}]
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