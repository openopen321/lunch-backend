import os
import json
import re
import uuid
import sys
import urllib.parse
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# 設定 AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- 輔助函式：還原短網址並擷取店名 ---
def resolve_and_extract_name(url):
    """
    嘗試將 maps.app.goo.gl 短網址還原，並從中提取店名。
    這能大幅增加 AI 判斷的準確率。
    """
    try:
        print(f"正在解析網址: {url}")
        # 1. 還原長網址 (設定 timeout 避免卡住)
        # 偽裝 User-Agent 避免被秒擋
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=5)
        long_url = response.url
        print(f"還原後網址: {long_url}")

        # 2. 嘗試從長網址中抓取 /place/店名/
        # 格式通常是 https://www.google.com/maps/place/店名/@座標...
        if "/place/" in long_url:
            parts = long_url.split("/place/")
            if len(parts) > 1:
                # 取出店名部分，並做 URL Decode (把 %E9%BC... 轉回中文)
                raw_name = parts[1].split("/")[0]
                name = urllib.parse.unquote(raw_name).replace("+", " ")
                print(f"網址內含店名: {name}")
                return name
    except Exception as e:
        print(f"網址解析失敗 (不影響後續 AI 執行): {e}")
    
    return None

# --- 自動尋找可用模型 ---
def get_best_available_model():
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        # 優先順序：Flash > Pro
        for name in available_models:
            if 'flash' in name.lower() and 'legacy' not in name.lower(): return name
        for name in available_models:
            if 'pro' in name.lower() and 'legacy' not in name.lower(): return name
        if available_models: return available_models[0]
    except:
        pass
    return "models/gemini-1.5-flash"

fake_db = {} 

@app.route("/")
def home():
    return "Precision AI Lunch API Running!"

@app.route("/api/analyze_menu", methods=['POST'])
def analyze_menu():
    data = request.json
    url = data.get('url')
    
    # 1. 先嘗試用 Python 硬解店名
    extracted_name = resolve_and_extract_name(url)
    
    # 2. 決定搜尋關鍵字
    if extracted_name:
        search_query = f"{extracted_name} 菜單 價格"
        context_info = f"我們已經從網址確認這家店名叫做：「{extracted_name}」。"
    else:
        search_query = f"Google Maps 網址 {url} 的餐廳菜單"
        context_info = "請試著從網址中分析店名。"

    try:
        if not GEMINI_API_KEY:
            raise Exception("Render 環境變數中找不到 GEMINI_API_KEY")

        model_name = get_best_available_model()
        print(f"使用模型: {model_name}")

        try:
            tools = {'google_search': {}}
            model = genai.GenerativeModel(model_name, tools=tools)
        except:
            model = genai.GenerativeModel(model_name)

        # --- 嚴格版提示詞 ---
        prompt = f"""
        請執行 Google 搜尋：{search_query}
        
        【重要資訊】
        {context_info}

        【任務目標】
        1. 找出這家餐廳最新的「菜單」與「價格」(TWD)。
        2. 請忽略「休息中」或「已打烊」的狀態。
        
        【嚴格限制】
        1. **絕對禁止捏造菜單**。如果你找不到這家特定餐廳的菜單，請直接回傳空白菜單，不要隨機生成別家店的資料。
        2. 如果找到的資料很舊，請盡量使用。

        【輸出 JSON 格式】
        {{
            "name": "{extracted_name if extracted_name else '搜尋到的店名'}",
            "address": "搜尋到的地址",
            "phone": "搜尋到的電話",
            "minDelivery": 0,
            "menu": [
                {{ "id": 1, "name": "菜色名稱", "price": 100 }}
            ]
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
                "name": extracted_name if extracted_name else "讀取失敗",
                "address": "請手動輸入",
                "phone": "",
                "minDelivery": 0,
                "menu": [{"id": 1, "name": "AI 找不到菜單，請手動輸入", "price": 0}]
            }

        # 檢查 AI 是否回傳了空的或錯誤的店名，如果是，強制使用我們抓到的店名
        if extracted_name and (ai_data.get("name") == "店名" or not ai_data.get("name")):
            ai_data["name"] = extracted_name

        # 補 ID
        for idx, item in enumerate(ai_data.get('menu', [])):
            item['id'] = idx + 1
            
        return jsonify(ai_data)

    except Exception as e:
        error_str = str(e)
        print(f"❌ 發生錯誤: {error_str}")
        
        return jsonify({
            "name": f"系統錯誤: {error_str}",
            "address": "", 
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