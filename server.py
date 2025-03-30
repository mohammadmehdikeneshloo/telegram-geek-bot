from flask import Flask
import threading
import event_bot_telegram_render_ready

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

if __name__ == '__main__':
    threading.Thread(target=event_bot_telegram_render_ready.run_bot).start()
    app.run(host='0.0.0.0', port=10000)