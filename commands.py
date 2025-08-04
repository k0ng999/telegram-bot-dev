from telebot.types import BotCommand

ALL_COMMANDS = [
    BotCommand("start", "🚀 Главная страница"),
    BotCommand("info", "ℹ️ Информация"),
    BotCommand("catalog", "📚 Каталог"),
    BotCommand("education", "🎓 Обучение"),
    BotCommand("stats", "📊 Моя статистика"),
    BotCommand("sales_report", "📤 Отправить отчет о продажах"),
    BotCommand("get_your_bonuses", "💰 Получить свои бонусы"),
    BotCommand("news_and_bonuses", "📰 Новости и Бонусы"),
    BotCommand("website", "🌐 Наш сайт"),
    BotCommand("faq", "❓ Часто задаваемые вопросы"),
    BotCommand("support", "🆘 Поддержка"),
]

command_names = [cmd.command for cmd in ALL_COMMANDS]
