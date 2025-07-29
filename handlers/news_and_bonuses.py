from telebot.types import Message
from models.service import SessionLocal  # твой sessionmaker
from models.service.models import Bonus  # ORM-класс

def register(bot):
    @bot.message_handler(commands=['news_and_bonuses'])
    def bonuses_handler(message: Message):
        with SessionLocal() as session:
            # ORM-запрос, выбираем только активные бонусы
            bonuses_list = session.query(Bonus).filter(Bonus.active == True).all()

        if not bonuses_list:
            bot.send_message(message.chat.id, "Сейчас нет активных бонусов.")
            return

        texts = []
        for bonus in bonuses_list:
            texts.append(
                f"🎁 *{bonus.name}*\n"
                f"{bonus.description or ''}\n"
                f"Размер: {bonus.amount or '-'}\n"
                f"Условия: {bonus.condition or '-'}\n"
                f"Частота: {bonus.frequency or '-'}\n"
            )

        bot.send_message(message.chat.id, "\n\n".join(texts), parse_mode="Markdown")
