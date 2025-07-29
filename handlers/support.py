from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
)
from sqlalchemy import select
from models.user import SessionLocal  # сессия ORM
from models.user.models import Seller  # ORM-модель продавца

MANAGER_CHAT_ID = -1002882986486

support_state = {}  # chat_id -> bool
pending_support_messages = {}  # chat_id -> текст


def register(bot):
    @bot.message_handler(commands=['support'])
    def handle_support(message: Message):
        support_state[message.chat.id] = True

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="support_cancel"))

        bot.send_message(
            message.chat.id,
            "Опишите ваш вопрос или проблему:",
            reply_markup=markup
        )

    @bot.message_handler(func=lambda msg: support_state.get(msg.chat.id))
    def handle_support_text(message: Message):
        if message.text.startswith('/'):
            return  # Пропускаем команды

        pending_support_messages[message.chat.id] = message.text.strip()

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Отправить", callback_data="support_confirm"),
            InlineKeyboardButton("✏️ Изменить", callback_data="support_edit"),
        )
        markup.add(InlineKeyboardButton("❌ Отменить обращение", callback_data="support_cancel"))

        bot.send_message(
            message.chat.id,
            f"Вы написали:\n\n\"{message.text.strip()}\"\n\nПодтвердить отправку?",
            reply_markup=markup
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("support_"))
    def handle_support_actions(call: CallbackQuery):
        chat_id = call.message.chat.id
        action = call.data.split("_")[1]

        if action == "confirm":
            user_text = pending_support_messages.get(chat_id)
            if not user_text:
                bot.answer_callback_query(call.id, "Сообщение не найдено.")
                return

            telegram_id = str(call.from_user.id)

            with SessionLocal() as session:
                seller = session.execute(
                    select(Seller).where(Seller.telegram_id == telegram_id)
                ).scalar_one_or_none()

            if seller:
                support_message = (
                    f"🔔 Обращение от продавца:\n"
                    f"🆔 Telegram ID: {telegram_id}\n"
                    f"👤 Имя: {seller.name}\n"
                    f"🏪 Магазин: {seller.shop_name}\n"
                    f"🏙 Город: {seller.city}\n"
                    f"🏦 Банк: {seller.bank_name or '—'}\n"
                    f"💳 Карта: {seller.card_number or '—'}\n"
                    f"📩 [Открыть чат с продавцом](tg://user?id={telegram_id})\n\n"
                    f"💬 Сообщение:\n{user_text}"
                )

                try:
                    bot.send_message(MANAGER_CHAT_ID, support_message, parse_mode="Markdown")
                except Exception as e:
                    print("Ошибка при отправке менеджеру:", e)

                bot.edit_message_text(
                    "Сообщение отправлено менеджеру ✅ Ожидайте ответ в личных сообщениях(НЕ ЗАБУДЬТЕ ОТКРЫТЬ ЛИЧНЫЕ СООБЩЕНИЯ!)",
                    chat_id, call.message.message_id)
            else:
                bot.send_message(chat_id, "Вы ещё не зарегистрированы.")

            support_state.pop(chat_id, None)
            pending_support_messages.pop(chat_id, None)

        elif action == "edit":
            last_text = pending_support_messages.get(chat_id, "")

            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    text="🔁 Вставить предыдущее сообщение",
                    switch_inline_query_current_chat=last_text
                )
            )
            markup.add(
                InlineKeyboardButton("❌ Отменить обращение", callback_data="support_cancel")
            )

            bot.edit_message_text(
                "Введите новое сообщение (можно нажать кнопку ниже 👇):",
                chat_id,
                call.message.message_id,
                reply_markup=markup
            )

            support_state[chat_id] = True

        elif action == "cancel":
            support_state.pop(chat_id, None)
            pending_support_messages.pop(chat_id, None)
            bot.edit_message_text("Обращение отменено ❌", chat_id, call.message.message_id)
