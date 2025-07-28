from telebot.types import Message
from sqlalchemy import select, func
from models.user import user_engine
from models.user.models import sales_reports

from models.user.crud_user import get_user

def register(bot):
    @bot.message_handler(commands=['stats'])
    def stats_handler(message: Message):
        telegram_id = str(message.from_user.id)

        seller = get_user(telegram_id)
        if not seller:
            bot.send_message(message.chat.id, "Вы не зарегистрированы как продавец.")
            return

        seller_id = seller['id']

        with user_engine.connect() as conn:
            sold_sum_query = select(func.coalesce(func.sum(sales_reports.c.sold_quantity), 0)).where(
                sales_reports.c.seller_id == seller_id,
                sales_reports.c.moderation_passed == True
            )
            total_sold = conn.execute(sold_sum_query).scalar()

        bot.send_message(
            message.chat.id,
            f"За всё время вы продали: {total_sold} пар."
        )
