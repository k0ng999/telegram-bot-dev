def register(bot):
    @bot.message_handler(commands=['catalog'])
    def handle_education(message):
        bot.send_message(message.chat.id, 'Каталог:')
        
