from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
)
from sqlalchemy import select
from models.user import SessionLocal
from models.user.models import Seller

MANAGER_CHAT_ID = -1002882986486
MANAGER_TOPIC_ID = 21

support_state = {}
pending_support_messages = {}
pending_support_attachments = {}  # chat_id -> list of (type, file_id, bot_msg_id)
manager_messages = {}  # chat_id -> list of msg_ids отправленных менеджеру
delete_buttons_msgs = {}  # chat_id -> list of msg_ids с кнопкой "Удалить"


def register(bot):
    @bot.message_handler(commands=['support'])
    def handle_support(message: Message):
        chat_id = message.chat.id
        support_state[chat_id] = "text"
        pending_support_attachments[chat_id] = []
        manager_messages[chat_id] = []
        delete_buttons_msgs[chat_id] = []

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="support_cancel"))

        bot.send_message(
            chat_id,
            "Опишите ваш вопрос или проблему:",
            reply_markup=markup
        )

    @bot.message_handler(func=lambda msg: support_state.get(msg.chat.id) == "text")
    def handle_support_text(message: Message):
        if message.text.startswith('/'):
            return

        chat_id = message.chat.id
        text = message.text.strip()
        pending_support_messages[chat_id] = text
        support_state[chat_id] = "attachments"

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("📎 Прикрепить вложение", callback_data="support_attach"),
            InlineKeyboardButton("➡️ Продолжить без вложений", callback_data="support_confirm")
        )
        markup.add(InlineKeyboardButton("❌ Отменить обращение", callback_data="support_cancel"))

        sent = bot.send_message(
            chat_id,
            f"Вы написали:\n\n\"{text}\"\n\nХотите прикрепить вложение?",
            reply_markup=markup
        )

        support_state[f"{chat_id}_last_msg_id"] = sent.message_id

    @bot.callback_query_handler(func=lambda call: call.data.startswith("support_"))
    def handle_support_actions(call: CallbackQuery):
        chat_id = call.message.chat.id
        action = call.data.split("_", 1)[1]

        if action == "attach":
            support_state[chat_id] = "waiting_attachments"

            old_msg_id = support_state.get(f"{chat_id}_last_msg_id")
            if old_msg_id:
                try:
                    bot.edit_message_reply_markup(chat_id, old_msg_id, reply_markup=None)
                except:
                    pass

            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("⬅️ Назад", callback_data="support_back_to_confirm"),
                InlineKeyboardButton("✅ Подтвердить", callback_data="support_confirm")
            )

            bot.send_message(
                chat_id,
                "📸 Отправь одно или несколько вложений.\nКогда отправишь все — нажми кнопку ниже.",
                reply_markup=markup
            )

        elif action == "confirm":
            user_text = pending_support_messages.get(chat_id)
            attachments = pending_support_attachments.get(chat_id, [])
            if not user_text:
                bot.answer_callback_query(call.id, "Сообщение не найдено.")
                return

            telegram_id = str(call.from_user.id)

            with SessionLocal() as session:
                seller = session.execute(
                    select(Seller).where(Seller.telegram_id == telegram_id)
                ).scalar_one_or_none()

            if not seller:
                bot.send_message(chat_id, "Вы ещё не зарегистрированы.")
                return

            support_message = (
                f"🔔 Обращение от продавца:\n"
                f"🆔 Telegram ID: {telegram_id} (@{call.from_user.username or 'нет username'})\n"
                f"👤 Имя: {seller.name}\n"
                f"🏪 Магазин: {seller.shop_name}\n"
                f"🏙 Город: {seller.city}\n"
                f"🏦 Банк: {seller.bank_name or '—'}\n"
                f"💳 Карта: {seller.card_number or '—'}\n"
                f"📩 [Открыть чат с продавцом](tg://user?id={telegram_id})\n\n"
                f"💬 Сообщение:\n{user_text}"
            )

            try:
                manager_markup = InlineKeyboardMarkup()
                manager_markup.add(InlineKeyboardButton("✅ Решено", callback_data=f"support_done_{chat_id}"))

                sent_msg = bot.send_message(
                    MANAGER_CHAT_ID,
                    support_message,
                    parse_mode="Markdown",
                    message_thread_id=MANAGER_TOPIC_ID,
                    reply_markup=manager_markup
                )

                manager_messages[chat_id].append(sent_msg.message_id)

                for media_type, file_id, _ in attachments:
                    if media_type == "photo":
                        msg = bot.send_photo(MANAGER_CHAT_ID, file_id, reply_to_message_id=sent_msg.message_id)
                    elif media_type == "video":
                        msg = bot.send_video(MANAGER_CHAT_ID, file_id, reply_to_message_id=sent_msg.message_id)
                    else:
                        continue
                    manager_messages[chat_id].append(msg.message_id)

            except Exception as e:
                print("Ошибка при отправке менеджеру:", e)

            # Удаляем все сообщения с кнопками "Удалить"
            for msg_id in delete_buttons_msgs.get(chat_id, []):
                try:
                    bot.delete_message(chat_id, msg_id)
                except:
                    pass
            delete_buttons_msgs.pop(chat_id, None)

            bot.edit_message_text(
                "Сообщение отправлено менеджеру ✅\nОжидайте ответ в личных сообщениях (НЕ ЗАБУДЬТЕ ОТКРЫТЬ ЛИЧНЫЕ СООБЩЕНИЯ!)",
                chat_id,
                call.message.message_id
            )

            support_state.pop(chat_id, None)
            pending_support_messages.pop(chat_id, None)
            pending_support_attachments.pop(chat_id, None)

        elif action == "back_to_confirm":
            text = pending_support_messages.get(chat_id, "")

            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("📎 Прикрепить вложение", callback_data="support_attach"),
                InlineKeyboardButton("➡️ Продолжить без вложений", callback_data="support_confirm")
            )
            markup.add(InlineKeyboardButton("❌ Отменить обращение", callback_data="support_cancel"))

            bot.send_message(
                chat_id,
                f"Вы написали:\n\n\"{text}\"\n\nХотите прикрепить вложение?",
                reply_markup=markup
            )

            support_state[chat_id] = "attachments"

        elif action == "cancel":
            support_state.pop(chat_id, None)
            pending_support_messages.pop(chat_id, None)
            pending_support_attachments.pop(chat_id, None)
            delete_buttons_msgs.pop(chat_id, None)
            bot.edit_message_text("Обращение отменено ❌", chat_id, call.message.message_id)

        elif action.startswith("done_"):
            target_chat_id = int(action.split("_")[1])
            msg_ids = manager_messages.get(target_chat_id, [])
            for msg_id in msg_ids:
                try:
                    bot.delete_message(MANAGER_CHAT_ID, msg_id)
                except Exception as e:
                    print("Ошибка при удалении:", e)

        elif action.startswith("delete_"):
            parts = action.split("_")
            chat_id = int(parts[1])
            msg_id = int(parts[2])

            if chat_id in pending_support_attachments:
                pending_support_attachments[chat_id] = [
                    att for att in pending_support_attachments[chat_id] if att[2] != msg_id
                ]

            try:
                bot.delete_message(chat_id, msg_id)
            except:
                pass

    @bot.message_handler(
        func=lambda msg: support_state.get(msg.chat.id) == "waiting_attachments",
        content_types=['photo', 'video', 'document', 'audio', 'voice', 'sticker']
    )
    def handle_attachments(message: Message):
        chat_id = message.chat.id
        if support_state.get(chat_id) != "waiting_attachments":
            return

        if message.content_type not in ['photo', 'video']:
            bot.send_message(chat_id, "❌ Разрешены только фото или видео. Попробуйте снова.")
            return

        # Лимит 5 вложений
        if len(pending_support_attachments.get(chat_id, [])) >= 5:
            bot.send_message(chat_id, "❗ Можно прикрепить не более 5 вложений.")
            return

        file_id = (
            message.photo[-1].file_id if message.content_type == 'photo'
            else getattr(message, message.content_type).file_id
        )

        pending_support_attachments[chat_id].append((message.content_type, file_id, message.message_id))

        # Кнопка "Удалить"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🗑 Удалить", callback_data=f"support_delete_{chat_id}_{message.message_id}"))

        sent = bot.send_message(
            chat_id,
            "✅ Вложение добавлено.\nЕсли хотите удалить его — нажмите кнопку ниже.\n\n📨 Чтобы отправить сообщение — нажмите кнопку \"Подтвердить\" выше.",
            reply_markup=markup,
            reply_to_message_id=message.message_id
        )

        # Сохраняем ID сообщения с кнопкой "Удалить", чтобы потом удалить
        delete_buttons_msgs[chat_id].append(sent.message_id)
