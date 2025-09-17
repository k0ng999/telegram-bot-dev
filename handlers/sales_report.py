from telebot.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, ReplyKeyboardRemove, InputMediaPhoto
)
from telebot import types
from sqlalchemy import select
from datetime import date
from uuid import uuid4
from models.user import SessionLocal
from models.user.models import Seller , SalesReport, SellerStat, TestAttempt
import requests
import threading

MANAGER_CHAT_ID = -1002882986486
MANAGER_TOPIC_ID = 14

IMGDD_API_KEY = '39883788afeda281f6268eb6f182fa0b'
MAX_PHOTO_SIZE_BYTES = 30 * 1024 * 1024  # 30 МБ

# Состояния пользователей
sales_report_state = {}    # { telegram_id: { step, photos, photo_msg_ids, quantity } }
pending_reports = {}       # { report_id: {...} }

def get_exit_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("❌ Выйти из режима", callback_data="sales_exit")
    )
    return markup

def get_photo_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Подтвердить фото", callback_data="sales_confirm_photos"),
        InlineKeyboardButton("❌ Отклонить", callback_data="sales_cancel")
    )
    return markup

def get_delete_photo_keyboard(photo_index):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🗑️ Удалить вложение", callback_data=f"sales_delete_photo|{photo_index}")
    )
    return markup

