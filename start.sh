#!/bin/sh
# One folder, two Railway services:
#   admin-panel        -> the admin website
#   materials-bot      -> the Telegram bot
if [ "$RAILWAY_SERVICE_NAME" = "admin-panel" ]; then
  exec uvicorn admin_panel:app --host 0.0.0.0 --port "${PORT:-8000}"
else
  exec python bot.py
fi
