from telebot import TeleBot, types
from sqlalchemy.orm import Session
from models.user.models import Seller, TestAttempt, Logs_test
from models.service.models import Tests
from models.user import SessionLocal as UserSessionLocal
from models.service import SessionLocal as ServiceSessionLocal
import json


def register(bot: TeleBot):
    """
    Регистрируем только обработчики, связанные с тестом.
    """

    @bot.callback_query_handler(func=lambda call: call.data in ["start_test", "repeat_wrong"] or call.data.startswith("answer_"))
    def handle_test(call):
        telegram_id = str(call.from_user.id)

        with UserSessionLocal() as user_session:
            seller = user_session.query(Seller).filter_by(telegram_id=telegram_id).first()
            if not seller:
                bot.answer_callback_query(call.id, "❌ Вы не зарегистрированы.")
                return

        last_message_id = call.message.message_id

        # ---- Начало теста ----
        if call.data == "start_test":
            try:
                bot.delete_message(call.message.chat.id, last_message_id)
            except:
                pass

            with UserSessionLocal() as user_session, ServiceSessionLocal() as service_session:
                attempt = user_session.query(TestAttempt).filter_by(seller_id=seller.id).first()
                if attempt:
                    # Сброс предыдущей попытки
                    attempt.correct_answers = 0
                    attempt.wrong_answers = "[]"
                    attempt.current_question_index = 0
                    attempt.finished = False
                else:
                    # Новая попытка
                    attempt = TestAttempt(
                        seller_id=seller.id,
                        name=seller.name,
                        shop_name=seller.shop_name,
                        city=seller.city,
                        correct_answers=0,
                        wrong_answers="[]",
                        current_question_index=0,
                        finished=False
                    )
                    user_session.add(attempt)

                user_session.commit()
                user_session.refresh(attempt)

                # Загружаем вопросы
                questions = service_session.query(Tests).order_by(Tests.test_number.asc()).all()
                if not questions:
                    bot.send_message(call.message.chat.id, "❌ Вопросы для теста не найдены.")
                    return

                # Первый вопрос
                question = questions[0]
                send_question(bot, call.message.chat.id, question, attempt.id)

            bot.answer_callback_query(call.id)
            return

        # ---- Повторение ошибок ----
        if call.data == "repeat_wrong":
            try:
                bot.delete_message(call.message.chat.id, last_message_id)
            except:
                pass

            with UserSessionLocal() as user_session, ServiceSessionLocal() as service_session:
                attempt = user_session.query(TestAttempt).filter_by(seller_id=seller.id).first()
                if not attempt or not attempt.wrong_answers:
                    bot.send_message(call.message.chat.id, "❌ Нет ошибок для повторения.")
                    return

                try:
                    wrong_list = json.loads(attempt.wrong_answers)
                except:
                    wrong_list = []

                wrong_numbers = [wa.get("test_number") for wa in wrong_list if wa.get("test_number")]
                questions = service_session.query(Tests).filter(Tests.test_number.in_(wrong_numbers)).order_by(
                    Tests.test_number.asc()).all()

                if not questions:
                    bot.send_message(call.message.chat.id, "❌ Ошибочные вопросы не найдены.")
                    return

                attempt.finished = False
                user_session.commit()

                # Первый вопрос из списка ошибок
                question = questions[0]
                send_question(bot, call.message.chat.id, question, attempt.id, repeat_mode=True, question_index=0)

            bot.answer_callback_query(call.id)
            return

        # ---- Ответы на вопросы ----
        if call.data.startswith("answer_"):
            process_answer(bot, call, seller, last_message_id)


def send_question(bot: TeleBot, chat_id: int, question, attempt_id: int, repeat_mode: bool = False, question_index: int = 0):
    """
    Отправка вопроса пользователю
    """
    keyboard = types.InlineKeyboardMarkup()
    for i in range(4):
        option_text = question.__dict__.get(f"option_{i}")
        if option_text:
            if repeat_mode:
                callback_data = f"answer_repeat_{attempt_id}_{i}_{question_index}"
            else:
                callback_data = f"answer_{attempt_id}_{i}"
            keyboard.add(types.InlineKeyboardButton(option_text, callback_data=callback_data))

    sent = None
    if getattr(question, "image_urls", None):
        urls = [u.strip() for u in str(question.image_urls).split(",") if u.strip()]
        if urls:
            sent = bot.send_photo(chat_id, urls[0], caption=f"📝 {question.question}", reply_markup=keyboard)
            for url in urls[1:]:
                bot.send_photo(chat_id, url)
    if not sent:
        bot.send_message(chat_id, f"📝 {question.question}", reply_markup=keyboard)


