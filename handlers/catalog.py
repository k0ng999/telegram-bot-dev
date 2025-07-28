from telebot import types

CATALOG_URL = "https://maison-dance.ru/catalog/"  # замени на реальную ссылку

def register(bot):
    @bot.message_handler(commands=['catalog'])
    def catalog_handler(message):
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        btn_site = types.InlineKeyboardButton(text="Смотреть каталог на сайте", url=CATALOG_URL)
        btn_quick_search = types.InlineKeyboardButton(text="Быстрый поиск по артикулу/названию модели обуви", callback_data="quick_search")

        keyboard.add(btn_site, btn_quick_search)
        bot.send_message(message.chat.id, "Выберите действие:", reply_markup=keyboard)


    @bot.callback_query_handler(func=lambda call: call.data == "quick_search")
    def quick_search_menu(call):
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        btn_by_article = types.InlineKeyboardButton(text="По артикулу", callback_data="search_by_article")
        btn_by_name = types.InlineKeyboardButton(text="По названию", callback_data="search_by_name")

        keyboard.add(btn_by_article, btn_by_name)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите способ поиска:",
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id)  # чтобы убрать "часики"


    @bot.callback_query_handler(func=lambda call: call.data in ["search_by_article", "search_by_name"])
    def search_handler(call):
        if call.data == "search_by_article":
            # TODO: здесь будет поиск по артикулу (пока заглушка)
            bot.answer_callback_query(call.id, "Поиск по артикулу пока не реализован.")
        elif call.data == "search_by_name":
            # TODO: здесь будет поиск по названию (пока заглушка)
            bot.answer_callback_query(call.id, "Поиск по названию пока не реализован.")
