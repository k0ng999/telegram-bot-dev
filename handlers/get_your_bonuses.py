from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select
from datetime import date
import uuid
from models.user import SessionLocal
from models.user.models import Seller, SellerStat, Payment
from telebot import types

MANAGER_CHAT_ID = -1002882986486
MANAGER_TOPIC_ID = 163

pending_withdrawals = {}  # Ключ: withdraw_id, значение: dict с данными


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

            withdraw_id = str(uuid.uuid4())
            pending_withdrawals[withdraw_id] = {
                "withdraw_id": withdraw_id,
                "seller_id": seller.id,
                "step": "waiting_amount",
                "stat": stat,
                "bank_name": seller.bank_name,
                "card_number": seller.card_number,
                "chat_id": message.chat.id,
                "telegram_id": telegram_id,
                "telegram_username": message.from_user.username or "нет",
                "seller_name": seller.name,
                "shop_name": seller.shop_name,
                "city": seller.city,
                "messages": []
            }

            send_bot_message(bot, withdraw_id,
                             f"🎉 У вас есть бонусы для вывода: {stat.unpaid_bonus} рублей.\n"
                             "Сколько хотите вывести? Введите сумму числом.",
                             cancel_markup(withdraw_id)
                             )

    @bot.message_handler(func=lambda m: any(
        str(m.from_user.id) == data.get("telegram_id") and data.get("step") in {
            "waiting_amount", "waiting_bank_name", "waiting_card_number", "confirm_withdraw", "choose_card"
        } for data in pending_withdrawals.values()
    ))
    def handle_withdraw_flow(message: Message):
        for withdraw_id, data in pending_withdrawals.items():
            if str(message.from_user.id) == data.get("telegram_id") and data.get("step") in {
                "waiting_amount", "waiting_bank_name", "waiting_card_number", "confirm_withdraw", "choose_card"
            }:
                process_withdraw_step(bot, message, withdraw_id, data)
                break


    def process_withdraw_step(bot, message, withdraw_id, data):
        step = data.get("step")

        if message.text.strip().lower() in ["/cancel", "отмена"]:
            cancel_request(bot, data)
            return

        if step == "waiting_amount":
            try:
                amount = int(message.text.strip())
            except ValueError:
                send_bot_message(bot, withdraw_id, "Введите сумму числом, пожалуйста.", cancel_markup(withdraw_id))
                return

            if amount <= 0:
                send_bot_message(bot, withdraw_id, "Сумма должна быть положительным числом.", cancel_markup(withdraw_id))
                return

            if amount > data["stat"].unpaid_bonus:
                send_bot_message(bot, withdraw_id,
                                 f"Вы не можете вывести больше, чем у вас есть: {data['stat'].unpaid_bonus}.",
                                 cancel_markup(withdraw_id))
                return

            data["amount"] = amount

            if data["bank_name"] and data["card_number"]:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("Использовать текущую карту", callback_data=f"use_old_card|{withdraw_id}"))
                markup.add(InlineKeyboardButton("Ввести новую карту", callback_data=f"new_card|{withdraw_id}"))
                markup.add(InlineKeyboardButton("❌ Отменить запрос", callback_data=f"cancel|{withdraw_id}"))

                send_bot_message(bot, withdraw_id,
                                 f"Ваша текущая карта:\nНазвание банка: {data['bank_name']} \nНомер карты: {data['card_number']}\n"
                                 "Использовать эту карту или ввести новую?",
                                 markup)
                data["step"] = "choose_card"
            else:
                send_bot_message(bot, withdraw_id, "Введите название банка:", cancel_markup(withdraw_id))
                data["step"] = "waiting_bank_name"

        elif step == "waiting_bank_name":
            data["bank_name"] = message.text.strip()
            send_bot_message(bot, withdraw_id, "Введите номер карты (12–19 цифр):", cancel_markup(withdraw_id))
            data["step"] = "waiting_card_number"

        elif step == "waiting_card_number":
            card_number = message.text.strip().replace(" ", "")
            if not card_number.isdigit() or not 12 <= len(card_number) <= 19:
                send_bot_message(bot, withdraw_id, "❌ Номер карты должен содержать от 12 до 19 цифр.", cancel_markup(withdraw_id))
                return

            data["card_number"] = card_number
            masked = f"{card_number}"
            send_bot_message(bot, withdraw_id,
                             f"Вы хотите вывести {data['amount']} рублей на карту:\n"
                             f"{data['bank_name']} - {masked}\nПодтвердите запрос вывода.",
                             confirm_withdraw_markup(withdraw_id))
            data["step"] = "confirm_withdraw"


    @bot.callback_query_handler(func=lambda c: True)
    def callback_withdraw_handler(call: CallbackQuery):
        if "|" not in call.data:
            return

        action, withdraw_id = call.data.split("|", 1)
        data = pending_withdrawals.get(withdraw_id)

        if not data:
            bot.answer_callback_query(call.id, "Данный запрос уже обработан или отменён.")
            return

        # --- Пользовательские действия ---
        if action in ["cancel", "use_old_card", "new_card", "confirm"]:
            if action == "cancel":
                cancel_request(bot, data)
                bot.answer_callback_query(call.id, "Запрос отменён.")
                return

            if action == "use_old_card":
                clear_bot_messages(bot, data)
                masked = data['card_number']
                send_bot_message(bot, withdraw_id,
                                 f"Вывод {data['amount']} рублей на карту {data['bank_name']} - {masked}.\n"
                                 "Подтвердите запрос.",
                                 confirm_withdraw_markup(withdraw_id))
                data["step"] = "confirm_withdraw"

            elif action == "new_card":
                clear_bot_messages(bot, data)
                send_bot_message(bot, withdraw_id, "Введите название банка:", cancel_markup(withdraw_id))
                data["step"] = "waiting_bank_name"

            elif action == "confirm":
                clear_bot_messages(bot, data)
                bot.answer_callback_query(call.id, "Запрос отправлен администратору.")

                with SessionLocal() as db:
                    seller = db.execute(
                        select(Seller).where(Seller.id == data["seller_id"])
                    ).scalar_one_or_none()

                    if seller is None:
                        raise ValueError("Seller not found")

                    seller.bank_name = data["bank_name"]
                    seller.card_number = data["card_number"]
                    db.commit()

                admin_text = (
                    "📤 Запрос на вывод\n"
                    f"👤 Продавец: {data['seller_name']}\n"
                    f"🏪 Магазин: {data['shop_name']}\n"
                    f"📍 Город: {data['city']}\n"
                    f"💰 Сумма: {data['amount']}₽\n"
                    f"💳 Карта: {data['bank_name']} {data['card_number']}\n"
                    f"🆔 Telegram: {'@' + data['telegram_username'] if data['telegram_username'] != 'нет' else 'без username'}"
                )

                sent_msg = bot.send_message(
                    chat_id=MANAGER_CHAT_ID,
                    text=admin_text,
                    reply_markup=admin_confirm_markup(withdraw_id),
                    message_thread_id=MANAGER_TOPIC_ID
                )
                data["admin_message_id"] = sent_msg.message_id

                send_bot_message(bot, withdraw_id,
                                 "⏳ Ожидайте поступления средств в течение суток.")

                data["step"] = "waiting_admin"

        # --- Действия администратора ---
        elif action in ["accept", "reject"]:
            if call.message.chat.id != MANAGER_CHAT_ID:
                bot.answer_callback_query(call.id, "Это доступно только администраторам.")
                return

            if action == "reject":
                bot.answer_callback_query(call.id, "Запрос отклонён.")
                send_bot_message(bot, withdraw_id, "❌ Ваш запрос отклонён. Обратитесь в поддержку.")

                keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
                btn_support = types.KeyboardButton('/support')
                keyboard.add(btn_support)

                bot.send_message(
                    data["telegram_id"],
                    'Нажмите кнопку "/support", чтобы связаться с оператором.',
                    reply_markup=keyboard
                )

                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                pending_withdrawals.pop(withdraw_id, None)

            elif action == "accept":
                with SessionLocal() as db:
                    stat = db.execute(
                        select(SellerStat).where(SellerStat.seller_id == data["seller_id"])
                    ).scalar_one()

                    stat.unpaid_bonus = max((stat.unpaid_bonus or 0) - data["amount"], 0)

                    payment = Payment(
                        seller_id=data["seller_id"],
                        payment_date=date.today(),
                        amount=data["amount"],
                        name=data["seller_name"],
                        shop_name=data["shop_name"],
                        city=data["city"],
                    )

                    db.add(payment)
                    db.commit()

                bot.answer_callback_query(call.id, "Оплата подтверждена.")
                send_bot_message(bot, withdraw_id,
                                 f"✅ Ваш запрос на вывод {data['amount']} рублей выполнен успешно!"
                                 )

                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                pending_withdrawals.pop(withdraw_id, None)


    # --- Вспомогательные функции ---
    def send_bot_message(bot, withdraw_id, text, reply_markup=None):
        data = pending_withdrawals.get(withdraw_id)
        if not data:
            return

        # Удаляем предыдущие сообщения
        clear_bot_messages(bot, data)

        msg = bot.send_message(data["chat_id"], text, reply_markup=reply_markup)
        data.setdefault("messages", []).append(msg.message_id)

    def clear_bot_messages(bot, data):
        for msg_id in data.get("messages", []):
            try:
                bot.delete_message(data["chat_id"], msg_id)
            except:
                pass
        data["messages"] = []

    def confirm_withdraw_markup(withdraw_id):
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("Подтвердить", callback_data=f"confirm|{withdraw_id}"),
            InlineKeyboardButton("Отмена", callback_data=f"cancel|{withdraw_id}"),
        )
        return markup

    def admin_confirm_markup(withdraw_id):
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"accept|{withdraw_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject|{withdraw_id}"),
        )
        return markup

    def cancel_markup(withdraw_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❌ Отменить запрос", callback_data=f"cancel|{withdraw_id}"))
        return markup

    def cancel_request(bot, data):
        clear_bot_messages(bot, data)
        bot.send_message(data["chat_id"], "🚫 Запрос на вывод отменён.")
        pending_withdrawals.pop(data.get("withdraw_id", ""), None)
