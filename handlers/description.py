# ---------- Импорт твоей модели ----------
import threading
import time

from telebot import TeleBot
from models.user.models import Seller  # замени на путь к твоей модели
from models.user import SessionLocal as UserSessionLocal

# ---------- Функция для обновления описания ----------
def update_bot_description(bot: TeleBot):
    while True:
        with UserSessionLocal() as session:
            count = session.query(Seller).count()

        bot.set_my_short_description(short_description=f"📊 Сейчас у нас {count} пользователей!")

        # Ждём неделю
        time.sleep(7 * 24 * 60 * 60)


# ---------- Регистрация в боте ----------
def register(bot: TeleBot):
    # Запускаем фоновый поток
    threading.Thread(target=update_bot_description, args=(bot,), daemon=True).start()
