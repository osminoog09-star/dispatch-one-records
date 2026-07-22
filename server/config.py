"""Настройки сервера Records. Секреты — из переменных окружения (не в коде)."""
import os

# URL вебхука Discord-канала #уголовные-дела. Пусто = «сухой» режим (постинг логируется, не шлётся).
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Ключ, которым мод авторизуется при отправке дела (POST /api/case).
API_KEY = os.environ.get("RECORDS_API_KEY", "dev-key")

# Название сообщества (для шапки сайта).
COMMUNITY_NAME = os.environ.get("COMMUNITY_NAME", "LAPD")

# Пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")

# Публичный базовый URL сайта (для ссылок/картинок в Discord). Локально:
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
