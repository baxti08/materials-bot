import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
# Neon adds "channel_binding=require", which asyncpg doesn't understand.
DATABASE_URL = (
    os.environ["DATABASE_URL"]
    .replace("&channel_binding=require", "")
    .replace("channel_binding=require&", "")
)

# Private channel that holds the materials (bot is admin there).
SOURCE_CHAT_ID = int(os.environ.get("SOURCE_CHAT_ID", "-1004399216429"))
# Posts sent to the user, in this order (t.me/c/4399216429/2 and /3).
SOURCE_MESSAGE_IDS = [
    int(x)
    for x in os.environ.get("SOURCE_MESSAGE_IDS", "2,3").split(",")
    if x.strip()
]

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

ADMIN_TELEGRAM_IDS = {
    int(x)
    for x in os.environ.get("ADMIN_TELEGRAM_IDS", "8233724149").split(",")
    if x.strip()
}

REQUIRED_CHANNELS = [
    {"name": "Alisher’s IELTS | 9.0", "username": "alisher_abduvohobov"},
    {"name": "Abdurazzoq Khanov", "username": "Abdurazzoq_Khanov"},
]

ALL_CHANNEL_USERNAMES = {c["username"].lower() for c in REQUIRED_CHANNELS}
