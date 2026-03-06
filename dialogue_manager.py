# dialogue_manager.py
# الدمج الكامل: المودل يفهم الكلام + GPS حقيقي + RAPTOR

import os, sys, requests, pickle, re, json
from datetime import datetime

# ─── إضافة root الريبو للـ path ───────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from states import State
from raptor.services.raptor_service  import run_raptor_from_assistant_json
from raptor.services.geo_utils       import find_nearest_stop, haversine
from raptor.utils                    import format_legs
from raptor.output_translation       import load_translations


# ─── مسارات ──────────────────────────────────────────────────────────────────
NETWORK_PATH      = os.path.join(BASE_DIR, "data", "network.pkl")
TRANSLATIONS_PATH = os.path.join(BASE_DIR, "data", "translations.txt")

# ─── حدود القاهرة ────────────────────────────────────────────────────────────
CAIRO_MIN_LAT, CAIRO_MAX_LAT = 29.8, 30.3
CAIRO_MIN_LON, CAIRO_MAX_LON = 31.0, 31.6


# ══════════════════════════════════════════════════════════════════════════════
#  تحميل الـ network
# ══════════════════════════════════════════════════════════════════════════════
_network = None

def get_network():
    global _network
    if _network is None:
        with open(NETWORK_PATH, "rb") as f:
            _network = pickle.load(f)
    return _network


# ══════════════════════════════════════════════════════════════════════════════
#  تحميل المودل (مرة وحدة - lazy)
# ══════════════════════════════════════════════════════════════════════════════
_tokenizer = None
_model     = None
_llm_ready = False

