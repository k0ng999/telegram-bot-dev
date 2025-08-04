from telebot.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove, InputMediaPhoto
)
from sqlalchemy import select
from datetime import date
from uuid import uuid4
from models.user import SessionLocal
from models.user.models import Seller, Exam, SalesReport, SellerStat
import requests

MANAGER_CHAT_ID = -1002882986486    # ID супергруппы
MANAGER_TOPIC_ID = 14            # ID темы форума (topic)

IMGDD_API_KEY = '39883788afeda281f6268eb6f182fa0b'

sales_report_state = {}
pending_reports = {}


def register(bot):
    def get_exit_keyboard():
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❌ Выйти из режима", callback_data="exit_sales_report"))
        return markup

    def get_photo_keyboard():
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Подтвердить фото", callback_data="confirm_photos"),
            InlineKeyboardButton("❌ Отклонить", callback_data="cancel_report")
        )
        return markup

    @bot.message_handler(commands=['sales_report'])
    def handle_sales_report(message: Message):
        telegram_id = str(message.from_user.id)

        with SessionLocal() as db:
            seller = db.execute(select(Seller).where(Seller.telegram_id == telegram_id)).scalar_one_or_none()
            if not seller:
                bot.send_message(message.chat.id, "❌ Вы ещё не зарегистрированы как продавец.")
                bot.send_message(message.chat.id, "/start")
                return

            exam = db.execute(
                select(Exam).where(Exam.seller_id == seller.id).order_by(Exam.exam_date.desc())
            ).scalars().first()

            if not exam or not exam.end_education:
                bot.send_message(message.chat.id, "📘 Сначала пройдите обучение, прежде чем отправлять отчёт о продажах.")
                bot.send_message(message.chat.id, "/education")
                return

        sales_report_state[telegram_id] = {'step': 'await_quantity', 'photos': []}
        bot.send_message(message.chat.id, "📦 Сколько пар обуви ты продал?", reply_markup=ReplyKeyboardRemove())
        bot.send_message(message.chat.id, "Если хотите выйти из режима отчёта — нажмите кнопку ниже.",
                         reply_markup=get_exit_keyboard())

    @bot.message_handler(func=lambda msg: sales_report_state.get(str(msg.from_user.id), {}).get('step') == 'await_quantity')
    def handle_quantity(message: Message):
        telegram_id = str(message.from_user.id)
        try:
            quantity = int(message.text.strip())
            if quantity <= 0:
                raise ValueError()
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите положительное число.", reply_markup=get_exit_keyboard())
            return

        sales_report_state[telegram_id]['quantity'] = quantity
        sales_report_state[telegram_id]['step'] = 'await_photos'
        bot.send_message(message.chat.id, "📸 Отправь одно или несколько фото чеков.\nКогда отправишь все — нажми кнопку ниже.",
                         reply_markup=get_photo_keyboard())

    @bot.message_handler(content_types=['photo'])
    def handle_photos(message: Message):
        telegram_id = str(message.from_user.id)
        state = sales_report_state.get(telegram_id)
        if not state or state.get('step') != 'await_photos':
            return

        # Сохраняем file_id
        state['photos'].append(message.photo[-1].file_id)

        bot.send_message(message.chat.id, "✅ Фото добавлено. Нажмите кнопку выше для отправки отчёта. Или прикрепи ещё фото")

    @bot.message_handler(
        content_types=['text', 'video', 'document', 'audio', 'voice', 'sticker', 'location', 'contact'])
    def handle_invalid_content(message: Message):
        telegram_id = str(message.from_user.id)
        state = sales_report_state.get(telegram_id)
        if state and state.get('step') == 'await_photos':
            bot.send_message(message.chat.id, "❌ Пожалуйста, прикрепите именно фото. Попробуйте ещё раз.")

    @bot.callback_query_handler(func=lambda call: call.data == 'confirm_photos')
    def confirm_photos_handler(call: CallbackQuery):
        telegram_id = str(call.from_user.id)
        state = sales_report_state.get(telegram_id)
        if not state or not state.get('photos'):
            bot.answer_callback_query(call.id, "❌ Вы ещё не прикрепили фото.")
            return

        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "⏳ Загружаю фото и отправляю на модерацию...")

        # Убираем кнопки из сообщения с кнопками подтверждения
        try:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        except Exception:
            pass

        image_urls = []

        for file_id in state['photos']:
            file_info = bot.get_file(file_id)
            file_data = bot.download_file(file_info.file_path)

            response = requests.post(
                'https://api.imgbb.com/1/upload',
                params={'key': IMGDD_API_KEY},
                files={'image': file_data}
            )

            if response.status_code == 200:
                image_urls.append(response.json()['data']['url'])

        if not image_urls:
            bot.send_message(call.message.chat.id, "❌ Не удалось загрузить ни одно фото.")
            return

        with SessionLocal() as db:
            seller = db.execute(select(Seller).where(Seller.telegram_id == telegram_id)).scalar_one()

        quantity = state['quantity']
        bonus = quantity * 200
        image_url_str = ",".join(image_urls)

        congrat_text = f"🎉 Поздравляю, твой бонус за эти продажи: {bonus}₽!\n"
        congrat_text += "Уже завтра ты можешь получить свои бонусы (отчёт проходит модерацию!)"
        if quantity > 10:
            congrat_text += "\n🔥 Вот это круто!"
        elif quantity > 5:
            congrat_text += "\n👍 Классный результат!"

        report_id = str(uuid4())[:8]
        pending_reports[report_id] = {
            'telegram_id': telegram_id,
            'quantity': quantity,
            'photo_urls': image_urls,
            'photo_url_str': image_url_str,
            'manager_chat_id': None,
            'manager_message_id': None,
            'manager_photo_message_ids': []
        }

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Принять", callback_data=f"accept|{report_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject|{report_id}")
        )

        # Отправляем фото в чат менеджера и сохраняем ID сообщений для удаления позже
        media_group = [InputMediaPhoto(media=url) for url in image_urls[:10]]  # максимум 10
        sent_photos = bot.send_media_group(MANAGER_CHAT_ID, media_group)
        photo_message_ids = [msg.message_id for msg in sent_photos]

        sent_msg = bot.send_message(
            chat_id=MANAGER_CHAT_ID,
            text=(f"🧾 Отчёт от {seller.name} (@{call.from_user.username or 'нет username'})\n"
                  f"Магазин: {seller.shop_name}\n"
                  f"Город: {seller.city}\n"
                  f"Продано пар: {quantity}\n"
                  f"Бонус: {bonus}₽"),
            reply_markup=markup,
            message_thread_id=MANAGER_TOPIC_ID
        )

        pending_reports[report_id]['manager_chat_id'] = sent_msg.chat.id
        pending_reports[report_id]['manager_message_id'] = sent_msg.message_id
        pending_reports[report_id]['manager_photo_message_ids'] = photo_message_ids

        bot.send_message(call.message.chat.id, congrat_text)
        del sales_report_state[telegram_id]

    @bot.callback_query_handler(func=lambda call: call.data == 'cancel_report')
    def cancel_report(call: CallbackQuery):
        telegram_id = str(call.from_user.id)
        sales_report_state.pop(telegram_id, None)
        bot.send_message(call.message.chat.id, "❌ Отчёт отменён.", reply_markup=ReplyKeyboardRemove())
        bot.answer_callback_query(call.id)

        # Убираем кнопки из сообщения с кнопками отмены
        try:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        except Exception:
            pass

    @bot.callback_query_handler(func=lambda call: call.data == 'exit_sales_report')
    def exit_sales_report(call: CallbackQuery):
        telegram_id = str(call.from_user.id)
        sales_report_state.pop(telegram_id, None)
        bot.send_message(call.message.chat.id, "ℹ️ Вы вышли из режима отчёта о продажах.",
                         reply_markup=ReplyKeyboardRemove())

        # Убираем кнопки из сообщения с кнопкой выхода из режима
        try:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        except Exception:
            pass

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('accept|'))
    def handle_accept(call: CallbackQuery):
        _, report_id = call.data.split('|')
        data = pending_reports.get(report_id)
        if not data:
            bot.answer_callback_query(call.id, "⚠️ Истекло или не найдено.")
            return

        with SessionLocal() as db:
            seller = db.execute(select(Seller).where(Seller.telegram_id == data['telegram_id'])).scalar_one()
            new_report = SalesReport(
                seller_id=seller.id,
                report_date=date.today(),
                sold_quantity=data['quantity'],
                receipt_photo_url=data['photo_url_str'],
                moderation_passed=True
            )
            db.add(new_report)

            bonus = data['quantity'] * 200
            seller_stat = db.execute(select(SellerStat).where(SellerStat.seller_id == seller.id)).scalar_one_or_none()

            if seller_stat:
                seller_stat.total_sold = (seller_stat.total_sold or 0) + data['quantity']
                seller_stat.total_bonus = (seller_stat.total_bonus or 0) + bonus
                seller_stat.unpaid_bonus = (seller_stat.unpaid_bonus or 0) + bonus
            else:
                seller_stat = SellerStat(
                    seller_id=seller.id,
                    total_sold=data['quantity'],
                    total_bonus=bonus,
                    unpaid_bonus=bonus
                )
                db.add(seller_stat)

            db.commit()

        bot.send_message(int(data['telegram_id']), "✅ Твой отчёт прошёл модерацию!")
        try:
            # Удаляем фото и сообщение с менеджером
            for photo_id in data.get('manager_photo_message_ids', []):
                bot.delete_message(data['manager_chat_id'], photo_id)
            bot.delete_message(data['manager_chat_id'], data['manager_message_id'])
        except Exception:
            pass

        del pending_reports[report_id]
        bot.answer_callback_query(call.id, "Принято.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('reject|'))
    def handle_reject(call: CallbackQuery):
        _, report_id = call.data.split('|')
        data = pending_reports.get(report_id)
        if not data:
            bot.answer_callback_query(call.id, "⚠️ Истекло или не найдено.")
            return

        bot.send_message(int(data['telegram_id']), "❌ Отчёт не прошёл модерацию, свяжитесь с менеджером.")
        try:
            # Удаляем фото и сообщение с менеджером
            for photo_id in data.get('manager_photo_message_ids', []):
                bot.delete_message(data['manager_chat_id'], photo_id)
            bot.delete_message(data['manager_chat_id'], data['manager_message_id'])
        except Exception:
            pass

        del pending_reports[report_id]
        bot.answer_callback_query(call.id, "Отклонено.")
