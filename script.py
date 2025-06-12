import os
import logging
import asyncio
from datetime import datetime, timedelta
import pytz

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

# Получаем токен из переменной окружения
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TOKEN:
    raise ValueError("Токен не найден! Убедитесь, что в файле .env есть переменная TELEGRAM_BOT_TOKEN.")

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

QUESTIONS = [
    "За что я сегодня благодарна(ен)?",
    "Что сегодня принесло мне радость?",
    "Что я сделала(делал) хорошо сегодня?",
    "Что я могу улучшить завтра?",
]

user_responses = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я буду напоминать тебе заполнять дневник благодарности каждый день в 23:00. Просто отвечай на мои вопросы!"
    )


async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if user_id not in user_responses:
        user_responses[user_id] = []

    user_responses[user_id].append(text)
    await update.message.reply_text("Записано! Спасибо.")


async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if 'users' not in context.application.bot_data:
        context.application.bot_data['users'] = set()
    context.application.bot_data['users'].add(user_id)
    await update.message.reply_text("Вы подписались на ежедневные напоминания!")


async def schedule_daily_reminder(application):
    tz = pytz.timezone('Europe/Moscow')
    while True:
        now_dt = datetime.now(tz)
        target_time = now_dt.replace(hour=23, minute=0, second=0, microsecond=0)
        if now_dt >= target_time:
            target_time += timedelta(days=1)
        wait_seconds = (target_time - now_dt).total_seconds()
        await asyncio.sleep(wait_seconds)

        users = application.bot_data.get('users', set())
        for user_id in users:
            for question in QUESTIONS:
                try:
                    await application.bot.send_message(chat_id=user_id, text=question)
                except Exception as e:
                    print(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")


async def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", add_user))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_response))

    # Запускаем задачу планировщика напоминаний
    asyncio.create_task(schedule_daily_reminder(application))

    # Запускаем бота (не блокирующий вызов)
    await application.start()


# Если вы запускаете этот скрипт в интерактивной среде (например PyCharm), используйте следующий код для запуска:

if __name__ == '__main__':
    # Проверка наличия уже запущенного цикла событий и запуск основного кода
    try:
        # В случае если цикл уже запущен (например в Jupyter или PyCharm), используйте этот подход
        loop = asyncio.get_event_loop()
        loop.create_task(main())
        loop.run_forever()
    except RuntimeError:
        # Если цикл не запущен — создаем новый и запускаем его
        asyncio.run(main())