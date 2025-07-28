from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Словарь частых вопросов и ответов (ключ — короткий, значение — пара "вопрос:ответ")
FAQS = {
    "sizes": (
        "Какие бывают размеры обуви в детском блоке?",
        "С 17 по 25 👟"
    ),
    "care": (
        "Как ухаживать за обувью?",
        "Протирать влажной тканью. Не стирать в машинке! 🧼"
    ),
    "models": (
        "Какие есть модели обуви?",
        "Кроссовки, ботинки, сандалии — уточняйте в каталоге 👟👢"
    ),
}

def register(bot):
    @bot.message_handler(commands=['faq'])
    def handle_faq(message: Message):
        keyboard = InlineKeyboardMarkup(row_width=1)
        for key, (question, _) in FAQS.items():
            keyboard.add(InlineKeyboardButton(text=question, callback_data=f"faq_{key}"))

        bot.send_message(message.chat.id, "❓ Часто задаваемые вопросы:", reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("faq_"))
    def handle_faq_answer(call: CallbackQuery):
        key = call.data.replace("faq_", "")
        if key in FAQS:
            question, answer = FAQS[key]
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, f"📌 {question}\n\n💬 {answer}")
        else:
            bot.answer_callback_query(call.id, "Вопрос не найден")