def _load_llm():
    global _tokenizer, _model, _llm_ready
    if _llm_ready:
        return True
    try:
        from cairo_assistant.model_manager import get_models
        _, _tokenizer, _model = get_models()
        _llm_ready = True
        print("[LLM] ✅ Model loaded successfully")
        return True
    except Exception as e:
        print(f"[LLM] ⚠️ Model not available: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  استخراج النية من المودل
# ══════════════════════════════════════════════════════════════════════════════

def _llm_extract(user_message):
    """
    يبعت رسالة المستخدم للمودل ويستخرج JSON فيه start_point و end_point.
    يرجع (assistant_json, True) لو نجح، أو (None, False) لو فشل.
    """
    if not _load_llm():
        return None, False

    try:
        from cairo_assistant.assistant_core import ask_cairo_assistant
        response, is_nav = ask_cairo_assistant(user_message, _tokenizer, _model)

        if not is_nav:
            return None, False

        # parse الـ JSON اللي رجع
        json_match = re.search(r'\{.*\}', response.replace('\n', ''))
        if not json_match:
            return None, False

        parsed = json.loads(json_match.group())

        # نتأكد إن فيه start و end
        if "start_point" in parsed and "end_point" in parsed:
            parsed["intent"] = "navigation"
            return parsed, True

    except Exception as e:
        print(f"[LLM] extraction error: {e}")

    return None, False


def _llm_answer_general(user_message):
    """للأسئلة العامة - يرجع رد نصي أو None"""
    if not _load_llm():
        return None
    try:
        from cairo_assistant.assistant_core import ask_cairo_assistant
        response, is_nav = ask_cairo_assistant(user_message, _tokenizer, _model)
        if not is_nav:
            return response
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  GPS
# ══════════════════════════════════════════════════════════════════════════════

def get_live_location():
    try:
        res = requests.get("http://127.0.0.1:5000/get_location", timeout=3)
        data = res.json()
        if data["lat"] is None:
            return None
        return float(data["lat"]), float(data["lon"])
    except Exception:
        return None


def _nearest_stop_info(user_lat, user_lon):
    """يرجع (اسم عربي, مسافة بالمتر, رابط الخريطة) أو None"""
    network  = get_network()
    stop_id  = find_nearest_stop(network, (user_lat, user_lon), max_distance_km=5.0)
    if stop_id is None:
        return None

    stop_row = network.stops[network.stops['stop_id'] == stop_id].iloc[0]
    dist_m   = round(haversine(user_lat, user_lon,
                               stop_row['stop_lat'], stop_row['stop_lon']) * 1000)

    # الاسم العربي
    stop_name_func = load_translations(TRANSLATIONS_PATH, network)
    arabic_name    = stop_name_func(stop_id)

    # رابط الخريطة
    link = (
        f"https://www.openstreetmap.org/directions"
        f"?engine=fossgis_osrm_foot"
        f"&route={user_lat},{user_lon};{stop_row['stop_lat']},{stop_row['stop_lon']}"
    )

    return arabic_name, dist_m, link


# ══════════════════════════════════════════════════════════════════════════════
#  RAPTOR
# ══════════════════════════════════════════════════════════════════════════════

def _run_raptor(assistant_json, departure_time):
    network       = get_network()
    legs_or_error = run_raptor_from_assistant_json(
        network, assistant_json, departure_time=departure_time
    )

    if isinstance(legs_or_error, dict) and "error" in legs_or_error:
        msg = f"⚠️ {legs_or_error.get('message', 'مفيش حل متاح')}"
        if "suggestions" in legs_or_error:
            msg += f"\n💡 اقتراحات: {', '.join(legs_or_error['suggestions'])}"
        return msg

    if isinstance(legs_or_error, str) and legs_or_error.startswith("Error"):
        return f"⚠️ {legs_or_error}"

    lines = format_legs(legs_or_error)
    return "\n".join(f"  {i+1}) {line}" for i, line in enumerate(lines))


def _parse_time(raw):
    raw = (raw or "").strip()
    if not raw or raw == "دلوقتي":
        return datetime.now().strftime("%H:%M:%S")
    if ":" in raw and len(raw) <= 5:
        return raw + ":00"
    return "08:00:00"


# ══════════════════════════════════════════════════════════════════════════════
#  مدير الحوار
# ══════════════════════════════════════════════════════════════════════════════

class DialogueManager:

    def __init__(self):
        self.state          = State.GREETING
        self.start_location = None
        self.destination    = None
        self.time           = None

    def process(self, message):
        message = (message or "").strip()

        # ── ترحيب ──────────────────────────────────────────────────────────
        if self.state == State.GREETING:
            self.state = State.ASK_DESTINATION
            return "مساء الخير 👋\nتحب تروح فين؟"

        # ── الوجهة ─────────────────────────────────────────────────────────
        elif self.state == State.ASK_DESTINATION:
            self.destination = message
            self.state = State.ASK_START
            return "تمام 👍\nانت دلوقتي فين؟"

        # ── موقع البداية ───────────────────────────────────────────────────
        elif self.state == State.ASK_START:
            self.start_location = message
            self.state = State.ASK_TIME
            return "هتتحرك امتى؟\n(اكتب: دلوقتي  أو وقت زي 08:30)"

        # ── حساب الطريق ────────────────────────────────────────────────────
        elif self.state == State.ASK_TIME:
            self.time      = message
            self.state     = State.END
            departure_time = _parse_time(message)

            # 1) المودل يحاول يفهم الكلام ويستخرج المحطات
            #    بيبني جملة كاملة من إجابات المستخدم السابقة
            full_query = f"عايز أروح من {self.start_location} إلى {self.destination}"
            assistant_json, used_llm = _llm_extract(full_query)

            # لو المودل مش شغال أو فشل → fallback مباشر
            if assistant_json is None:
                assistant_json = {
                    "intent":      "navigation",
                    "start_point": {"official_name_ar": self.start_location},
                    "end_point":   {"official_name_ar": self.destination}
                }

            # 2) RAPTOR يحسب الطريق الحقيقي
            route_lines = _run_raptor(assistant_json, departure_time)
            header      = f"أفضل طريق من {self.start_location} إلى {self.destination}:\n\n"
            llm_note    = "\n🤖 (مُحلَّل بالذكاء الاصطناعي)" if used_llm else ""
            route       = header + route_lines + llm_note

            # 3) GPS الحقيقي من الموبايل
            location = get_live_location()

            if location is None:
                return (
                    route +
                    "\n\n⚠️ لم أستطع تحديد موقعك.\n"
                    "افتح صفحة الخريطة من الموبايل أولاً:\n"
                    "http://<IP>:5000/"
                )

            user_lat, user_lon = location

            # 4) Geofencing
            inside_cairo = (
                CAIRO_MIN_LAT <= user_lat <= CAIRO_MAX_LAT and
                CAIRO_MIN_LON <= user_lon <= CAIRO_MAX_LON
            )
            if not inside_cairo:
                return (
                    route +
                    "\n\n📍 يبدو أنك خارج نطاق خدمة القاهرة حالياً.\n"
                    "الخدمة تعمل داخل القاهرة الكبرى فقط."
                )

            # 5) أقرب محطة من الـ network الحقيقي
            stop_info = _nearest_stop_info(user_lat, user_lon)

            if stop_info is None:
                return route + "\n\n⚠️ لم أجد محطة قريبة منك (أكثر من 5 كم)."

            arabic_name, dist_m, link = stop_info

            return (
                route +
                f"\n\n📍 أقرب محطة ليك: {arabic_name}\n"
                f"المسافة: {dist_m} متر تقريبًا\n\n"
                f"اتبع الخريطة:\n{link}"
            )

        # ── بعد انتهاء الرحلة ──────────────────────────────────────────────
        else:
            llm_answer = _llm_answer_general(message)
            if llm_answer:
                return llm_answer
            return "رحلة سعيدة 🚇"
