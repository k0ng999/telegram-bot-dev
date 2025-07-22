
from config import TOKEN
import telebot

from handlers import (
    start, support, website, info, catalog, education, stats, photo
)

bot = telebot.TeleBot(TOKEN)


start.register(bot)
support.register(bot)
website.register(bot)
info.register(bot)
catalog.register(bot)
education.register(bot)
stats.register(bot)
photo.register(bot)

if __name__ == '__main__':
    print("Бот запущен...")
    
    bot.infinity_polling()

