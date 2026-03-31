import requests
import time
import csv
import os
import threading
from datetime import datetime, timedelta, timezone # تم إضافة timezone و timedelta للتوقيت
from flask import Flask

# =========================
# الإعدادات
# =========================
TWELVEDATA_KEY = "867e160b02b3402e8ddf705c03544487"
TOKEN = "8212195518:AAHqa5jb5h_el4ohPMc0pAxqRAQCc7kUeJI"
CHAT_IDS = ["5652097199", "8214327595"] 

LOG_FILE = "forex_brain.csv"

SYMBOLS_CONFIG = {
    "EUR/USD": {"sl_percent": 0.0003, "tp_percent": 0.0009},
    "GBP/USD": {"sl_percent": 0.0003, "tp_percent": 0.0009},
    "EUR/GBP": {"sl_percent": 0.0002, "tp_percent": 0.0006},
    "XAU/USD": {"sl_percent": 0.0005, "tp_percent": 0.0015}
}

active_trades = {}

# =========================
# دوال البوت الأساسية
# =========================
def send_msg(text, specific_chat=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    chats = [specific_chat] if specific_chat else CHAT_IDS
    for cid in chats:
        try:
            requests.post(url, data={"chat_id": cid, "text": text, "parse_mode": "Markdown"})
        except:
            print("خطأ إرسال")

def save_trade(symbol, result, rsi_val):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "symbol", "result", "rsi"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now(),
            "symbol": symbol,
            "result": result,
            "rsi": rsi_val
        })

def get_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=100&apikey={TWELVEDATA_KEY}"
    try:
        res = requests.get(url).json()
        if "values" not in res:
            return None, [], [], []
        data = res["values"]
        closes = [float(d["close"]) for d in data][::-1]
        highs = [float(d["high"]) for d in data][::-1]
        lows = [float(d["low"]) for d in data][::-1]
        volumes = [float(d["volume"]) for d in data][::-1]
        return closes, highs, lows, volumes
    except:
        return None, [], [], []

