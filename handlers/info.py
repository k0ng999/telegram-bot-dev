def register(bot):
    @bot.message_handler(commands=['info'])
    def handle_info(message):
        bot.send_message(message.chat.id, 'Приветственная информация:')