def process_answer(bot: TeleBot, call, seller, last_message_id):
    """
    Обработка ответа пользователя (обычный тест или повторение ошибок)
    """
    parts = call.data.split("_")
    mode = parts[1]

    if mode == "repeat":
        attempt_id = parts[2]
        selected_option = int(parts[3])
        question_index = int(parts[4])
        repeat_mode = True
    else:
        attempt_id = parts[1]
        selected_option = int(parts[2])
        repeat_mode = False

    with UserSessionLocal() as user_session, ServiceSessionLocal() as service_session:
        attempt = user_session.query(TestAttempt).filter_by(id=attempt_id).first()
        if not attempt or attempt.finished:
            bot.answer_callback_query(call.id, "❌ Попытка теста не найдена или завершена.")
            return

        # Определяем текущий вопрос
        if repeat_mode:
            try:
                wrong_list = json.loads(attempt.wrong_answers) if attempt.wrong_answers else []
            except:
                wrong_list = []
            wrong_numbers = [wa.get("test_number") for wa in wrong_list if wa.get("test_number")]
            questions = service_session.query(Tests).filter(Tests.test_number.in_(wrong_numbers)).order_by(
                Tests.test_number.asc()).all()
            current_question = questions[question_index]
        else:
            questions = service_session.query(Tests).order_by(Tests.test_number.asc()).all()
            current_question = questions[attempt.current_question_index]

        wrong_answers = []
        try:
            wrong_answers = json.loads(attempt.wrong_answers) if attempt.wrong_answers else []
        except Exception:
            wrong_answers = []

        correct_index = int(current_question.correct_option_index)

        # ---- Логика ответа ----
        if repeat_mode:
            user_answer_text = current_question.__dict__.get(f"option_{selected_option}") or "—"
            if selected_option == correct_index:
                wrong_answers = [wa for wa in wrong_answers if wa.get("test_number") != current_question.test_number]
            else:
                wrong_answers.append({
                    "test_number": current_question.test_number,
                    "question": current_question.question,
                    "your_answer": user_answer_text
                })
            attempt.wrong_answers = json.dumps(wrong_answers, ensure_ascii=False)
            user_session.commit()
        else:
            if selected_option == correct_index:
                attempt.correct_answers = (attempt.correct_answers or 0) + 1
            else:
                user_answer_text = current_question.__dict__.get(f"option_{selected_option}") or "—"
                wrong_answers.append({
                    "test_number": current_question.test_number,
                    "question": current_question.question,
                    "your_answer": user_answer_text
                })
            attempt.wrong_answers = json.dumps(wrong_answers, ensure_ascii=False)
            attempt.current_question_index += 1
            user_session.commit()

        try:
            bot.delete_message(call.message.chat.id, last_message_id)
        except:
            pass

        # ---- Продолжение ----
        if repeat_mode:
            next_index = question_index + 1
            if next_index >= len(questions):
                if wrong_answers:
                    bot.send_message(
                        call.message.chat.id,
                        "❌ Остались ошибки. 🔄 Повторить ошибки?",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("🔄 Повторить ошибки", callback_data="repeat_wrong")
                        )
                    )
                else:
                    # Отмечаем попытку как завершённую
                    with UserSessionLocal() as user_session_finish:
                        attempt_to_finish = user_session_finish.query(TestAttempt).filter_by(
                            seller_id=seller.id,
                        ).first()
                        if attempt_to_finish:
                            attempt_to_finish.finished = True
                            user_session_finish.commit()

                    bot.send_message(call.message.chat.id, "✅ Все ошибки исправлены!")
                bot.answer_callback_query(call.id)
                return
            else:
                next_question = questions[next_index]
                send_question(bot, call.message.chat.id, next_question, attempt.id, repeat_mode=True,
                              question_index=next_index)
                bot.answer_callback_query(call.id)
                return

        else:  # обычный тест
            if attempt.current_question_index >= len(questions):
                attempt.finished = True
                user_session.commit()

                wrong_texts = (
                    "\n".join([f"❌ {wa['question']}\n➡ Ваш ответ: {wa['your_answer']}" for wa in wrong_answers])
                    if wrong_answers else "🎉 Все ответы верные!"
                )
                result_text = (
                    f"✅ Вы ответили на {attempt.correct_answers} из {len(questions)}\n"
                    f"{wrong_texts}"
                )

                result_keyboard = types.InlineKeyboardMarkup()
                if wrong_answers:
                    result_keyboard.add(types.InlineKeyboardButton("🔄 Повторить ошибки", callback_data="repeat_wrong"))

                bot.send_message(call.message.chat.id, result_text, reply_markup=result_keyboard)
                bot.answer_callback_query(call.id)

                # Логирование
                try:
                    log_entry = Logs_test(
                        seller_id=seller.id,
                        name=seller.name,
                        shop_name=seller.shop_name,
                        city=seller.city,
                        correct_answers=attempt.correct_answers,
                        wrong_answers=json.dumps(wrong_answers, ensure_ascii=False) if wrong_answers else None,
                    )
                    user_session.add(log_entry)
                    user_session.commit()
                except Exception:
                    user_session.rollback()
                return
            else:
                next_question = questions[attempt.current_question_index]
                send_question(bot, call.message.chat.id, next_question, attempt.id)
                bot.answer_callback_query(call.id)
                return
