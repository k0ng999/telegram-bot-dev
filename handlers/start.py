from telebot.types import Message, BotCommandScopeChat

from commands import COMMANDS_WITHOUT_START, ALL_COMMANDS
from models.user.crud_user import get_user, add_user

# Временное хранилище шагов регистрации
user_states = {}

def register(bot):
    @bot.message_handler(commands=['start'])
    def handle_start(message: Message):
        telegram_id = message.from_user.id
        result = get_user(telegram_id)


        if result:
            bot.set_my_commands(COMMANDS_WITHOUT_START, scope=BotCommandScopeChat(chat_id=message.chat.id))
            bot.send_message(message.chat.id, "Вы уже зарегистрированы!")
        else:
            bot.set_my_commands(ALL_COMMANDS, scope=BotCommandScopeChat(chat_id=message.chat.id))
            bot.send_message(message.chat.id, "Добро пожаловать! Давайте зарегистрируем вас.\nВведите ваше имя:")
            user_states[telegram_id] = {"step": "name"}

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

            # Сохранение в Supabase 
            add_user(
                telegram_id=telegram_id,
                name=state["name"],
                shop_name=state["shop_name"],
                city=state["city"]
            )

            bot.send_message(message.chat.id, f"Регистрация завершена! Добро пожаловать, {state['name']} 👋. Жми на меню снизу!")
            user_states.pop(telegram_id)


    
