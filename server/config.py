"""Настройки сервера Records. Секреты — из переменных окружения (не в коде)."""
import os

# Вебхуки Discord по каналам. Пусто = «сухой» режим (не шлётся).
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")            # общий/запасной
DISCORD_WEBHOOK_ARRESTS = os.environ.get("DISCORD_WEBHOOK_ARRESTS", "")    # аресты, суды
DISCORD_WEBHOOK_CITATIONS = os.environ.get("DISCORD_WEBHOOK_CITATIONS", "")  # штрафы, предупреждения
DISCORD_WEBHOOK_CALLOUTS = os.environ.get("DISCORD_WEBHOOK_CALLOUTS", "")  # вызовы
DISCORD_WEBHOOK_CASES = os.environ.get("DISCORD_WEBHOOK_CASES", "")        # дела (досье, итог)
DISCORD_WEBHOOK_SHIFTS = os.environ.get("DISCORD_WEBHOOK_SHIFTS", "")      # рапорты смен


def webhook_for(kind):
    """Возвращает вебхук канала для типа события."""
    if kind in ("citation", "warning"):
        return DISCORD_WEBHOOK_CITATIONS or DISCORD_WEBHOOK_URL
    if kind == "callout":
        return DISCORD_WEBHOOK_CALLOUTS or DISCORD_WEBHOOK_URL
    if kind == "shift":
        return DISCORD_WEBHOOK_SHIFTS or DISCORD_WEBHOOK_URL
    # arrest, court
    return DISCORD_WEBHOOK_ARRESTS or DISCORD_WEBHOOK_URL

# Ключ, которым мод авторизуется при отправке дела (POST /api/case).
API_KEY = os.environ.get("RECORDS_API_KEY", "dev-key")

# Название сообщества (для шапки сайта).
COMMUNITY_NAME = os.environ.get("COMMUNITY_NAME", "LAPD")

# Имя офицера-персонажа по умолчанию (для тест-дел). В реальном моде имя берётся
# из игрового персонажа LSPDFR / из настройки мода.
OFFICER_NAME = os.environ.get("OFFICER_NAME", "Denis Sherman")

# Пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")

# Публичный базовый URL сайта (для ссылок/картинок в Discord). Локально:
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
