from telebot import TeleBot, types
from datetime import date
import json

from models.service.models import LearningCard
from models.service import SessionLocal as ServiceSessionLocal

from models.user.models import Exam, Seller
from models.user import SessionLocal as UserSessionLocal

# --- Глобальный словарь для хранения ID последних сообщений бота ---
last_bot_messages = {}


def safe_send_message(bot, user_id, text, **kwargs):
    """Отправка текста с сохранением ID"""
    msg = bot.send_message(user_id, text, **kwargs)
    last_bot_messages.setdefault(user_id, []).append(msg.message_id)
    return msg


def safe_send_photo(bot, user_id, photo, **kwargs):
    """Отправка фото с сохранением ID"""
    msg = bot.send_photo(user_id, photo, **kwargs)
    last_bot_messages.setdefault(user_id, []).append(msg.message_id)
    return msg


def safe_send_media_group(bot, user_id, media, **kwargs):
    """Отправка медиа-группы с сохранением ID"""
    msgs = bot.send_media_group(user_id, media, **kwargs)
    for m in msgs:
        last_bot_messages.setdefault(user_id, []).append(m.message_id)
    return msgs


def clear_last_messages(bot, user_id):
    """Удаляет предыдущие сообщения пользователя"""
    if user_id in last_bot_messages:
        for mid in last_bot_messages[user_id]:
            try:
                bot.delete_message(user_id, mid)
            except Exception:
                pass
        last_bot_messages[user_id] = []


