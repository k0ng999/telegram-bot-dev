from telebot import TeleBot, types
from sqlalchemy.orm import Session
from models.user.models import Seller, TestAttempt, Logs_test
from models.service.models import Tests
from models.user import SessionLocal as UserSessionLocal
from models.service import SessionLocal as ServiceSessionLocal
import json
import uuid
from sqlalchemy import Column, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# Временное хранилище для сообщений с группой фото
photo_group_messages = {}  # ключ: attempt_id, значение: список message_id

# Временное хранилище для текущих выделений (для мультивыбора)
# ключ: f"{attempt_id}_{test_number}" -> set(int)
selection_states = {}


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
    Поддерживаются callback'ы:
     - start_test
     - repeat_wrong
     - answer_{attempt}_{tn}_{i} (как было)
     - answer_repeat_{...}
     - select_{attempt}_{tn}_{i} (toggle для мультивыбора)
     - select_repeat_{...}
     - submit_{attempt}_{tn} (подтвердить мультивыбор)
     - submit_repeat_{...}
     - cancel_{attempt}_{tn} (сброс выбора)
    """

    @bot.callback_query_handler(
        func=lambda call: (
            call.data in ["start_test", "repeat_wrong"]
            or call.data.startswith(("answer_", "select_", "submit_", "cancel_"))
        )
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

        # ---- SELECT (toggle для мультивыбора) ----
        if call.data.startswith("select_"):
            process_select(bot, call, seller, last_message_id)
            return

        # ---- SUBMIT (подтвердить мультивыбор) ----
        if call.data.startswith("submit_"):
            process_submit(bot, call, seller, last_message_id)
            return

        # ---- CANCEL (сброс выбора) ----
        if call.data.startswith("cancel_"):
            process_cancel(bot, call)
            return

        # ---- Ответы на вопросы (одиночный выбор как раньше) ----
        if call.data.startswith("answer_"):
            process_answer(bot, call, seller, last_message_id)
            return


def build_keyboard_for_question(question, attempt_id: int, tn_part: str, repeat_mode: bool, selected_set=None):
    """
    Возвращает InlineKeyboardMarkup для вопроса.
    Если question.correct_option_index содержит >1 индексов — это мультивыбор: кнопки будут
    с callback_data select_... и будет добавлена кнопка submit.
    Для обычного - оставляем answer_... как раньше.
    """
    keyboard = types.InlineKeyboardMarkup()
    correct_indexes = [int(x.strip()) for x in str(question.correct_option_index).split(",") if x.strip().isdigit()]
    multi = len(correct_indexes) > 1
    selected_set = selected_set or set()

    for i in range(4):
        option_text = question.__dict__.get(f"option_{i}")
        if option_text:
            label = option_text
            if multi:
                # показываем чекбокс для выбранных
                if i in selected_set:
                    label = f"✅ {label}"
                else:
                    label = f"▫️ {label}"
                if repeat_mode:
                    callback_data = f"select_repeat_{attempt_id}_{tn_part}_{i}"
                else:
                    callback_data = f"select_{attempt_id}_{tn_part}_{i}"
            else:
                # обычный режим: сохраняем прежнее поведение
                if repeat_mode:
                    callback_data = f"answer_repeat_{attempt_id}_{tn_part}_{i}"
                else:
                    callback_data = f"answer_{attempt_id}_{tn_part}_{i}"
            keyboard.add(types.InlineKeyboardButton(label, callback_data=callback_data))

    if multi:
        # кнопка подтверждения (показывает сколько выбрано)
        req = len(correct_indexes)
        sel_count = len(selected_set)
        if repeat_mode:
            submit_cd = f"submit_repeat_{attempt_id}_{tn_part}"
            cancel_cd = f"cancel_repeat_{attempt_id}_{tn_part}"
        else:
            submit_cd = f"submit_{attempt_id}_{tn_part}"
            cancel_cd = f"cancel_{attempt_id}_{tn_part}"
        # Подтвердить
        keyboard.add(types.InlineKeyboardButton(f"✅ Подтвердить ({sel_count}/{req})", callback_data=submit_cd))
        # Сбросить выбор
        keyboard.add(types.InlineKeyboardButton("⤾ Сбросить выбор", callback_data=cancel_cd))

    return keyboard


def send_question(bot: TeleBot, chat_id: int, question, attempt_id: int, repeat_mode: bool = False):
    from models.user import SessionLocal as UserSessionLocal
    from models.service import SessionLocal as ServiceSessionLocal
    import json

    # при отправке нового вопроса — сбрасываем временный выбор
    tn = getattr(question, "test_number", None)
    tn_part = str(tn) if tn is not None else "0"
    sel_key = f"{attempt_id}_{tn_part}"
    selection_states.pop(sel_key, None)

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

            # Берём первый вопрос из remaining wrong_answers
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

        # Формируем клавиатуру (в callback_data добавляем test_number)
        tn = getattr(question, "test_number", None)
        tn_part = str(tn) if tn is not None else "0"

        # определяем, мультивыбор ли это
        correct_indexes = [int(x.strip()) for x in str(question.correct_option_index).split(",") if x.strip().isdigit()]
        multi = len(correct_indexes) > 1

        # клавиатура (без выбранных еще)
        keyboard = build_keyboard_for_question(question, attempt_id, tn_part, repeat_mode, selected_set=set())

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
                # отправляем группу изображений, а отдельным сообщением — текст + клавиатура
                media = [types.InputMediaPhoto(media=urls[0], caption=f"")]
                for url in urls[1:]:
                    media.append(types.InputMediaPhoto(media=url))
                try:
                    messages = bot.send_media_group(chat_id, media)
                    media_group_ids.extend([m.message_id for m in messages])
                    # отправляем отдельное сообщение с текстом вопроса и клавиатурой (чтобы клавиатура была прикреплена)
                    msg = bot.send_message(chat_id, f"📝 {question.question}", reply_markup=keyboard)
                    media_group_ids.append(msg.message_id)
                except Exception:
                    msg = bot.send_message(chat_id, f"📝 {question.question}", reply_markup=keyboard)
                    media_group_ids.append(msg.message_id)
        else:
            msg = bot.send_message(chat_id, f"📝 {question.question}", reply_markup=keyboard)
            media_group_ids.append(msg.message_id)

        photo_group_messages[attempt_id] = media_group_ids


def process_select(bot: TeleBot, call, seller, last_message_id):
    """
    Переключение вариантов для мультивыбора.
    callback_data:
      select_{attempt_id}_{test_number}_{option_index}
      select_repeat_{attempt_id}_{test_number}_{option_index}
    """
    parts = call.data.split("_")
    try:
        if parts[1] == "repeat":
            if len(parts) < 5:
                bot.answer_callback_query(call.id, "❌ Некорректные данные селекта.")
                return
            attempt_id = parts[2]
            test_number_raw = parts[3]
            selected_option = int(parts[4])
            repeat_mode = True
        else:
            if len(parts) < 4:
                bot.answer_callback_query(call.id, "❌ Некорректные данные селекта.")
                return
            attempt_id = parts[1]
            test_number_raw = parts[2]
            selected_option = int(parts[3])
            repeat_mode = False
    except Exception:
        bot.answer_callback_query(call.id, "❌ Ошибка при разборе селекта.")
        return

    # try to normalize test_number to int if possible
    try:
        test_number = int(test_number_raw)
    except:
        test_number = test_number_raw

    # получаем вопрос из БД, чтобы понять, мульти это или нет, и взять тексты опций
    with ServiceSessionLocal() as service_session:
        question = service_session.query(Tests).filter_by(test_number=test_number).first()

    if not question:
        bot.answer_callback_query(call.id, "❌ Вопрос не найден.")
        return

    correct_indexes = [int(x.strip()) for x in str(question.correct_option_index).split(",") if x.strip().isdigit()]
    multi = len(correct_indexes) > 1

    # Если это не мульти — делегируем на обычный обработчик answer_
    if not multi:
        # преобразуем callback_data в answer_ и передаём в process_answer
        # формируем новый call.data временно
        if repeat_mode:
            call.data = f"answer_repeat_{attempt_id}_{test_number_raw}_{selected_option}"
        else:
            call.data = f"answer_{attempt_id}_{test_number_raw}_{selected_option}"
        process_answer(bot, call, seller, last_message_id)
        return

    # Для мультивыбора — переключаем selection_states
    tn_part = str(test_number) if test_number is not None else "0"
    sel_key = f"{attempt_id}_{tn_part}"
    sel_set = selection_states.get(sel_key, set())

    if selected_option in sel_set:
        sel_set.remove(selected_option)
    else:
        sel_set.add(selected_option)

    selection_states[sel_key] = sel_set

    # пересобираем клавиатуру с учётом выделенных
    keyboard = build_keyboard_for_question(question, attempt_id, tn_part, repeat_mode, selected_set=sel_set)

    # обновляем reply_markup на сообщении (где пользователь нажал)
    try:
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=keyboard)
    except Exception:
        # если не получилось — молча проигнорируем
        pass

    bot.answer_callback_query(call.id)


def process_cancel(bot: TeleBot, call):
    """
    Сброс выбора (cancel_/cancel_repeat_)
    """
    parts = call.data.split("_")
    try:
        if parts[1] == "repeat":
            if len(parts) < 4:
                bot.answer_callback_query(call.id, "❌ Некорректные данные.")
                return
            attempt_id = parts[2]
            test_number_raw = parts[3]
            repeat_mode = True
        else:
            if len(parts) < 3:
                bot.answer_callback_query(call.id, "❌ Некорректные данные.")
                return
            attempt_id = parts[1]
            test_number_raw = parts[2]
            repeat_mode = False
    except Exception:
        bot.answer_callback_query(call.id, "❌ Ошибка при разборе.")
        return

    try:
        test_number = int(test_number_raw)
    except:
        test_number = test_number_raw

    # удаляем состояние
    tn_part = str(test_number) if test_number is not None else "0"
    sel_key = f"{attempt_id}_{tn_part}"
    selection_states.pop(sel_key, None)

    # перестроим клавиатуру пустой (без выделений)
    with ServiceSessionLocal() as service_session:
        question = service_session.query(Tests).filter_by(test_number=test_number).first()
    if not question:
        bot.answer_callback_query(call.id, "❌ Вопрос не найден.")
        return

    keyboard = build_keyboard_for_question(question, attempt_id, tn_part, repeat_mode, selected_set=set())
    try:
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=keyboard)
    except Exception:
        pass

    bot.answer_callback_query(call.id, "Выбор сброшен.")


def process_submit(bot: TeleBot, call, seller, last_message_id):
    """
    Подтверждение выбора для мультивыбора.
    callback_data:
      submit_{attempt_id}_{test_number}
      submit_repeat_{...}
    """
    parts = call.data.split("_")
    try:
        if parts[1] == "repeat":
            if len(parts) < 4:
                bot.answer_callback_query(call.id, "❌ Некорректные данные submit.")
                return
            attempt_id = parts[2]
            test_number_raw = parts[3]
            repeat_mode = True
        else:
            if len(parts) < 3:
                bot.answer_callback_query(call.id, "❌ Некорректные данные submit.")
                return
            attempt_id = parts[1]
            test_number_raw = parts[2]
            repeat_mode = False
    except Exception:
        bot.answer_callback_query(call.id, "❌ Ошибка при разборе submit.")
        return

    try:
        test_number = int(test_number_raw)
    except:
        test_number = test_number_raw

    tn_part = str(test_number) if test_number is not None else "0"
    sel_key = f"{attempt_id}_{tn_part}"
    sel_set = selection_states.get(sel_key, set())

    with UserSessionLocal() as user_session, ServiceSessionLocal() as service_session:
        attempt = user_session.query(TestAttempt).filter_by(id=attempt_id).first()
        if not attempt or attempt.finished:
            bot.answer_callback_query(call.id, "❌ Попытка теста не найдена или завершена.")
            return

        questions = service_session.query(Tests).order_by(Tests.test_number.asc()).all()

        # load persisted wrong_answers
        try:
            stored_wrong = json.loads(attempt.wrong_answers) if attempt.wrong_answers else []
        except:
            stored_wrong = []
        stored_wrong = _dedup_keep_last(stored_wrong)

        # find current question object by test_number (preferred)
        current_question = next((q for q in questions if str(getattr(q, "test_number", "")) == str(test_number)), None)

        # fallback for normal mode: use current index if not found
        if not current_question and not repeat_mode:
            if attempt.current_question_index >= len(questions):
                bot.answer_callback_query(call.id, "❌ Вопросов больше нет.")
                return
            current_question = questions[attempt.current_question_index]

        if not current_question:
            bot.answer_callback_query(call.id, "❌ Вопрос не найден.")
            return

        # Определяем корректные индексы
        correct_indexes = [int(x.strip()) for x in str(current_question.correct_option_index).split(",") if x.strip().isdigit()]
        required_count = len(correct_indexes)

        # Проверяем количество выбранных
        if len(sel_set) != required_count:
            bot.answer_callback_query(call.id, f"Выберите {required_count} вариантов (выбрано {len(sel_set)}).")
            return

        # Составляем текст ответа пользователя
        user_answer_texts = []
        for idx in sorted(list(sel_set)):
            user_answer_texts.append(current_question.__dict__.get(f"option_{idx}") or "—")
        user_answer_text = ", ".join(user_answer_texts)

        answered_correctly = set(sel_set) == set(correct_indexes)

        key = str(getattr(current_question, "test_number", None) if getattr(current_question, "test_number", None) is not None else current_question.question)

        # --- Логика для режима повтора ---
        if repeat_mode:
            # Найти индекс текущего вопроса в stored_wrong (по test_number или по тексту)
            idx = next((i for i, wa in enumerate(stored_wrong)
                        if str(wa.get("test_number") or wa.get("question")) == key), None)

            if idx is None:
                # Если вдруг не найден — безопасно показать следующий имеющийся (или сказать, что нет вопросов)
                if not stored_wrong:
                    attempt.finished = True
                    user_session.commit()
                    bot.send_message(call.message.chat.id, "✅ Все ошибки исправлены!")
                    bot.answer_callback_query(call.id)
                    return
                idx = 0

            # Если ответ верный — удаляем текущий элемент из очереди повторения,
            # если неверный — обновляем его your_answer (оставляем в очереди)
            if answered_correctly:
                del stored_wrong[idx]
                removed = True
            else:
                # обновляем ваш ответ, не перемещая элемент
                stored_wrong[idx]["your_answer"] = user_answer_text
                removed = False

            # Сохраняем оставшиеся вопросы (те, которые ещё нужно пройти в этом повторе)
            attempt.wrong_answers = json.dumps(_dedup_keep_last(stored_wrong), ensure_ascii=False)
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

            # очищаем состояние выбора
            selection_states.pop(sel_key, None)

            # Вычисляем индекс следующего вопроса в очереди повторения
            next_idx = idx if removed else idx + 1

            if next_idx < len(stored_wrong):
                # есть следующий — показываем конкретный следующий вопрос (не снова первый)
                next_tn = stored_wrong[next_idx].get("test_number")
                next_question = next((q for q in questions if q.test_number == next_tn), None)
                if next_question:
                    send_question(bot, call.message.chat.id, next_question, attempt.id, repeat_mode=True)
                    bot.answer_callback_query(call.id)
                    return
                else:
                    # Если нет подходящего вопроса по test_number — продолжаем к следующему элементу
                    pass

            # Если следующего нет — показываем итог повторения
            attempt.finished = True
            user_session.commit()
            wrong_texts = "\n".join([f"❌ {wa['question']}\n➡ Ваш ответ: {wa['your_answer']}" for wa in stored_wrong]) if stored_wrong else "🎉 Все ответы верные!"
            result_text = f"✅ Повторение завершено!\n{wrong_texts}"
            result_keyboard = types.InlineKeyboardMarkup()
            if stored_wrong:
                result_keyboard.add(types.InlineKeyboardButton("🔄 Повторить тест", callback_data="repeat_wrong"))
            bot.send_message(call.message.chat.id, result_text, reply_markup=result_keyboard)
            bot.answer_callback_query(call.id)
            return

        # --- Обычный режим (не repeat) ---
        else:
            # Обновляем wrong_answers (удаляем старую запись для этого вопроса и при ошибке добавляем новую)
            updated_wrong = [wa for wa in stored_wrong if str(wa.get("test_number") or wa.get("question")) != key]
            if not answered_correctly:
                updated_wrong.append({"test_number": current_question.test_number, "question": current_question.question, "your_answer": user_answer_text})

            attempt.wrong_answers = json.dumps(_dedup_keep_last(updated_wrong), ensure_ascii=False)

            # Обновляем счетчик
            if answered_correctly:
                attempt.correct_answers = (attempt.correct_answers or 0) + 1
            attempt.current_question_index = (attempt.current_question_index or 0) + 1

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

            # очищаем состояние выбора
            selection_states.pop(sel_key, None)

            # Продолжаем или завершаем
            total_q = len(questions)
            if attempt.current_question_index >= total_q:
                attempt.finished = True
                user_session.commit()
                wrong_answers_final = _dedup_keep_last(updated_wrong)
                wrong_texts = "\n".join([f"❌ {wa['question']}\n➡ Ваш ответ: {wa['your_answer']}" for wa in wrong_answers_final]) if wrong_answers_final else "🎉 Все ответы верные!"
                result_text = f"✅ Вы ответили на {attempt.correct_answers} из {total_q}\n{wrong_texts}"
                result_keyboard = types.InlineKeyboardMarkup()
                if wrong_answers_final:
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
                        wrong_answers=json.dumps(wrong_answers_final, ensure_ascii=False) if wrong_answers_final else None,
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


def process_answer(bot: TeleBot, call, seller, last_message_id):
    """
    Существующий обработчик одиночного ответа (не мультивыбор).
    Оставлен без изменений (за исключением мелких проверок).
    """
    parts = call.data.split("_")
    # Ожидаемые форматы:
    #  - repeat: answer_repeat_{attempt_id}_{test_number}_{option_index}
    #  - normal: answer_{attempt_id}_{test_number}_{option_index}
    try:
        if parts[1] == "repeat":
            if len(parts) < 5:
                bot.answer_callback_query(call.id, "❌ Некорректные данные ответа.")
                return
            attempt_id = parts[2]
            test_number_raw = parts[3]
            selected_option = int(parts[4])
            repeat_mode = True
        else:
            if len(parts) < 4:
                bot.answer_callback_query(call.id, "❌ Некорректные данные ответа.")
                return
            attempt_id = parts[1]
            test_number_raw = parts[2]
            selected_option = int(parts[3])
            repeat_mode = False
    except Exception:
        bot.answer_callback_query(call.id, "❌ Ошибка при разборе ответа.")
        return

    # try to normalize test_number to int if possible
    try:
        test_number = int(test_number_raw)
    except:
        test_number = test_number_raw

    with UserSessionLocal() as user_session, ServiceSessionLocal() as service_session:
        attempt = user_session.query(TestAttempt).filter_by(id=attempt_id).first()
        if not attempt or attempt.finished:
            bot.answer_callback_query(call.id, "❌ Попытка теста не найдена или завершена.")
            return

        questions = service_session.query(Tests).order_by(Tests.test_number.asc()).all()

        # load persisted wrong_answers
        try:
            stored_wrong = json.loads(attempt.wrong_answers) if attempt.wrong_answers else []
        except:
            stored_wrong = []
        stored_wrong = _dedup_keep_last(stored_wrong)

        # find current question object by test_number (preferred)
        current_question = next((q for q in questions if str(getattr(q, "test_number", "")) == str(test_number)), None)

        # fallback for normal mode: use current index if not found
        if not current_question and not repeat_mode:
            if attempt.current_question_index >= len(questions):
                bot.answer_callback_query(call.id, "❌ Вопросов больше нет.")
                return
            current_question = questions[attempt.current_question_index]

        if not current_question:
            bot.answer_callback_query(call.id, "❌ Вопрос не найден.")
            return

        # Определяем корректные индексы
        correct_indexes = [int(x.strip()) for x in str(current_question.correct_option_index).split(",") if x.strip().isdigit()]
        # Если вдруг correct_indexes >1, пользователю должен был быть показан мультивыбор,
        # но на всякий случай предотвращаем попадание сюда: делаем проверку и перенаправление.
        if len(correct_indexes) > 1:
            # Перенаправляем на мультивыбор: формируем select-колбэк (в качестве toggle)
            # Тут просто проигнорируем и попросим использовать кнопку Подтвердить
            bot.answer_callback_query(call.id, "❗ Этот вопрос требует выбора нескольких вариантов — используйте кнопку 'Подтвердить'.")
            return

        tn = getattr(current_question, "test_number", None)
        key = str(tn if tn is not None else current_question.question)
        user_answer_text = current_question.__dict__.get(f"option_{selected_option}") or "—"
        answered_correctly = selected_option in correct_indexes

        # --- Логика для режима повтора ---
        if repeat_mode:
            # Найти индекс текущего вопроса в stored_wrong (по test_number или по тексту)
            idx = next((i for i, wa in enumerate(stored_wrong)
                        if str(wa.get("test_number") or wa.get("question")) == key), None)

            if idx is None:
                # Если вдруг не найден — безопасно показать следующий имеющийся (или сказать, что нет вопросов)
                if not stored_wrong:
                    attempt.finished = True
                    user_session.commit()
                    bot.send_message(call.message.chat.id, "✅ Все ошибки исправлены!")
                    bot.answer_callback_query(call.id)
                    return
                idx = 0

            # Если ответ верный — удаляем текущий элемент из очереди повторения,
            # если неверный — обновляем его your_answer (оставляем в очереди)
            if answered_correctly:
                del stored_wrong[idx]
                removed = True
            else:
                # обновляем ваш ответ, не перемещая элемент
                stored_wrong[idx]["your_answer"] = user_answer_text
                removed = False

            # Сохраняем оставшиеся вопросы (те, которые ещё нужно пройти в этом повторе)
            attempt.wrong_answers = json.dumps(_dedup_keep_last(stored_wrong), ensure_ascii=False)
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

            # Вычисляем индекс следующего вопроса в очереди повторения
            next_idx = idx if removed else idx + 1

            if next_idx < len(stored_wrong):
                # есть следующий — показываем конкретный следующий вопрос (не снова первый)
                next_tn = stored_wrong[next_idx].get("test_number")
                next_question = next((q for q in questions if q.test_number == next_tn), None)
                if next_question:
                    send_question(bot, call.message.chat.id, next_question, attempt.id, repeat_mode=True)
                    bot.answer_callback_query(call.id)
                    return
                else:
                    # Если нет подходящего вопроса по test_number — продолжаем к следующему элементу
                    pass

            # Если следующего нет — показываем итог повторения
            attempt.finished = True
            user_session.commit()
            wrong_texts = "\n".join([f"❌ {wa['question']}\n➡ Ваш ответ: {wa['your_answer']}" for wa in stored_wrong]) if stored_wrong else "🎉 Все ответы верные!"
            result_text = f"✅ Повторение завершено!\n{wrong_texts}"
            result_keyboard = types.InlineKeyboardMarkup()
            if stored_wrong:
                result_keyboard.add(types.InlineKeyboardButton("🔄 Повторить тест", callback_data="repeat_wrong"))
            bot.send_message(call.message.chat.id, result_text, reply_markup=result_keyboard)
            bot.answer_callback_query(call.id)
            return

        # --- Обычный режим (не repeat) ---
        else:
            # Обновляем wrong_answers (удаляем старую запись для этого вопроса и при ошибке добавляем новую)
            updated_wrong = [wa for wa in stored_wrong if str(wa.get("test_number") or wa.get("question")) != key]
            if not answered_correctly:
                updated_wrong.append({"test_number": tn, "question": current_question.question, "your_answer": user_answer_text})

            attempt.wrong_answers = json.dumps(_dedup_keep_last(updated_wrong), ensure_ascii=False)

            # Обновляем счетчик
            if answered_correctly:
                attempt.correct_answers = (attempt.correct_answers or 0) + 1
            attempt.current_question_index = (attempt.current_question_index or 0) + 1

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

            # Продолжаем или завершаем
            total_q = len(questions)
            if attempt.current_question_index >= total_q:
                attempt.finished = True
                user_session.commit()
                wrong_answers_final = _dedup_keep_last(updated_wrong)
                wrong_texts = "\n".join([f"❌ {wa['question']}\n➡ Ваш ответ: {wa['your_answer']}" for wa in wrong_answers_final]) if wrong_answers_final else "🎉 Все ответы верные!"
                result_text = f"✅ Вы ответили на {attempt.correct_answers} из {total_q}\n{wrong_texts}"
                result_keyboard = types.InlineKeyboardMarkup()
                if wrong_answers_final:
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
                        wrong_answers=json.dumps(wrong_answers_final, ensure_ascii=False) if wrong_answers_final else None,
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
