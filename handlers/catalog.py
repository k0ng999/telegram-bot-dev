# catalog.py
from telebot import types
from models.catalog.product_search import search_products_by_article, search_products_by_name

CATALOG_URL = "https://maison-dance.ru/catalog/"


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
        bot.answer_callback_query(call.id)

    # Сохраняем текущий режим поиска в память
    user_search_mode = {}

    @bot.callback_query_handler(func=lambda call: call.data in ["search_by_article", "search_by_name"])
    def search_handler(call):
        user_search_mode[call.from_user.id] = call.data
        bot.send_message(call.message.chat.id, "Введите артикул:" if call.data == "search_by_article" else "Введите название:")
        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda message: message.from_user.id in user_search_mode)
    def handle_search_input(message):
        search_mode = user_search_mode.pop(message.from_user.id)  # <-- pop, чтобы удалить режим после одного поиска
        search_term = message.text.strip()

        if search_mode == "search_by_article":
            results = search_products_by_article(search_term)
        else:
            results = search_products_by_name(search_term)

        if not results:
            bot.send_message(message.chat.id, "Ничего не найдено 😔")
        else:
            for item in results:
                image_url = item.get("image_url")

                caption = f"📦 <b>{item['name']}</b>\nАртикул: <code>{item['sku']}</code>"

                if item.get("description"):
                    caption += f"\n\n📝 {item['description']}"

                if image_url:
                    bot.send_photo(
                        message.chat.id,
                        photo=image_url,
                        caption=caption,
                        parse_mode="HTML"
                    )
                else:
                    bot.send_message(
                        message.chat.id,
                        text=caption,
                        parse_mode="HTML"
                    )

        # После вывода результатов предлагать заново выбрать режим поиска
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        btn_by_article = types.InlineKeyboardButton(text="По артикулу", callback_data="search_by_article")
        btn_by_name = types.InlineKeyboardButton(text="По названию", callback_data="search_by_name")
        keyboard.add(btn_by_article, btn_by_name)

        bot.send_message(message.chat.id, "Выберите способ поиска:", reply_markup=keyboard)
