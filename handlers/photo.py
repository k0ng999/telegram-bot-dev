def register(bot):
    @bot.message_handler(content_types=['photo'])
    def handle_photo(message):
        bot.reply_to(message, 'Супер!')
