import threading
import time
from tronprofit_ai import run_bot
from telegram_notifier import run_telegram_bot

def main():
    print("Starting TronProfit AI bot and Telegram notifier...")

    # Thread for the trading bot
    trading_thread = threading.Thread(target=run_bot)
    trading_thread.daemon = True
    trading_thread.start()

    # Thread for the Telegram notifier
    telegram_thread = threading.Thread(target=run_telegram_bot)
    telegram_thread.daemon = True
    telegram_thread.start()

    # Keep the main thread alive
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
