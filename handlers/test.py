from telebot import TeleBot, types
from sqlalchemy.orm import Session
from models.user.models import Seller, TestAttempt, Logs_test
from models.service.models import Tests
from models.user import SessionLocal as UserSessionLocal
from models.service import SessionLocal as ServiceSessionLocal
import json

# Временное хранилище для сообщений с группой фото
photo_group_messages = {}  # ключ: attempt_id, значение: список message_id


def _dedup_keep_last(items):
    """
    Убираем дубликаты по test_number (если его нет — по тексту вопроса),
    оставляем последний ответ.
    """
    seen = {}
    for wa in items:
        key = str(wa.get("test_number") if wa.get("test_number") is not None else wa.get("question"))
        if key:
            seen[key] = {
                "test_number": wa.get("test_number"),
                "question": wa.get("question"),
                "your_answer": wa.get("your_answer"),
            }
    return list(seen.values())


def register(bot: TeleBot):
    """
    Регистрируем только обработчики, связанные с тестом.
    """

    @bot.callback_query_handler(
        func=lambda call: call.data in ["start_test", "repeat_wrong"] or call.data.startswith("answer_")
    )
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
                    attempt.correct_answers = 0
                    attempt.wrong_answers = "[]"
                    attempt.current_question_index = 0
                    attempt.finished = False
                else:
                    attempt = TestAttempt(
                        seller_id=seller.id,
                        name=seller.name,
                        shop_name=seller.shop_name,
                        city=seller.city,
                        correct_answers=0,
                        wrong_answers="[]",
                        current_question_index=0,
                        finished=False,
                    )
                    user_session.add(attempt)

                user_session.commit()
                user_session.refresh(attempt)

                questions = service_session.query(Tests).order_by(Tests.test_number.asc()).all()
                if not questions:
                    bot.send_message(call.message.chat.id, "❌ Вопросы для теста не найдены.")
                    return

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

                wrong_list = _dedup_keep_last(wrong_list)
                wrong_numbers = [wa.get("test_number") for wa in wrong_list if wa.get("test_number")]

                questions = (
                    service_session.query(Tests)
                    .filter(Tests.test_number.in_(wrong_numbers))
                    .order_by(Tests.test_number.asc())
                    .all()
                )

                if not questions:
                    bot.send_message(call.message.chat.id, "❌ Ошибочные вопросы не найдены.")
                    return

                attempt.finished = False
                user_session.commit()

                question = questions[0]
                send_question(bot, call.message.chat.id, question, attempt.id, repeat_mode=True)

            bot.answer_callback_query(call.id)
            return

        # ---- Ответы на вопросы ----
        if call.data.startswith("answer_"):
            process_answer(bot, call, seller, last_message_id)



