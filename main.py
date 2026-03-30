import requests
import time
import csv
import os
import json
from datetime import datetime

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
last_ping = 0

# =========================
# إرسال تلغرام
# =========================
def send_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for cid in CHAT_IDS:
        try:
            requests.post(url, data={"chat_id": cid, "text": text})
        except:
            print("خطأ إرسال")

# =========================
# حفظ البيانات (Smart AI)
# =========================
def save_trade(symbol, result, rsi_val, score):
    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["time","symbol","result","rsi","score"])

        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "time": datetime.now(),
            "symbol": symbol,
            "result": result,
            "rsi": rsi_val,
            "score": score
        })

# =========================
# AI Prediction
# =========================
def predict_trade(rsi_val, score):
    if not os.path.isfile(LOG_FILE):
        return 50

    wins = 0
    total = 0

    try:
        with open(LOG_FILE, mode='r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                old_rsi = float(row.get("rsi", 50))
                old_score = float(row.get("score", 0))

                if abs(old_rsi - rsi_val) < 3 and abs(old_score - score) < 2:
                    total += 1
                    if "WIN" in row["result"]:
                        wins += 1

        if total == 0:
            return 50

        return int((wins / total) * 100)

    except:
        return 50

# =========================
# RSI
# =========================
def rsi(data, period=14):
    if len(data) < period + 1:
        return 50

    deltas = [data[i] - data[i-1] for i in range(1, len(data))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [abs(d) if d < 0 else 0 for d in deltas[-period:]]

    avg_g = sum(gains) / period
    avg_l = sum(losses) / period

    return 100 - (100 / (1 + (avg_g / (avg_l if avg_l != 0 else 1))))

# =========================
# Candle Confirmation
# =========================
def candle_confirmation(closes):
    if len(closes) < 3:
        return None

    if closes[-1] > closes[-2]:
        return "BULLISH"
    elif closes[-1] < closes[-2]:
        return "BEARISH"

    return None

# =========================
# Smart Learning
# =========================
def is_bad_zone(rsi_val):
    if not os.path.isfile(LOG_FILE):
        return False

    losses = 0

    try:
        with open(LOG_FILE, mode='r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "LOSS" in row['result']:
                    old_rsi = float(row.get('rsi', 50))
                    if abs(old_rsi - rsi_val) < 3:
                        losses += 1

        return losses >= 3

    except:
        return False

# =========================
# Score
# =========================
def score_trade(rsi_val, price, fib, candle):
    score = 0

    if 30 < rsi_val < 70:
        score += 2

    if abs(price - fib) / price < 0.001:
        score += 4

    if candle:
        score += 4

    return score

# =========================
# البيانات
# =========================
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

        return closes, highs, lows

    except:
        return None, [], []

# =========================
# الاستراتيجية
# =========================
def strategy(symbol, closes, highs, lows):
    if len(active_trades) >= 3:
        return None, None, None, None, None, None

    price = closes[-1]
    rsi_val = rsi(closes)

    if is_bad_zone(rsi_val):
        print("⚠️ منطقة خطر تم تجنبها")
        return None, None, None, None, None, None

    momentum = closes[-1] - closes[-5]
    if abs(momentum) < 0.0002:
        return None, None, None, None, None, None

    ma100 = sum(closes[-100:]) / 100

    recent_high = max(highs[-50:])
    recent_low = min(lows[-50:])
    fib = recent_high - ((recent_high - recent_low) * 0.618)

    candle = candle_confirmation(closes)

    config = SYMBOLS_CONFIG[symbol]

    score = score_trade(rsi_val, price, fib, candle)
    probability = predict_trade(rsi_val, score)

    print(f"📊 Score={score} | AI={probability}%")

    if probability < 60:
        print("❌ AI رفض الصفقة")
        return None, None, None, None, None, None

    if price > ma100 and price <= fib * 1.0005 and rsi_val < 45 and candle == "BULLISH":
        sl = price * (1 - config['sl_percent'])
        tp = price * (1 + config['tp_percent'])
        return "BUY", price, sl, tp, score, probability

    if price < ma100 and price >= fib * 0.9995 and rsi_val > 55 and candle == "BEARISH":
        sl = price * (1 + config['sl_percent'])
        tp = price * (1 - config['tp_percent'])
        return "SELL", price, sl, tp, score, probability

    return None, None, None, None, None, None

# =========================
# التشغيل
# =========================
print("🚀 البوت يعمل الآن (AI Prediction + Smart Learning)...")

while True:
    try:
        now = time.time()

        if now - last_ping >= 300:
            print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] البوت يعمل...")
            send_msg("📡 البوت يفحص السوق الآن (5M)...")
            last_ping = now

        for symbol in SYMBOLS_CONFIG.keys():
            print(f"🔄 فحص {symbol}...")

            closes, highs, lows = get_data(symbol)

            if not closes:
                print("❌ فشل البيانات")
                continue

            price = closes[-1]

            if symbol in active_trades:
                t = active_trades[symbol]
                res = None

                if t['type'] == "BUY":
                    if price >= t['tp']:
                        res = "WIN"
                    elif price <= t['sl']:
                        res = "LOSS"
                else:
                    if price <= t['tp']:
                        res = "WIN"
                    elif price >= t['sl']:
                        res = "LOSS"

                if res:
                    save_trade(symbol, res, rsi(closes), t['score'])
                    send_msg(f"{'✅' if res=='WIN' else '❌'} {symbol} {res}")
                    del active_trades[symbol]

            else:
                sig, entry, sl, tp, score, prob = strategy(symbol, closes, highs, lows)

                if sig:
                    msg = f"""🔥 {sig} (5M)

💱 {symbol}
💰 Entry: {round(entry,5)}
🛑 SL: {round(sl,5)}
🎯 TP: {round(tp,5)}

⭐ Score: {score}/10
🧠 AI: {prob}%"""

                    send_msg(msg)

                    active_trades[symbol] = {
                        "type": sig,
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "score": score
                    }

        time.sleep(60)

    except Exception as e:
        print("❌ خطأ:", e)
        time.sleep(10)
