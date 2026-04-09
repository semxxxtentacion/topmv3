import os
from dotenv import load_dotenv
load_dotenv()
# 6906621275:AAFiXmgZ9uez-U9a5FHyNbFQNAt4KSn_EQU. тестовый токен для бота
# 7962163111:AAHDBFyXAYILqVinNOziAONkAnD4dvDDans боевой токен
# ==== Telegram ====

TOKEN = os.getenv("BOT_TOKEN", "6906621275:AAFiXmgZ9uez-U9a5FHyNbFQNAt4KSn_EQU")
ADMIN_CHAT_IDS = [1714559515, 7986806485, 227711554]
# ADMIN_CHAT_IDS = [1369450033]
# ==== PostgreSQL ====
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "top-machine")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "MIIEvQIBADANBg")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ==== Внутренний HTTP-сервер ====
INTERNAL_HOST = os.getenv("INTERNAL_HOST", "0.0.0.0")
INTERNAL_PORT = int(os.getenv("INTERNAL_PORT", 8081))

YANDEX_BOT_URL = os.getenv("YANDEX_BOT_URL", "http://yandex-bot:8082")
YANDEX_BOT_SECRET = os.getenv("YANDEX_BOT_SECRET", "")