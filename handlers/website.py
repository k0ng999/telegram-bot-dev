import webbrowser

def register(bot):
    @bot.message_handler(commands=['website'])
    def handle_website(message):
        webbrowser.open('https://maison-dance.ru/')
