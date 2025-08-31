from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from models.user.crud_user import get_user, add_user

# Временное хранилище шагов регистрации
user_states = {}

def register(bot):
    @bot.message_handler(commands=['start'])
    def handle_start(message: Message):
        telegram_id = message.from_user.id
        result = get_user(telegram_id)

        if result:
            bot.send_message(message.chat.id, "Добро пожаловать, 👋. Жми на меню снизу!")
        else:
            bot.send_message(message.chat.id, "Добро пожаловать! Давайте зарегистрируем вас.\nВведите ваше имя:")
            user_states[telegram_id] = {
                "step": "name",
                "username": message.from_user.username or ""
            }

    @bot.message_handler(func=lambda msg: msg.from_user.id in user_states)
    def handle_registration(message: Message):
        telegram_id = message.from_user.id
        state = user_states[telegram_id]

        if state["step"] == "name":
            state["name"] = message.text
            state["step"] = "shop"
            bot.send_message(message.chat.id, "Введите название магазина:")

        elif state["step"] == "shop":
            state["shop_name"] = message.text
            state["step"] = "city"
            bot.send_message(message.chat.id, "Введите ваш город:")

        elif state["step"] == "city":
            state["city"] = message.text
            state["step"] = "confirm"

            # Формируем сообщение с данными
            summary = (
                f"Проверьте данные:\n\n"
                f"👤 Имя: {state['name']}\n"
                f"🏬 Магазин: {state['shop_name']}\n"
                f"🏙 Город: {state['city']}\n\n"
                f"Подтвердить регистрацию?"
            )

            # Кнопки
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{telegram_id}"),
                InlineKeyboardButton("✏️ Изменить", callback_data=f"edit_{telegram_id}")
            )

            bot.send_message(message.chat.id, summary, reply_markup=markup)

    # Обработчик кнопок
    @bot.callback_query_handler(func=lambda call: call.data.startswith(("confirm_", "edit_")))
    def handle_confirmation(call):
        telegram_id = call.from_user.id
        if telegram_id not in user_states:
            bot.answer_callback_query(call.id, "Нет активной регистрации")
            return

        if call.data.startswith("confirm_"):
            state = user_states[telegram_id]

            # Сохраняем в БД
            add_user(
                telegram_id=telegram_id,
                username=state["username"],
                name=state["name"],
                shop_name=state["shop_name"],
                city=state["city"]
            )

            bot.edit_message_text(
                "🎉 Регистрация завершена! Добро пожаловать, 👋. Жми на меню снизу!",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
            user_states.pop(telegram_id)

        elif call.data.startswith("edit_"):
            # Возвращаем на ввод имени
            user_states[telegram_id]["step"] = "name"
            bot.edit_message_text(
                "✏️ Давайте изменим данные. Введите ваше имя:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
