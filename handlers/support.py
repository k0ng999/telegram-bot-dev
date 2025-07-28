def register(bot):
    @bot.message_handler(commands=['support'])
    def handle_support(message):
        bot.send_message(
            message.chat.id,
            'Связаться с вашим менеджером:\nhttps://t.me/tryhard223'
        )