def send_question(bot: TeleBot, chat_id: int, question, attempt_id: int, repeat_mode: bool = False):
    from models.user import SessionLocal as UserSessionLocal
    from models.service import SessionLocal as ServiceSessionLocal
    import json

    with UserSessionLocal() as user_session, ServiceSessionLocal() as service_session:
        if repeat_mode and question is None:
            # Загружаем attempt и wrong_answers
            attempt = user_session.query(TestAttempt).filter_by(id=attempt_id).first()
            if not attempt:
                bot.send_message(chat_id, "❌ Попытка не найдена.")
                return
            try:
                wrong_answers = json.loads(attempt.wrong_answers) if attempt.wrong_answers else []
            except:
                wrong_answers = []
            wrong_answers = _dedup_keep_last(wrong_answers)
            if not wrong_answers:
                bot.send_message(chat_id, "✅ Все ошибки исправлены!")
                attempt.finished = True
                user_session.commit()
                return

            # Берём первый вопрос из оставшихся wrong_answers
            questions = service_session.query(Tests).order_by(Tests.test_number.asc()).all()
            question = None
            for wa in wrong_answers:
                tn = wa.get("test_number")
                question = next((q for q in questions if q.test_number == tn), None)
                if question:
                    break
            if not question:
                bot.send_message(chat_id, "❌ Ошибочный вопрос не найден.")
                return

        # Формируем клавиатуру
        keyboard = types.InlineKeyboardMarkup()
        for i in range(4):
            option_text = question.__dict__.get(f"option_{i}")
            if option_text:
                callback_data = f"answer_repeat_{attempt_id}_{i}" if repeat_mode else f"answer_{attempt_id}_{i}"
                keyboard.add(types.InlineKeyboardButton(option_text, callback_data=callback_data))

        urls = []
        if getattr(question, "image_urls", None):
            urls = [u.strip() for u in str(question.image_urls).split(",") if u.strip()]

        # Удаляем старую группу фото
        old_ids = photo_group_messages.get(attempt_id, [])
        for msg_id in old_ids:
            try:
                bot.delete_message(chat_id, msg_id)
            except:
                continue
        photo_group_messages[attempt_id] = []

        # Отправка сообщения / фото
        media_group_ids = []
        if urls:
            if len(urls) == 1:
                msg = bot.send_photo(chat_id, urls[0], caption=f"📝 {question.question}", reply_markup=keyboard)
                media_group_ids.append(msg.message_id)
            else:
                media = [types.InputMediaPhoto(media=urls[0], caption=f"📝 {question.question}")]
                for url in urls[1:]:
                    media.append(types.InputMediaPhoto(media=url))
                try:
                    messages = bot.send_media_group(chat_id, media)
                    media_group_ids.extend([m.message_id for m in messages])
                    bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=messages[0].message_id,
                        caption=f"📝 {question.question}",
                        reply_markup=keyboard,
                    )
                except Exception:
                    msg = bot.send_message(chat_id, f"📝 {question.question}", reply_markup=keyboard)
                    media_group_ids.append(msg.message_id)
        else:
            msg = bot.send_message(chat_id, f"📝 {question.question}", reply_markup=keyboard)
            media_group_ids.append(msg.message_id)

        photo_group_messages[attempt_id] = media_group_ids



