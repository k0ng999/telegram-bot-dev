from telebot import TeleBot, types
from sqlalchemy import asc
from models.user.models import Seller, TestAttempt
from models.service.models import LearningCard, LearningBlocks
from models.user import SessionLocal as UserSessionLocal
from models.service import SessionLocal as ServiceSessionLocal

WELCOME_TEXT = (
    "Добро пожаловать в команду Maison!\n"
    "Здесь каждый шаг — это стиль, комфорт и уверенность.\n\n"
    "В этом обучающем блоке ты узнаешь всё, что нужно для отличного старта:\n"
    "об особенностях и ассортименте нашей продукции, маркетинге и продвижении - что поможет тебе легко и уверенно продавать!\n"
    "Наша цель — не просто продавать обувь, а дарить ощущение лёгкости, уверенности и красоты каждому, кто выбирает Maison!"
)


def show_blocks_menu(bot: TeleBot, chat_id):
    """Показывает меню блоков обучения и отдельную кнопку 'Пройти обучение', возвращает список ID сообщений"""
    message_ids = []

    with ServiceSessionLocal() as service_session:
        blocks = service_session.query(LearningBlocks).order_by(asc(LearningBlocks.block_number)).all()

    # Сначала список блоков
    keyboard_blocks = types.InlineKeyboardMarkup()
    for block in blocks:
        keyboard_blocks.add(types.InlineKeyboardButton(block.block_name, callback_data=f"block_{block.block_number}"))
    msg_blocks = bot.send_message(chat_id, "Выберите блок обучения:", reply_markup=keyboard_blocks)
    message_ids.append(msg_blocks.message_id)

    # Отдельная кнопка "Пройти тест"
    if blocks:
        keyboard_start = types.InlineKeyboardMarkup()
        keyboard_start.add(types.InlineKeyboardButton("Пройти тест ✅", callback_data="start_test"))
        msg_start = bot.send_message(
            chat_id,
            "Прошли обучение? Тогда пройдите тест и сможете отправлять отчеты!",
            reply_markup=keyboard_start
        )
        message_ids.append(msg_start.message_id)

    return message_ids


def send_card(bot: TeleBot, chat_id, seller_id, block_number, card_number=1, last_message_ids=None):
    """Отправка карточки конкретного блока, удаляем все предыдущие сообщения перед отправкой"""
    if last_message_ids:
        for msg_id in last_message_ids:
            try:
                bot.delete_message(chat_id, msg_id)
            except:
                pass

    # Проверка, прошёл ли пользователь обучение
    with UserSessionLocal() as user_session:
        finished_attempt = user_session.query(TestAttempt).filter_by(seller_id=seller_id, finished=True).first()
        if finished_attempt:
            keyboard_sales = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            keyboard_sales.add(types.KeyboardButton("/sales_report"))
            bot.send_message(
                chat_id,
                "✅ Вы уже прошли обучение! Теперь вы можете отправить отчет, написав /sales_report.",
                reply_markup=keyboard_sales
            )
            return None

    # Получаем карточки блока
    with ServiceSessionLocal() as service_session:
        cards = service_session.query(LearningCard).filter_by(block=block_number).order_by(asc(LearningCard.card_number)).all()
        if not cards:
            bot.send_message(chat_id, "Карточки для этого блока не найдены ❌")
            return None

        card_number = max(1, min(card_number, len(cards)))
        card = cards[card_number - 1]

    # Кнопки навигации
    is_last_card = card_number == len(cards)
    keyboard = types.InlineKeyboardMarkup()
    if card_number > 1:
        keyboard.add(types.InlineKeyboardButton("⬅ Назад", callback_data=f"card_{block_number}_{card_number-1}"))
    if not is_last_card:
        keyboard.add(types.InlineKeyboardButton("Вперед ➡", callback_data=f"card_{block_number}_{card_number+1}"))
    else:
        keyboard.add(types.InlineKeyboardButton("Завершить блок ➡", callback_data="show_congrats"))

    # Отправка карточки
    if card.image_urls:
        urls = [u.strip() for u in card.image_urls.split(",") if u.strip()]
        msg = bot.send_photo(chat_id, urls[0], caption=f"📚 {card.lesson_text}", reply_markup=keyboard)
        for url in urls[1:]:
            bot.send_photo(chat_id, url)
    else:
        msg = bot.send_message(chat_id, f"📚 {card.lesson_text}", reply_markup=keyboard)

    return msg.message_id


def register(bot: TeleBot):
    """Регистрируем команды и коллбеки для обучения"""

    @bot.message_handler(commands=['education'])
    def handle_education(message):
        telegram_id = str(message.from_user.id)

        with UserSessionLocal() as user_session:
            seller_id = user_session.query(Seller.id).filter_by(telegram_id=telegram_id).scalar()
            if not seller_id:
                bot.send_message(message.chat.id, "❌ Вы не зарегистрированы. Используйте /start")
                return

            finished_attempt = user_session.query(TestAttempt).filter_by(seller_id=seller_id, finished=True).first()
            if finished_attempt:
                keyboard_sales = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                keyboard_sales.add(types.KeyboardButton("/sales_report"))
                bot.send_message(
                    message.chat.id,
                    "✅ Вы уже прошли обучение! Теперь вы можете пройти тест, написав /sales_report.",
                    reply_markup=keyboard_sales
                )
                return

        bot.send_message(message.chat.id, WELCOME_TEXT)
        # Сохраняем ID сообщений для последующего удаления
        bot.user_last_messages = getattr(bot, "user_last_messages", {})
        bot.user_last_messages[telegram_id] = show_blocks_menu(bot, message.chat.id)

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("block_") or call.data.startswith("card_") or
                          call.data == "show_congrats" or call.data.startswith("start_block_")
    )
    def handle_callback(call):
        telegram_id = str(call.from_user.id)

        with UserSessionLocal() as user_session:
            seller_id = user_session.query(Seller.id).filter_by(telegram_id=telegram_id).scalar()
            if not seller_id:
                bot.answer_callback_query(call.id, "❌ Вы не зарегистрированы.")
                return

        last_message_ids = getattr(bot, "user_last_messages", {}).get(telegram_id, [])

        # Кнопка «Пройти обучение» — сразу первая карточка блока
        if call.data.startswith("start_block_"):
            block_number = int(call.data.split("_")[2])
            send_card(bot, call.message.chat.id, seller_id, block_number, card_number=1, last_message_ids=last_message_ids)
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith("block_"):
            block_number = int(call.data.split("_")[1])
            send_card(bot, call.message.chat.id, seller_id, block_number, card_number=1, last_message_ids=last_message_ids)
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith("card_"):
            try:
                _, block_number, card_number = call.data.split("_")
                block_number = int(block_number)
                card_number = int(card_number)
            except:
                bot.answer_callback_query(call.id, "❌ Ошибка данных.")
                return

            send_card(bot, call.message.chat.id, seller_id, block_number, card_number=card_number, last_message_ids=last_message_ids)
            bot.answer_callback_query(call.id)
            return

        if call.data == "show_congrats":
            try:
                for msg_id in last_message_ids:
                    bot.delete_message(call.message.chat.id, msg_id)
            except:
                pass
            bot.send_message(call.message.chat.id, "🎉 Вы завершили блок обучения!")
            # Показываем снова меню блоков
            bot.user_last_messages[telegram_id] = show_blocks_menu(bot, call.message.chat.id)
            bot.answer_callback_query(call.id)
