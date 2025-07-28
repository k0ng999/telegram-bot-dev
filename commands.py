from telebot.types import BotCommand

ALL_COMMANDS = [
    BotCommand("start", "Начать регистрацию"),
    BotCommand("support", "Поддержка"),
    BotCommand("website", "Наш сайт"),
    BotCommand("info", "Информация"),
    BotCommand("catalog", "Каталог"),
    BotCommand("education", "Обучение"),
    BotCommand("stats", "Статистика"),
    BotCommand("faq", "FAQ"),
    BotCommand("news_and_bonuses", "Новости и Бонусы")
]

COMMANDS_WITHOUT_START = [cmd for cmd in ALL_COMMANDS if cmd.command != "start"]
