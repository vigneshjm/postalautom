# postalautom

India Post RD Account Automation API — scrapes RD account data and generates a PDF report.

## Telegram Bot Setup (for CAPTCHA)

The app sends the login CAPTCHA image to your Telegram chat so you can read and reply with the code.

### 1. Create a Telegram Bot
1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts to create a bot
3. Copy the **HTTP API token** (e.g. `123456:ABC-DEF...`)

### 2. Get your Chat ID
1. Message your new bot (send any text like `/start`)
2. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser
3. Find `"chat":{"id": 123456789}` in the response — that number is your Chat ID

### 3. Set environment variables
```bash
export TELEGRAM_BOT_TOKEN="your-bot-token-here"
export TELEGRAM_CHAT_ID="your-chat-id-here"
export INDIA_POST_USER="your-user-id"
export INDIA_POST_PASS="your-password"
```

## Run locally

```bash
pip install -r requirements.txt
playwright install chromium
python main.py
```

Then call `GET http://localhost:8000/generate-report`. The CAPTCHA image will arrive in your Telegram chat — **reply to that message** with the code within 120 seconds.

## Run with Docker

```bash
docker build -t postalautom .
docker run -p 8000:8000 \
  -e TELEGRAM_BOT_TOKEN="..." \
  -e TELEGRAM_CHAT_ID="..." \
  -e INDIA_POST_USER="..." \
  -e INDIA_POST_PASS="..." \
  postalautom
```