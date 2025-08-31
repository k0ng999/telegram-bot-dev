from telebot import TeleBot, types
from sqlalchemy.orm import Session
from models.service.models import Faq
from models.service import SessionLocal as ServiceSessionLocal


def register(bot: TeleBot):

    @bot.message_handler(commands=['faq'])
    def show_faq(message):
        with ServiceSessionLocal() as session:
            faqs = session.query(Faq).all()

        if not faqs:
            bot.send_message(message.chat.id, "❌ FAQ пока пуст.")
            return

        keyboard = types.InlineKeyboardMarkup()
        for faq in faqs:
            keyboard.add(
                types.InlineKeyboardButton(
                    text=faq.question,
                    callback_data=f"faq_{faq.id}"
                )
            )

        bot.send_message(message.chat.id, "📖 Выберите вопрос:", reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("faq_"))
    def show_answer(call):
        faq_id = call.data.split("_", 1)[1]

        with ServiceSessionLocal() as session:
            faq = session.query(Faq).filter_by(id=faq_id).first()

        if not faq:
            bot.answer_callback_query(call.id, "❌ Вопрос не найден.")
            return

        # ✅ закрываем "висящую загрузку"
        bot.answer_callback_query(call.id)

        text = f"❓ {faq.question}\n\n📌 {faq.answer}"

        if faq.image_urls:
            urls = [u.strip() for u in faq.image_urls.split(",") if u.strip()]

            if len(urls) == 1:
                # Одно фото
                try:
                    bot.send_photo(
                        call.message.chat.id,
                        urls[0],
                        caption=text
                    )
                except Exception:
                    bot.send_message(
                        call.message.chat.id,
                        f"{text}\n\n🔗 {urls[0]}"
                    )
            else:
                # Несколько фото
                media = []
                for i, url in enumerate(urls):
                    try:
                        media.append(
                            types.InputMediaPhoto(
                                media=url,
                                caption=text if i == 0 else None
                            )
                        )
                    except Exception:
                        bot.send_message(call.message.chat.id, f"🔗 {url}")

                if media:
                    bot.send_media_group(call.message.chat.id, media)
        else:
            # Только текст
            bot.send_message(call.message.chat.id, text)