def register(bot):
    @bot.message_handler(commands=['sales_report'])
    def handle_sales_report(message: Message):
        telegram_id = str(message.from_user.id)
        with SessionLocal() as db:
            seller = db.execute(
                select(Seller).where(Seller.telegram_id == telegram_id)
            ).scalar_one_or_none()
            if not seller:
                bot.send_message(message.chat.id, "❌ Вы ещё не зарегистрированы как продавец.")
                bot.send_message(message.chat.id, "/start")
                return

            exam = db.execute(
                select(TestAttempt)
                .where(TestAttempt.seller_id == seller.id)
            ).scalars().first()
            if not exam or not exam.finished:
                bot.send_message(
                    message.chat.id,
                    "📘 Сначала пройдите обучение, прежде чем отправлять отчёт о продажах."
                )
                bot.send_message(message.chat.id, "/education")
                return

        sales_report_state[telegram_id] = {
            'step': 'await_quantity',
            'photos': [],
            'photo_msg_ids': []
        }
        bot.send_message(
            message.chat.id,
            "📦 Сколько пар обуви ты продал?",
            reply_markup=ReplyKeyboardRemove()
        )
        bot.send_message(
            message.chat.id,
            "Если хотите выйти из режима отчёта — нажмите кнопку ниже.",
            reply_markup=get_exit_keyboard()
        )

    @bot.message_handler(
        func=lambda msg: sales_report_state.get(str(msg.from_user.id), {}).get('step') == 'await_quantity'
    )
    def handle_quantity(message: Message):
        telegram_id = str(message.from_user.id)
        try:
            qty = int(message.text.strip())
            if qty <= 0:
                raise ValueError()
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Введите положительное число.",
                reply_markup=get_exit_keyboard()
            )
            return

        sales_report_state[telegram_id]['quantity'] = qty
        sales_report_state[telegram_id]['step'] = 'await_photos'
        bot.send_message(
            message.chat.id,
            "📸 Отправь одно или несколько фото чеков.\n"
            "Когда отправишь все — нажми кнопку ниже.",
            reply_markup=get_photo_keyboard()
        )

    @bot.message_handler(
        func=lambda msg: sales_report_state.get(str(msg.from_user.id), {}).get('step') == 'await_photos',
        content_types=['photo']
    )
    def handle_photos(message: Message):
        telegram_id = str(message.from_user.id)
        state = sales_report_state.get(telegram_id)
        if not state:
            return

        file_info = bot.get_file(message.photo[-1].file_id)
        if file_info.file_size > MAX_PHOTO_SIZE_BYTES:
            bot.send_message(
                message.chat.id,
                "❌ Это фото слишком большое (>30 МБ)."
            )
            return

        state['photos'].append(message.photo[-1].file_id)
        idx = len(state['photos']) - 1

        sent = bot.send_message(
            message.chat.id,
            "✅ Фото добавлено!\n\n"
            "Чтобы прикрепить ещё, пришлите следующее фото.\n"
            "Чтобы удалить — нажмите кнопку ниже.\n\n"
            "Когда готовы — нажмите «Подтвердить фото» выше.",
            reply_markup=get_delete_photo_keyboard(idx)
        )
        state['photo_msg_ids'].append(sent.message_id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('sales_delete_photo|'))
    def delete_photo_handler(call: CallbackQuery):
        telegram_id = str(call.from_user.id)
        state = sales_report_state.get(telegram_id)
        if not state or state.get('step') != 'await_photos':
            bot.answer_callback_query(call.id, "❌ Нет активного отчёта.")
            return

        _, idx_str = call.data.split('|', 1)
        try:
            idx = int(idx_str)
        except ValueError:
            bot.answer_callback_query(call.id, "❌ Неверные данные.")
            return

        if 0 <= idx < len(state['photos']):
            state['photos'].pop(idx)
            try:
                msg_id = state['photo_msg_ids'].pop(idx)
                bot.delete_message(call.message.chat.id, msg_id)
            except:
                pass
            bot.answer_callback_query(call.id, "🗑️ Фото удалено.")
            bot.send_message(
                call.message.chat.id,
                "📨 Чтобы отправить отчёт — нажмите «✅ Подтвердить фото»."
            )
        else:
            bot.answer_callback_query(call.id, "❌ Фото не найдено.")

    @bot.message_handler(
        func=lambda msg: sales_report_state.get(str(msg.from_user.id), {}).get('step') == 'await_photos',
        content_types=['text', 'video', 'document', 'audio', 'voice', 'sticker', 'location', 'contact']
    )
    def handle_invalid_content(message: Message):
        bot.send_message(message.chat.id, '❌ Прикрепите, пожалуйста, именно фото чеков.\n Если хотите выйти с режима отправки отчета то нажмите кнопку выше "Отклонить"!')

    def retry_upload(bot, call, state, seller, telegram_id, attempt=1):
        MAX_ATTEMPTS = 5
        try:
            image_urls = []
            for file_id in state['photos']:
                fi = bot.get_file(file_id)
                data = bot.download_file(fi.file_path)
                resp = requests.post(
                    'https://api.imgbb.com/1/upload',
                    params={'key': IMGDD_API_KEY},
                    files={'image': data}
                )
                if resp.status_code == 200:
                    image_urls.append(resp.json()['data']['url'])
            if not image_urls:
                raise RuntimeError("No images uploaded")

            qty = state['quantity']
            bonus = qty * 200
            url_str = ",".join(image_urls)

            stub = bot.send_message(
                chat_id=MANAGER_CHAT_ID,
                text="📎 Чеки по отчёту:",
                message_thread_id=MANAGER_TOPIC_ID
            )

            report_id = str(uuid4())[:8]
            pending_reports[report_id] = {
                'telegram_id': telegram_id,
                'quantity': qty,
                'photo_url_str': url_str,
                'manager_chat_id': None,
                'manager_message_id': None,
                'manager_photo_message_ids': [],
                'stub_id': stub.message_id
            }

            media = [InputMediaPhoto(media=u) for u in image_urls[:10]]
            sent_photos = bot.send_media_group(
                chat_id=MANAGER_CHAT_ID,
                media=media,
                reply_to_message_id=stub.message_id
            )
            photo_ids = [m.message_id for m in sent_photos]

            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("✅ Принять", callback_data=f"sales_accept|{report_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"sales_reject|{report_id}")
            )
            sent = bot.send_message(
                chat_id=MANAGER_CHAT_ID,
                text=(
                    f"🧾 Отчёт от @{call.from_user.username or 'no_username'} "
                    f"({call.from_user.id})\n"
                    f"Продано: {qty} пар, бонус {bonus}₽"
                ),
                reply_markup=markup,
                message_thread_id=MANAGER_TOPIC_ID
            )

            pending_reports[report_id].update({
                'manager_chat_id': sent.chat.id,
                'manager_message_id': sent.message_id,
                'manager_photo_message_ids': photo_ids
            })

            for mid in state.get('photo_msg_ids', []):
                try:
                    bot.delete_message(call.message.chat.id, mid)
                except:
                    pass

            bot.send_message(
                call.message.chat.id,
                f"✅ Ваш отчёт отправлен на модерацию. Если одобрят — получите {bonus} бонусов."
            )
            sales_report_state.pop(telegram_id, None)

        except Exception as e:
            if attempt < MAX_ATTEMPTS:
                bot.send_message(
                    call.message.chat.id,
                    f"⚠️ Ошибка загрузки, пробую ещё ({attempt+1}/{MAX_ATTEMPTS})..."
                )
                threading.Timer(
                    2, retry_upload,
                    args=(bot, call, state, seller, telegram_id, attempt+1)
                ).start()
            else:
                bot.send_message(
                    call.message.chat.id,
                    "❌ Не удалось загрузить фото после нескольких попыток."
                )

    @bot.callback_query_handler(func=lambda c: c.data == 'sales_confirm_photos')
    def confirm_photos_handler(call: CallbackQuery):
        telegram_id = str(call.from_user.id)
        state = sales_report_state.get(telegram_id)
        if not state or not state.get('photos'):
            bot.answer_callback_query(call.id, "❌ Фото ещё не прикреплены.")
            return

        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "⏳ Отправляю на модерацию...")
        try:
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
        except:
            pass

        with SessionLocal() as db:
            seller = db.execute(
                select(Seller).where(Seller.telegram_id == telegram_id)
            ).scalar_one()

        threading.Timer(
            0, retry_upload,
            args=(bot, call, state, seller, telegram_id)
        ).start()

    @bot.callback_query_handler(func=lambda c: c.data == 'sales_cancel')
    def cancel_report(call: CallbackQuery):
        telegram_id = str(call.from_user.id)
        sales_report_state.pop(telegram_id, None)
        bot.send_message(
            call.message.chat.id,
            "❌ Отчёт отменён.",
            reply_markup=ReplyKeyboardRemove()
        )
        try:
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
        except:
            pass
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == 'sales_exit')
    def exit_sales_report(call: CallbackQuery):
        telegram_id = str(call.from_user.id)

        if telegram_id in sales_report_state:
            sales_report_state.pop(telegram_id)

        bot.send_message(
            call.message.chat.id,
            "ℹ️ Вы вышли из режима отчёта о продажах.",
            reply_markup=ReplyKeyboardRemove()
        )
        try:
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
        except:
            pass
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('sales_accept|'))
    def handle_accept(call: CallbackQuery):
        _, report_id = call.data.split('|', 1)
        data = pending_reports.get(report_id)
        if not data:
            bot.answer_callback_query(call.id, "⚠️ Запрос не найден.")
            return

        with SessionLocal() as db:
            seller = db.execute(
                select(Seller).where(Seller.telegram_id == data['telegram_id'])
            ).scalar_one()

            new_r = SalesReport(
                seller_id=seller.id,
                name=seller.name,
                shop_name=seller.shop_name,
                city=seller.city,
                report_date=date.today(),
                sold_quantity=data['quantity'],
                receipt_photo_url=data['photo_url_str'],
                moderation_passed=True
            )
            db.add(new_r)

            bonus = data['quantity'] * 200
            st = db.execute(
                select(SellerStat).where(SellerStat.seller_id == seller.id)
            ).scalar_one_or_none()
            if st:

                st.total_sold += data['quantity']
                st.total_bonus += bonus
                st.unpaid_bonus += bonus

            else:
                db.add(SellerStat(
                    seller_id=seller.id,
                    name=seller.name,
                    shop_name=seller.shop_name,
                    city=seller.city,
                    total_sold=data['quantity'],
                    total_bonus=bonus,
                    unpaid_bonus=bonus

                ))
            db.commit()
        bot.send_message(
            int(data['telegram_id']),
            f"🎉"
        )
        bot.send_message(
            int(data['telegram_id']),
            f"Ваш отчёт одобрен! Бонус: {bonus}₽."
        )
        try:
            for pid in data['manager_photo_message_ids']:
                bot.delete_message(data['manager_chat_id'], pid)
            bot.delete_message(data['manager_chat_id'], data['manager_message_id'])
            bot.delete_message(data['manager_chat_id'], data['stub_id'])
        except:
            pass

        pending_reports.pop(report_id, None)
        bot.answer_callback_query(call.id, "✅ Принято.")

    @bot.callback_query_handler(func=lambda c: c.data.startswith('sales_reject|'))
    def handle_reject(call: CallbackQuery):
        _, report_id = call.data.split('|', 1)
        data = pending_reports.get(report_id)
        if not data:
            bot.answer_callback_query(call.id, "⚠️ Запрос не найден.")
            return

        with SessionLocal() as db:
            seller = db.execute(
                select(Seller).where(Seller.telegram_id == data['telegram_id'])
            ).scalar_one()

            # Запись отклонённого отчёта
            new_r = SalesReport(
                seller_id=seller.id,
                name=seller.name,
                shop_name=seller.shop_name,
                city=seller.city,
                report_date=date.today(),
                sold_quantity=data['quantity'],
                receipt_photo_url=data['photo_url_str'],
                moderation_passed=False
            )
            db.add(new_r)
            db.commit()

        # Уведомление пользователя
        bot.send_message(
            int(data['telegram_id']),
            '❌ Отчёт отклонён. Обратитесь в поддержку.'
        )

        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn_support = types.KeyboardButton('/support')
        keyboard.add(btn_support)

        bot.send_message(
            data["telegram_id"],
            'Нажмите кнопку "/support", чтобы связаться с оператором.',
            reply_markup=keyboard
        )

        # Удаление сообщений менеджера
        try:
            for pid in data['manager_photo_message_ids']:
                bot.delete_message(data['manager_chat_id'], pid)
            bot.delete_message(data['manager_chat_id'], data['manager_message_id'])
            bot.delete_message(data['manager_chat_id'], data['stub_id'])
        except:
            pass

        pending_reports.pop(report_id, None)
        bot.answer_callback_query(call.id, "❌ Отклонено.")

