def register(bot):
    @bot.message_handler(commands=['stats'])
    def handle_stats(message):
        bot.send_message(message.chat.id, 'Ваша статистика:')
