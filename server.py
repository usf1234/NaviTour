# server.py
# سيرفر Flask - GPS + شات بوت + أقرب محطة حقيقية

import os, sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
for p in [BASE_DIR, REPO_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from flask import Flask, request, jsonify, send_file
from dialogue_manager import DialogueManager

app          = Flask(__name__)
user_location = {"lat": None, "lon": None}
bot          = DialogueManager()

# ── صفحات ──────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return send_file(os.path.join(BASE_DIR, "location.html"))

@app.route("/chat")
def chat_page():
    return send_file(os.path.join(BASE_DIR, "chat.html"))

# ── GPS endpoints ───────────────────────────────────────────────────────────

@app.route("/location", methods=["POST"])
def receive_location():
    data = request.json
    user_location["lat"] = float(data["lat"])
    user_location["lon"] = float(data["lon"])
    print(f"[GPS] {user_location}")
    return jsonify({"status": "received"})

@app.route("/get_location", methods=["GET"])
def get_location():
    return jsonify(user_location)

@app.route("/nearest", methods=["GET"])
def nearest():
    if user_location["lat"] is None:
        return jsonify({"stop": None})

    from dialogue_manager import _nearest_stop_info
    info = _nearest_stop_info(user_location["lat"], user_location["lon"])

    if info is None:
        return jsonify({"stop": None})

    arabic_name, dist_m, _ = info

    # إحداثيات المحطة للخريطة
    from dialogue_manager import get_network
    from raptor.output_translation import load_translations
    import os
    network = get_network()
    TRANSLATIONS_PATH = os.path.join(REPO_DIR, "data", "translations.txt")
    stop_name_func = load_translations(TRANSLATIONS_PATH, network)

    # نلاقي الـ stop_id من الاسم العربي
    from raptor.services.geo_utils import find_nearest_stop
    stop_id  = find_nearest_stop(network, (user_location["lat"], user_location["lon"]))
    stop_row = network.stops[network.stops['stop_id'] == stop_id].iloc[0]

    return jsonify({
        "stop":     arabic_name,
        "lat":      float(stop_row['stop_lat']),
        "lon":      float(stop_row['stop_lon']),
        "distance": dist_m
    })

# ── Chat endpoints ──────────────────────────────────────────────────────────

@app.route("/message", methods=["POST"])
def message():
    data    = request.json or {}
    user_msg = data.get("message", "")
    reply   = bot.process(user_msg)
    return jsonify({"reply": reply})

@app.route("/reset", methods=["POST"])
def reset():
    global bot
    bot = DialogueManager()
    return jsonify({"status": "reset"})

# ── تشغيل ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚇 NaviTour running → http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
