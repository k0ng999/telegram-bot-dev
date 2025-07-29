def register(bot):
    @bot.message_handler(commands=['get_chat_id'])
    def handle_me(message):
        bot.send_message(message.chat.id, f"Ваш chat_id: {message.chat.id}")

