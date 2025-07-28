def register(bot):
    @bot.message_handler(commands=['website'])
    def handle_website(message):
        bot.send_message(
            message.chat.id,
            "🌐 Наш сайт: [maison-dance.ru](https://maison-dance.ru/)",
            parse_mode="Markdown"
        )
