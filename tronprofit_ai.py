import time
import requests
import hmac
import hashlib
import pandas as pd
import numpy as np
import os
from urllib.parse import urlencode
from dotenv import load_dotenv
from datetime import datetime

# ====== LOAD ENV VARIABLES ======
load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TRADE_SYMBOLS = os.getenv("TRADE_SYMBOLS", "BTCUSDT").split('|')
TRADE_QUANTITY = float(os.getenv("TRADE_QUANTITY", 0.001))
TRADE_LOG_FILE = os.getenv("TRADE_LOG_FILE", "trade_log.csv")
PERFORMANCE_FEE = float(os.getenv("PERFORMANCE_FEE", 0.20))
BASE_URL = 'https://testnet.binance.vision'

# ====== TELEGRAM NOTIFIER ======
def send_telegram_message(message):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        try:
            requests.post(url, data=data)
        except Exception as e:
            print(f"Telegram Error: {e}")

# ====== AI DECISION ENGINE ======
def get_klines(symbol='BTCUSDT', interval='1h', limit=100):
    url = f'{BASE_URL}/api/v3/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    response = requests.get(url, params=params)
    data = response.json()
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                                     'close_time', 'quote_asset_volume', 'num_trades',
                                     'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['close'] = pd.to_numeric(df['close'])
    return df[['timestamp', 'close']]

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_ema(prices, span):
    return prices.ewm(span=span, adjust=False).mean()

def calculate_macd(prices):
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line, signal_line

def ai_decision_engine(symbol):
    df = get_klines(symbol)
    df['RSI'] = calculate_rsi(df['close'])
    df['EMA12'] = calculate_ema(df['close'], 12)
    df['EMA26'] = calculate_ema(df['close'], 26)
    df['MACD'], df['Signal'] = calculate_macd(df['close'])

    latest = df.iloc[-1]
    rsi = latest['RSI']
    ema12 = latest['EMA12']
    ema26 = latest['EMA26']
    macd = latest['MACD']
    signal = latest['Signal']

    if rsi < 30 and ema12 > ema26 and macd > signal:
        return 'BUY'
    elif rsi > 70 and ema12 < ema26 and macd < signal:
        return 'SELL'
    return 'HOLD'

# ====== TRADING EXECUTION ======
def create_signature(query_string, secret):
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

def send_order(symbol, side, quantity):
    path = '/api/v3/order'
    url = BASE_URL + path
    timestamp = int(time.time() * 1000)
    params = {
        'symbol': symbol,
        'side': side,
        'type': 'MARKET',
        'quantity': quantity,
        'timestamp': timestamp
    }
    query_string = urlencode(params)
    signature = create_signature(query_string, API_SECRET)
    headers = {"X-MBX-APIKEY": API_KEY}
    params['signature'] = signature
    response = requests.post(url, headers=headers, params=params)
    return response.json()

# ====== PROFIT TRACKING ======
def log_trade(symbol, trade_type, price):
    timestamp = datetime.utcnow().isoformat()
    entry = f"{timestamp},{symbol},{trade_type},{price}\n"
    with open(TRADE_LOG_FILE, 'a') as f:
        f.write(entry)

def read_last_trade(symbol):
    if not os.path.exists(TRADE_LOG_FILE):
        return None, None
    with open(TRADE_LOG_FILE, 'r') as f:
        lines = [line for line in f.readlines() if symbol in line]
    if not lines:
        return None, None
    last = lines[-1].strip().split(',')
    return last[2], float(last[3])

def calculate_profit(symbol, current_price):
    last_type, last_price = read_last_trade(symbol)
    if last_type == 'BUY':
        profit = (current_price - last_price) * TRADE_QUANTITY
        fee = profit * PERFORMANCE_FEE
        return profit, fee
    elif last_type == 'SELL':
        profit = (last_price - current_price) * TRADE_QUANTITY
        fee = profit * PERFORMANCE_FEE
        return profit, fee
    return 0, 0

# ====== MAIN LOOP ======
def run_bot():
    while True:
        for symbol in TRADE_SYMBOLS:
            decision = ai_decision_engine(symbol)
            current_price = get_klines(symbol).iloc[-1]['close']
            profit, fee = calculate_profit(symbol, current_price)

            message = f"[{symbol}] AI Decision: {decision}\nUnrealized Profit: {profit:.4f} USDT | Fee: {fee:.4f} USDT"
            print(message)
            send_telegram_message(message)

            if decision == 'BUY':
                result = send_order(symbol, 'BUY', TRADE_QUANTITY)
                log_trade(symbol, 'BUY', current_price)
                print(f"Buy Order: {result}")
                send_telegram_message(f"BUY ORDER for {symbol}: {result}")
            elif decision == 'SELL':
                result = send_order(symbol, 'SELL', TRADE_QUANTITY)
                log_trade(symbol, 'SELL', current_price)
                print(f"Sell Order: {result}")
                send_telegram_message(f"SELL ORDER for {symbol}: {result}")
            else:
                print(f"HOLD - No trade for {symbol}.")
        time.sleep(3600)

if __name__ == "__main__":
    run_bot()
