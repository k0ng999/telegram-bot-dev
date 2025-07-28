from telebot.types import Message
from sqlalchemy import select
from models.service import services_engine  # engine для MaisonBotServices
from models.service.models import bonuses

def register(bot):
    @bot.message_handler(commands=['bonuses'])
    def bonuses_handler(message: Message):
        with services_engine.connect() as conn:
            query = select(bonuses).where(bonuses.c.active == True)
            rows = conn.execute(query).fetchall()

        if not rows:
            bot.send_message(message.chat.id, "Сейчас нет активных бонусов.")
            return

        texts = []
        for row in rows:
            texts.append(
                f"🎁 *{row.name}*\n"
                f"{row.description}\n"
                f"Размер: {row.amount}\n"
                f"Условия: {row.condition}\n"
                f"Частота: {row.frequency}\n"
            )

        bot.send_message(message.chat.id, "\n\n".join(texts), parse_mode="Markdown")