def rsi(data, period=14):
    if len(data) < period + 1:
        return 50
    deltas = [data[i] - data[i-1] for i in range(1, len(data))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [abs(d) if d < 0 else 0 for d in deltas[-period:]]
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    return 100 - (100 / (1 + (avg_g / (avg_l if avg_l != 0 else 1))))

def is_bad_zone(rsi_val):
    if not os.path.isfile(LOG_FILE):
        return False
    try:
        with open(LOG_FILE, mode='r') as f:
            reader = csv.DictReader(f)
            losses = 0
            for row in reader:
                if "LOSS" in row['result']:
                    old_rsi = float(row.get('rsi', 50))
                    if abs(old_rsi - rsi_val) < 3:
                        losses += 1
            return losses >= 3
    except:
        return False

def candle_confirmation(closes):
    if len(closes) < 3:
        return None
    if closes[-1] > closes[-2]:
        return "BULLISH"
    elif closes[-1] < closes[-2]:
        return "BEARISH"
    return None

def score_trade(rsi_val, price, ma100, fib, candle):
    score = 0
    score += 2  
    if 30 < rsi_val < 70:
        score += 2
    if abs(price - fib) / price < 0.001:
        score += 3
    if candle:
        score += 3
    return score

def strategy(symbol, closes, highs, lows, volumes):
    if len(active_trades) >= 3:
        return None, None, None, None, None

    price = closes[-1]
    rsi_val = rsi(closes)

    if is_bad_zone(rsi_val):
        print(f"⚠️ تم تجنب صفقة بسبب الذاكرة RSI={rsi_val}")
        return None, None, None, None, None

    momentum = closes[-1] - closes[-5]
    if abs(momentum) < 0.0002:
        return None, None, None, None, None

    ma100 = sum(closes[-100:]) / 100
    recent_high = max(highs[-50:])
    recent_low = min(lows[-50:])
    fib = recent_high - ((recent_high - recent_low) * 0.618)
    candle = candle_confirmation(closes)
    config = SYMBOLS_CONFIG[symbol]

    # BUY
    if price > ma100 and price <= fib * 1.0005 and rsi_val < 45 and candle == "BULLISH":
        sl = price * (1 - config['sl_percent'])
        tp = price * (1 + config['tp_percent'])
        score = score_trade(rsi_val, price, ma100, fib, candle)
        return "BUY", price, sl, tp, score

    # SELL
    if price < ma100 and price >= fib * 0.9995 and rsi_val > 55 and candle == "BEARISH":
        sl = price * (1 + config['sl_percent'])
        tp = price * (1 - config['tp_percent'])
        score = score_trade(rsi_val, price, ma100, fib, candle)
        return "SELL", price, sl, tp, score

    return None, None, None, None, None

# =========================
# خادم Flask (لخداع منصة Render)
# =========================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running online!"

# =========================
# محرك تشغيل البوت في الخلفية
# =========================
def run_bot():
    print("🚀 بوت التداول بنسبة مخاطرة 3:1 يعمل الآن (10ص - 9م)...", flush=True)
    send_msg("✅ *تم تفعيل النظام الجديد!*\n\n- وقت العمل: 10:00 ص إلى 09:00 م (بتوقيت سوريا).\n- رسائل التأكيد: مفعلة كل 5 دقائق.\n- الاستراتيجية: المومنتوم، فيبوناتشي، وذاكرة الخسارة.")

    last_check = 0
    while True:
        try:
            # حساب وقت سوريا الحالي
            syria_now = datetime.now(timezone(timedelta(hours=3)))
            current_hour = syria_now.hour
            
            # شرط وقت العمل (من 10 صباحاً إلى قبل 9 مساءً)
            if 10 <= current_hour < 21:
                curr = time.time()
                if curr - last_check >= 300 or last_check == 0:
                    # رسالة التأكيد الدورية
                    send_msg(f"📡 *البوت يفحص السوق الآن...*\n⏰ توقيت سوريا: {syria_now.strftime('%H:%M')}")
                    print(f"\n[{syria_now.strftime('%H:%M')}] جولة فحص جديدة...", flush=True)
                    
                    for symbol in SYMBOLS_CONFIG.keys():
                        closes, highs, lows, volumes = get_data(symbol)
                        if not closes: continue
                        
                        if symbol in active_trades:
                            t = active_trades[symbol]
                            p = closes[-1]
                            res = None
                            if t['type'] == "BUY":
                                if p >= t['tp']: res = "WIN ✅"
                                elif p <= t['sl']: res = "LOSS ❌"
                            else:
                                if p <= t['tp']: res = "WIN ✅"
                                elif p >= t['sl']: res = "LOSS ❌"
                            
                            if res:
                                send_msg(f"🏁 *إغلاق صفقة:* `{symbol}`\nالنتيجة: {res}\nالسعر: `{p}`")
                                save_trade(symbol, res, rsi(closes))
                                del active_trades[symbol]
                        else:
                            sig, ent, sl, tp, score = strategy(symbol, closes, highs, lows, volumes)
                            if sig:
                                msg = (f"🔥 *إشارة {sig} (إدارة 3:1)*\n\n"
                                       f"💱 الزوج: `{symbol}`\n"
                                       f"💵 دخول: `{round(ent, 5)}`\n"
                                       f"🛑 وقف الخسارة: `{round(sl, 5)}`\n"
                                       f"🎯 الهدف (3x): `{round(tp, 5)}`\n"
                                       f"⭐ التقييم: `{score}/10`\n"
                                       f"⚖️ المخاطرة: 1% مقابل 3% ربح")
                                send_msg(msg)
                                active_trades[symbol] = {"type": sig, "entry": ent, "sl": sl, "tp": tp}
                    last_check = curr
            else:
                # وضع الاستراحة خارج الساعات المحددة
                if syria_now.minute == 0 and syria_now.second < 40:
                    print(f"😴 وضع الاستراحة (توقيت سوريا: {syria_now.strftime('%H:%M')})", flush=True)
            
            time.sleep(30) # فحص الوقت كل 30 ثانية
        except Exception as e:
            print(f"⚠️ خطأ: {e}", flush=True)
            time.sleep(10)

# =========================
# التشغيل النهائي (الويب + البوت)
# =========================
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
        