def register(bot: TeleBot):
    @bot.message_handler(commands=['education'])
    def cmd_education(message: types.Message):
        user_id = message.from_user.id
        telegram_id = str(user_id)

        with UserSessionLocal() as db:
            seller = db.query(Seller).filter_by(telegram_id=telegram_id).first()
            if not seller:
                bot.send_message(user_id, "🚫 Вы не зарегистрированы как продавец.")
                return

            exam = db.query(Exam).filter_by(seller_id=seller.id).first()

            if exam and exam.end_education:
                keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
                btn_support = types.KeyboardButton('/sales_report')
                keyboard.add(btn_support)

                bot.send_message(
                    user_id,
                    "🎓 Вы успешно завершили обучение и готовы применять полученные знания на практике.\n\n"
                    "Теперь вы можете отправить отчет о продажах, написав команду:\n\n"
                    "`/sales_report`",
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                return

        with ServiceSessionLocal() as db:
            cards = db.query(LearningCard).order_by(LearningCard.card_number).all()
            if not cards:
                bot.send_message(user_id, "Карточек для обучения пока нет.")
                return

        with UserSessionLocal() as db:
            if not exam:
                exam = Exam(
                    seller_id=seller.id,
                    exam_date=date.today(),
                    correct_answers=0,
                    active_question=0,
                    start_education=True,
                    end_education=False,
                    wrong_answers="[]",
                    name=seller.name,
                    shop_name=seller.shop_name,
                    city=seller.city
                )
                db.add(exam)
                db.commit()
                db.refresh(exam)
            else:
                if not exam.start_education:
                    exam.start_education = True
                    exam.end_education = False
                    exam.active_question = 0
                    exam.correct_answers = 0
                    exam.wrong_answers = "[]"
                    db.commit()

            current_index = exam.active_question

        send_learning_card(bot, user_id, cards, current_index)

    # ---------------- ХЕЛПЕРЫ ----------------
    def send_learning_card(bot, user_id, cards, index):
        clear_last_messages(bot, user_id)  # удаляем старые сообщения

        card = cards[index]
        urls = [u.strip() for u in (card.image_urls or "").split(',') if u.strip()]
        if len(urls) > 1:
            safe_send_media_group(bot, user_id, [types.InputMediaPhoto(url) for url in urls])
        elif urls:
            safe_send_photo(bot, user_id, urls[0])

        safe_send_message(bot, user_id, card.lesson_text)

        kb = types.InlineKeyboardMarkup()
        if index > 0:
            kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="prev_card"))
        if index + 1 < len(cards):
            kb.add(types.InlineKeyboardButton("➡️ Далее", callback_data="next_card"))
            safe_send_message(bot, user_id, "Нажмите кнопку, чтобы продолжить обучение 📚", reply_markup=kb)
        else:
            kb.add(types.InlineKeyboardButton("✅ Всё понятно, готов пройти тест", callback_data="start_test"))
            safe_send_photo(bot, user_id, "https://i.ibb.co/JRDxQ7HY/photo-1-2025-08-20-06-30-25.jpg")
            safe_send_message(bot, user_id, "Поздравляю! ты прошел обучение! Мы подготовили небольшой тест, это займет всего пару минут 🕒")
            safe_send_message(bot, user_id, "Нажмите кнопку, чтобы перейти к тесту 📝", reply_markup=kb)
            safe_send_message(bot, user_id, "⚠️ Не выходите из теста, иначе обучение начнётся заново. ⚠️")

    def send_test_question(bot, user_id, cards, index):
        clear_last_messages(bot, user_id)  # удаляем старые сообщения

        card = cards[index]

        urls = [u.strip() for u in (card.test_image_urls or "").split(',') if u.strip()]
        if len(urls) > 1:
            safe_send_media_group(bot, user_id, [types.InputMediaPhoto(url) for url in urls])
        elif urls:
            safe_send_photo(bot, user_id, urls[0])

        options = [opt for opt in [card.option_1, card.option_2, card.option_3, card.option_4] if opt]
        kb = types.InlineKeyboardMarkup(row_width=2)
        for idx, opt in enumerate(options):
            kb.add(types.InlineKeyboardButton(opt, callback_data=f"answer|{idx}"))

        safe_send_message(bot, user_id, card.question, reply_markup=kb)

    # ---------------- КОЛЛБЭКИ ----------------
    @bot.callback_query_handler(func=lambda cq: cq.data == "prev_card")
    def cq_prev_card(cq: types.CallbackQuery):
        user_id = cq.from_user.id
        telegram_id = str(user_id)

        with UserSessionLocal() as db_user, ServiceSessionLocal() as db_service:
            seller = db_user.query(Seller).filter_by(telegram_id=telegram_id).first()
            if not seller:
                bot.answer_callback_query(cq.id, "Вы не зарегистрированы.")
                return

            cards = db_service.query(LearningCard).order_by(LearningCard.card_number).all()
            exam = db_user.query(Exam).filter_by(seller_id=seller.id).first()

            if not exam or not exam.start_education:
                bot.answer_callback_query(cq.id, "Обучение не запущено.")
                return

            if exam.active_question == 0:
                bot.answer_callback_query(cq.id, "Это первая карточка, назад нельзя.")
                return

            exam.active_question -= 1
            exam.active_answer = 0
            db_user.commit()
            current_index = exam.active_question

        bot.answer_callback_query(cq.id)
        send_learning_card(bot, user_id, cards, current_index)

    @bot.callback_query_handler(func=lambda cq: cq.data == "next_card")
    def cq_next_card(cq: types.CallbackQuery):
        user_id = cq.from_user.id
        telegram_id = str(user_id)

        with UserSessionLocal() as db:
            seller = db.query(Seller).filter_by(telegram_id=telegram_id).first()
            if not seller:
                bot.answer_callback_query(cq.id, "Вы не зарегистрированы.")
                return

        with ServiceSessionLocal() as db:
            cards = db.query(LearningCard).order_by(LearningCard.card_number).all()

        with UserSessionLocal() as db:
            exam = db.query(Exam).filter_by(seller_id=seller.id).first()
            if not exam:
                bot.answer_callback_query(cq.id, "Обучение не запущено.")
                return

            if exam.active_question + 1 >= len(cards):
                bot.answer_callback_query(cq.id, "Это последняя карточка.")
                return

            exam.active_question += 1
            db.commit()
            current_index = exam.active_question

        bot.answer_callback_query(cq.id)
        send_learning_card(bot, user_id, cards, current_index)

    @bot.callback_query_handler(func=lambda cq: cq.data == "start_test")
    def cq_start_test(cq: types.CallbackQuery):
        user_id = cq.from_user.id
        telegram_id = str(user_id)

        with UserSessionLocal() as db:
            seller = db.query(Seller).filter_by(telegram_id=telegram_id).first()
            if not seller:
                bot.answer_callback_query(cq.id, "Вы не зарегистрированы.")
                return

            exam = db.query(Exam).filter_by(seller_id=seller.id).first()
            if not exam:
                bot.answer_callback_query(cq.id, "Обучение не запущено.")
                return

            exam.active_question = 0
            exam.correct_answers = 0
            exam.wrong_answers = "[]"
            db.commit()

        with ServiceSessionLocal() as db:
            cards = db.query(LearningCard).order_by(LearningCard.card_number).all()

        bot.answer_callback_query(cq.id)
        send_test_question(bot, user_id, cards, 0)

    @bot.callback_query_handler(func=lambda cq: cq.data and cq.data.startswith("answer|"))
    def cq_answer(cq: types.CallbackQuery):
        user_id = cq.from_user.id
        telegram_id = str(user_id)

        with UserSessionLocal() as db_user, ServiceSessionLocal() as db_service:
            seller = db_user.query(Seller).filter_by(telegram_id=telegram_id).first()
            if not seller:
                bot.answer_callback_query(cq.id, "Вы не зарегистрированы.")
                return

            cards = db_service.query(LearningCard).order_by(LearningCard.card_number).all()
            exam = db_user.query(Exam).filter_by(seller_id=seller.id).first()
            if not exam:
                bot.answer_callback_query(cq.id, "Обучение не запущено.")
                return

            _, sidx = cq.data.split('|')
            selected = int(sidx)
            current_index = exam.active_question

            if current_index >= len(cards):
                bot.answer_callback_query(cq.id, "Тест завершён или произошла ошибка.")
                return

            card = cards[current_index]
            options = [opt for opt in [card.option_1, card.option_2, card.option_3, card.option_4] if opt]

            correct_indexes = [int(x.strip()) for x in str(card.correct_option_index).split(",") if x.strip().isdigit()]

            exam.active_answer = selected
            if selected in correct_indexes:
                exam.correct_answers += 1
            else:
                wrong = {
                    "question": card.question,
                    "correct": ", ".join(options[i] for i in correct_indexes if i < len(options)),
                    "selected": options[selected] if selected < len(options) else "❓"
                }
                wrong_answers = json.loads(exam.wrong_answers or "[]")
                wrong_answers.append(wrong)
                exam.wrong_answers = json.dumps(wrong_answers, ensure_ascii=False)

            exam.active_question += 1
            next_index = exam.active_question

            if next_index >= len(cards):
                exam.active_question = 0
                exam.active_answer = 0
                exam.end_education = (exam.correct_answers == len(cards))

            db_user.commit()
            correct = exam.correct_answers
            total = len(cards)
            wrong_answers = json.loads(exam.wrong_answers or "[]")

        bot.answer_callback_query(cq.id)

        if next_index < total:
            send_test_question(bot, user_id, cards, next_index)
        else:
            clear_last_messages(bot, user_id)  # удаляем старый вопрос с кнопками
            if correct == total:
                safe_send_message(bot, user_id, "🎉 Молодец! Все ответы правильные!")
            else:
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("Начать заново", callback_data="restart_education"))

                message = f"❌ Вы ответили правильно на {correct} из {total} вопросов.\n\nНеправильные ответы:\n\n"
                for i, w in enumerate(wrong_answers, 1):
                    message += (
                        f"❓ *{w['question']}*\n"
                        f"🟥 Ваш ответ: {w['selected']}\n\n"
                    )

                safe_send_message(bot, user_id, message, parse_mode="Markdown", reply_markup=kb)

    @bot.callback_query_handler(func=lambda cq: cq.data == "restart_education")
    def cq_restart_education(cq: types.CallbackQuery):
        user_id = cq.from_user.id
        telegram_id = str(user_id)

        with UserSessionLocal() as db:
            seller = db.query(Seller).filter_by(telegram_id=telegram_id).first()
            if not seller:
                bot.answer_callback_query(cq.id, "Вы не зарегистрированы.")
                return

            exam = db.query(Exam).filter_by(seller_id=seller.id).first()
            if not exam:
                bot.answer_callback_query(cq.id, "Обучение не запущено.")
                return

            exam.start_education = True
            exam.end_education = False
            exam.active_question = 0
            exam.correct_answers = 0
            exam.wrong_answers = "[]"
            db.commit()

        with ServiceSessionLocal() as db:
            cards = db.query(LearningCard).order_by(LearningCard.card_number).all()

        bot.answer_callback_query(cq.id)
        send_learning_card(bot, user_id, cards, 0)