def process_answer(bot: TeleBot, call, seller, last_message_id):
    parts = call.data.split("_")
    mode = parts[1]

    if mode == "repeat":
        attempt_id = parts[2]
        selected_option = int(parts[3])
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

        questions = service_session.query(Tests).order_by(Tests.test_number.asc()).all()

        try:
            wrong_answers = json.loads(attempt.wrong_answers) if attempt.wrong_answers else []
        except:
            wrong_answers = []

        wrong_answers = _dedup_keep_last(wrong_answers)

        # Определяем текущий вопрос
        if repeat_mode:
            if not wrong_answers:
                bot.answer_callback_query(call.id, "❌ Ошибок для повторения нет.")
                return

            current_question = None
            # Берём первый вопрос из remaining wrong_answers
            for wa in wrong_answers:
                tn = wa.get("test_number")
                current_question = next((q for q in questions if q.test_number == tn), None)
                if current_question:
                    break
            if not current_question:
                bot.answer_callback_query(call.id, "❌ Вопрос не найден.")
                return
        else:
            if attempt.current_question_index >= len(questions):
                bot.answer_callback_query(call.id, "❌ Вопросов больше нет.")
                return
            current_question = questions[attempt.current_question_index]

        # Проверка ответа
        correct_indexes = [int(x.strip()) for x in str(current_question.correct_option_index).split(",") if x.strip().isdigit()]
        tn = getattr(current_question, "test_number", None)
        key = str(tn if tn is not None else current_question.question)
        user_answer_text = current_question.__dict__.get(f"option_{selected_option}") or "—"
        answered_correctly = selected_option in correct_indexes

        # Обновляем wrong_answers
        wrong_answers = [wa for wa in wrong_answers if str(wa.get("test_number") or wa.get("question")) != key]
        if not answered_correctly and not repeat_mode:
            wrong_answers.append({"test_number": tn, "question": current_question.question, "your_answer": user_answer_text})

        attempt.wrong_answers = json.dumps(_dedup_keep_last(wrong_answers), ensure_ascii=False)

        # Обновляем счетчик
        if not repeat_mode and answered_correctly:
            attempt.correct_answers = (attempt.correct_answers or 0) + 1
        if not repeat_mode:
            attempt.current_question_index += 1

        user_session.commit()

        # Удаляем старые сообщения
        try:
            bot.delete_message(call.message.chat.id, last_message_id)
        except:
            pass
        for msg_id in photo_group_messages.get(attempt_id, []):
            try:
                bot.delete_message(call.message.chat.id, msg_id)
            except:
                continue
        photo_group_messages[attempt_id] = []

        # Продолжение
        if repeat_mode:
            key = str(tn if tn is not None else current_question.question)
            
            if answered_correctly:
                # Убираем вопрос из wrong_answers
                wrong_answers = [wa for wa in wrong_answers if str(wa.get("test_number") or wa.get("question")) != key]
            else:
                # Если ответ неправильный, обновляем или добавляем wrong_answers
                updated = False
                for wa in wrong_answers:
                    if str(wa.get("test_number") or wa.get("question")) == key:
                        wa["your_answer"] = user_answer_text
                        updated = True
                        break
                if not updated:
                    wrong_answers.append({"test_number": tn, "question": current_question.question, "your_answer": user_answer_text})
            
            attempt.wrong_answers = json.dumps(_dedup_keep_last(wrong_answers), ensure_ascii=False)
            user_session.commit()
            
            # Проверяем, остались ли вопросы для повторения
            if not wrong_answers:
                attempt.finished = True
                user_session.commit()
                bot.send_message(call.message.chat.id, "✅ Все ошибки исправлены!")
                bot.answer_callback_query(call.id)
                return
            else:
                # Проверяем, остались ли вопросы для следующего показа
                questions_to_repeat = []
                questions_all = service_session.query(Tests).order_by(Tests.test_number.asc()).all()
                for wa in wrong_answers:
                    tn_wa = wa.get("test_number")
                    q = next((q for q in questions_all if q.test_number == tn_wa), None)
                    if q:
                        questions_to_repeat.append(q)
        
                if questions_to_repeat:
                    # Есть вопросы, продолжаем
                    send_question(bot, call.message.chat.id, None, attempt.id, repeat_mode=True)
                else:
                    # Все вопросы показаны, выводим финальный отчёт
                    wrong_texts = "\n".join([f"❌ {wa['question']}\n➡ Ваш ответ: {wa['your_answer']}" for wa in wrong_answers])
                    result_text = f"✅ Тест завершён!\n{wrong_texts}"
                    result_keyboard = types.InlineKeyboardMarkup()
                    result_keyboard.add(types.InlineKeyboardButton("🔄 Повторить тест", callback_data="repeat_wrong"))
                    bot.send_message(call.message.chat.id, result_text, reply_markup=result_keyboard)
                bot.answer_callback_query(call.id)
                return

        else:
            # обычный режим — нормальные вопросы
            if attempt.current_question_index >= len(questions):
                attempt.finished = True
                user_session.commit()
                wrong_answers = _dedup_keep_last(wrong_answers)
                wrong_texts = "\n".join([f"❌ {wa['question']}\n➡ Ваш ответ: {wa['your_answer']}" for wa in wrong_answers]) if wrong_answers else "🎉 Все ответы верные!"
                result_text = f"✅ Вы ответили на {attempt.correct_answers} из {len(questions)}\n{wrong_texts}"
                result_keyboard = types.InlineKeyboardMarkup()
                if wrong_answers:
                    result_keyboard.add(types.InlineKeyboardButton("🔄 Повторить тест", callback_data="repeat_wrong"))
                bot.send_message(call.message.chat.id, result_text, reply_markup=result_keyboard)
                bot.answer_callback_query(call.id)
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
        