from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select
from datetime import date
from models.user import SessionLocal
from models.user.models import Seller, SalesReport, SellerStat, Payment

withdraw_requests = {}  # Ключ: telegram_id, значение: dict с данными запроса


def register(bot):
    @bot.message_handler(commands=['get_your_bonuses'])
    def get_your_bonuses_handler(message: Message):
        telegram_id = str(message.from_user.id)

        with SessionLocal() as db:
            seller = db.execute(
                select(Seller).where(Seller.telegram_id == telegram_id)
            ).scalar_one_or_none()

            if not seller:
                bot.send_message(message.chat.id, "Вы ещё не зарегистрированы.")
                return

            stat = db.execute(
                select(SellerStat).where(SellerStat.seller_id == seller.id)
            ).scalar_one_or_none()

            if not stat or not stat.unpaid_bonus or stat.unpaid_bonus <= 0:
                bot.send_message(message.chat.id, "У вас нет доступных бонусов для вывода.")
                return

            bot.send_message(
                message.chat.id,
                f"🎉 У вас есть бонусы для вывода: {stat.unpaid_bonus} рублей.\n"
                "Сколько хотите вывести? Введите сумму числом."
            )

            withdraw_requests[telegram_id] = {
                "seller_id": seller.id,
                "step": "waiting_amount",
                "stat": stat,
                "bank_name": seller.bank_name,
                "card_number": seller.card_number,
                "chat_id": message.chat.id,
                "telegram_username": message.from_user.username or "нет",
                "seller_name": seller.name,
                "shop_name": seller.shop_name,
                "city": seller.city,
            }

    @bot.message_handler(func=lambda m: str(m.from_user.id) in withdraw_requests)
    def handle_withdraw_flow(message: Message):
        telegram_id = str(message.from_user.id)
        data = withdraw_requests.get(telegram_id)

        if not data:
            bot.send_message(message.chat.id,
                             "Что-то пошло не так, попробуйте начать заново командой /get_your_bonuses")
            return

        step = data.get("step")

        if step == "waiting_amount":
            try:
                amount = int(message.text.strip())
            except ValueError:
                bot.send_message(message.chat.id, "Введите сумму числом, пожалуйста.")
                return

            if amount <= 0:
                bot.send_message(message.chat.id, "Сумма должна быть положительным числом.")
                return

            if amount > data["stat"].unpaid_bonus:
                bot.send_message(message.chat.id,
                                 f"Вы не можете вывести больше, чем у вас есть: {data['stat'].unpaid_bonus}.")
                return

            data["amount"] = amount

            if data["bank_name"] and data["card_number"]:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("Использовать текущую карту", callback_data="use_old_card"))
                markup.add(InlineKeyboardButton("Ввести новую карту", callback_data="new_card"))
                bot.send_message(message.chat.id,
                                 f"Ваша текущая карта:\n{data['bank_name']} - {data['card_number']}\n"
                                 "Использовать эту карту или ввести новую?",
                                 reply_markup=markup)
                data["step"] = "choose_card"
            else:
                bot.send_message(message.chat.id, "Введите название банка:")
                data["step"] = "waiting_bank_name"

        elif step == "waiting_bank_name":
            data["bank_name"] = message.text.strip()
            bot.send_message(message.chat.id, "Введите номер карты:")
            data["step"] = "waiting_card_number"

        elif step == "waiting_card_number":
            card_number = message.text.strip()
            data["card_number"] = card_number

            bot.send_message(
                message.chat.id,
                f"Вы хотите вывести {data['amount']} рублей на карту:\n"
                f"{data['bank_name']} - {data['card_number']}\n"
                "Подтвердите запрос вывода.",
                reply_markup=confirm_withdraw_markup()
            )
            data["step"] = "confirm_withdraw"

        elif step == "confirm_withdraw":
            bot.send_message(message.chat.id, "Пожалуйста, используйте кнопки ниже для подтверждения.")

    @bot.callback_query_handler(
        func=lambda c: c.data in ["use_old_card", "new_card", "confirm_withdraw_yes", "confirm_withdraw_no"])
    def callback_withdraw_handler(call: CallbackQuery):
        telegram_id = str(call.from_user.id)
        data = withdraw_requests.get(telegram_id)
        if not data:
            bot.answer_callback_query(call.id, "Ошибка: нет активного запроса.")
            return

        if call.data == "use_old_card":
            bot.edit_message_reply_markup(data["chat_id"], call.message.message_id, reply_markup=None)
            bot.send_message(data["chat_id"],
                             f"Вывод {data['amount']} рублей на карту {data['bank_name']} - {data['card_number']}.\n"
                             "Подтвердите запрос.",
                             reply_markup=confirm_withdraw_markup())
            data["step"] = "confirm_withdraw"

        elif call.data == "new_card":
            bot.edit_message_reply_markup(data["chat_id"], call.message.message_id, reply_markup=None)
            bot.send_message(data["chat_id"], "Введите название банка:")
            data["step"] = "waiting_bank_name"

        elif call.data == "confirm_withdraw_yes":
            bot.answer_callback_query(call.id, "Запрос на вывод отправлен администратору.")
            bot.edit_message_reply_markup(data["chat_id"], call.message.message_id, reply_markup=None)

            # Обновляем данные Seller (если была новая карта)
            with SessionLocal() as db:
                seller = db.execute(select(Seller).where(Seller.id == data["seller_id"])).scalar_one()
                seller.bank_name = data["bank_name"]
                seller.card_number = data["card_number"]
                db.commit()

            admin_chat_id = -1002882986486

            # Отправляем запрос админу с подробной информацией
            admin_message_text = (
                "📤 Запрос на вывод\n"
                f"👤 Продавец: {data['seller_name']}\n"
                f"🏪 Магазин: {data['shop_name']}\n"
                f"📍 Город: {data['city']}\n"
                f"💰 Сумма: {data['amount']}₽\n"
                f"💳 Карта: {data['bank_name']} {data['card_number'][:4]}******{data['card_number'][-4:]}\n"
                f"🆔 Telegram: {'@' + data['telegram_username'] if data['telegram_username'] != 'нет' else 'без username'} (ID: {telegram_id})")

            sent_msg = bot.send_message(
                admin_chat_id,
                admin_message_text,
                reply_markup=admin_confirm_markup(telegram_id, data["amount"])
            )

            # Сохраняем message_id админского сообщения для удаления потом
            data["admin_message_id"] = sent_msg.message_id

            # Уведомляем пользователя
            bot.send_message(
                data["chat_id"],
                "⏳ Ваш запрос принят. Ожидайте выплаты, она может прийти в течение 48 часов."
            )

            data["step"] = "waiting_admin"

        elif call.data == "confirm_withdraw_no":
            bot.answer_callback_query(call.id, "Запрос на вывод отменён.")
            bot.edit_message_reply_markup(data["chat_id"], call.message.message_id, reply_markup=None)
            del withdraw_requests[telegram_id]
            bot.send_message(data["chat_id"], "Запрос на вывод отменён.")

    # Кнопки подтверждения и отклонения пользователем
    def confirm_withdraw_markup():
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("Подтвердить", callback_data="confirm_withdraw_yes"),
            InlineKeyboardButton("Отмена", callback_data="confirm_withdraw_no")
        )
        return markup

    # Кнопки для админа
    def admin_confirm_markup(telegram_id, amount):
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(f"✅ Подтвердить ({amount}₽)", callback_data=f"admin_confirm_{telegram_id}_{amount}"),
            InlineKeyboardButton(f"❌ Отклонить ({amount}₽)", callback_data=f"admin_reject_{telegram_id}_{amount}"),
        )
        return markup

    @bot.callback_query_handler(
        func=lambda c: c.data and (c.data.startswith("admin_confirm_") or c.data.startswith("admin_reject_")))
    def admin_response_handler(call: CallbackQuery):
        # Проверка, что сообщение от админа в группе
        if call.message.chat.id != -1002882986486:
            bot.answer_callback_query(call.id, "Это действие доступно только в группе администраторов.")
            return

        data_parts = call.data.split("_")
        action = data_parts[1]  # confirm или reject
        telegram_id = data_parts[2]
        amount = int(data_parts[3])

        if telegram_id not in withdraw_requests:
            bot.answer_callback_query(call.id, "Запрос уже обработан или не найден.")
            return

        req = withdraw_requests[telegram_id]

        with SessionLocal() as db:
            stat = db.execute(
                select(SellerStat).where(SellerStat.seller_id == req["seller_id"])
            ).scalar_one()

            if action == "confirm":
                new_unpaid = (stat.unpaid_bonus or 0) - amount
                if new_unpaid < 0:
                    new_unpaid = 0
                stat.unpaid_bonus = new_unpaid

                payment = Payment(
                    seller_id=req["seller_id"],
                    payment_date=date.today(),
                    amount=amount
                )
                db.add(payment)
                db.commit()

                bot.answer_callback_query(call.id, "Оплата подтверждена.")
                bot.send_message(req["chat_id"], f"✅ Ваш запрос на вывод {amount} рублей выполнен успешно!")

            elif action == "reject":
                bot.answer_callback_query(call.id, "Запрос отклонён.")
                bot.send_message(req["chat_id"], "❌ Ваш запрос отклонён. Обратитесь в поддержку /support.")

            # Удаляем сообщение админа с запросом
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass

            # Удаляем запрос из памяти
            del withdraw_requests[telegram_id]
