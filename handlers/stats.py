from telebot.types import Message
from sqlalchemy import select, func
from models.user import SessionLocal
from models.user.models import SalesReport
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

        with SessionLocal() as session:
            sold_sum_query = select(func.coalesce(func.sum(SalesReport.sold_quantity), 0)).where(
                SalesReport.seller_id == seller_id,
                SalesReport.moderation_passed == True
            )
            total_sold = session.execute(sold_sum_query).scalar_one()

        bot.send_message(
            message.chat.id,
            f"За всё время вы продали: {total_sold} пар."
        )
