from telebot.types import BotCommandScopeDefault

from commands import ALL_COMMANDS
import os
from dotenv import load_dotenv

import telebot
from handlers import (
    start, support, website, info, catalog, education, stats, faq, news_and_bonuses, get_chat_id, sales_report, get_your_bonuses, description, test
)

from apscheduler.schedulers.background import BackgroundScheduler
import random
import time

from models.user.crud_user import get_all_telegram_ids


load_dotenv()  # загружает переменные из файла .env

TOKEN = os.getenv("TOKEN")

# Инициализация бота
bot = telebot.TeleBot(TOKEN)
# Регистрация обработчиков
start.register(bot)
info.register(bot)
catalog.register(bot)
education.register(bot)
test.register(bot)
stats.register(bot)
news_and_bonuses.register(bot)
website.register(bot)
faq.register(bot)
support.register(bot)
get_chat_id.register(bot)
sales_report.register(bot)
description.register(bot)

get_your_bonuses.register(bot)




bot.set_my_commands(ALL_COMMANDS, scope=BotCommandScopeDefault())

# Мотивационные фразы
MOTIVATIONAL_MESSAGES = [
    "Каждая пара — это твой шаг к бонусу! 🎁👟",
    "Продал больше пар — получил больше бонус! 💸🔥",
    "Чем больше пар в чеке, тем толще твой кошелёк! 💰👠",
    "Не упусти шанс — каждая продажа приближает к цели! 🎯🚀",
    "Клиенту комфорт, тебе — премия! 😍💵",
    "Продвигая лучшие модели, ты поднимаешь свой доход! 📈✨",
    "Ты управляешь своим доходом: продавай активнее! 💪💎",
    "Помни: твоя рекомендация = твоя прибыль! 🗣️💲",
    "Клиент уходит с пакетом, ты — с прибавкой к зарплате! 🛍️😎",
    "Каждая пара обуви — это твой шаг к победе! 🏆👞"
]


# Функция рассылки мотивационных сообщений
def send_motivation():
    user_ids = get_all_telegram_ids()
    message = random.choice(MOTIVATIONAL_MESSAGES)
    for user_id in user_ids:
        try:
            bot.send_message(user_id, message)
        except Exception as e:
            print(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

# Запуск планировщика (понедельник и четверг в 10:00)
scheduler = BackgroundScheduler()
scheduler.add_job(send_motivation, 'cron', day_of_week='mon,thu', hour=10, minute=0)
scheduler.start()

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    bot.remove_webhook()   # <--- вот эта строка нужна!
    while True:
        try:
            bot.infinity_polling()
        except Exception as e:
            print(f"Ошибка в polling: {e}")
            time.sleep(10)