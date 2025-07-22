def register(bot):
    @bot.message_handler(commands=['education'])
    def handle_education(message):
        bot.send_message(message.chat.id, 'Процесс обучения:')
