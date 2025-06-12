import os
import logging
import asyncio
from datetime import datetime, timedelta
import pytz
import json
import nest_asyncio
nest_asyncio.apply()

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

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
    "что меня сегодня удивило?"
    "что заставило улыбнуться искренне?"
    "что сегодня принесло мне радость?"
    "в чем я сегодня была хороша?"

]

# Файл для хранения данных
DATA_FILE = 'user_answers.json'

# Загрузка данных из файла
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logging.error("Ошибка чтения JSON. Создаётся новый файл.")
            return {}
    return {}

# Сохранение данных в файл
def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Инициализация хранилища
user_data = load_data()

# Главное меню
def main_menu():
    keyboard = [
        [KeyboardButton("Подписаться"), KeyboardButton("Отписаться")],
        [KeyboardButton("Мои записи")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Получена команда /start от {update.effective_user.id}")
    await update.message.reply_text(
        "Привет! Я буду напоминать тебе заполнять дневник благодарности каждый день в 23:00.\n"
        "Нажми на кнопку ниже, чтобы начать!",
        reply_markup=main_menu()
    )

async def add_user_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in user_data:
        user_data[user_id] = {"answers": [], "subscribed": True}
    else:
        user_data[user_id]["subscribed"] = True
    save_data(user_data)
    logging.info(f"Пользователь {user_id} подписался через кнопку")
    await update.message.reply_text("Вы подписались на ежедневные напоминания!", reply_markup=main_menu())

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id in user_data:
        user_data[user_id]["subscribed"] = False
        save_data(user_data)
        logging.info(f"Пользователь {user_id} отписался")
        await update.message.reply_text("Вы отписаны от ежедневных напоминаний.", reply_markup=main_menu())

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in user_data or "history" not in user_data[user_id]:
        await update.message.reply_text("У вас пока нет записей.", reply_markup=main_menu())
        return

    history = user_data[user_id]["history"]
    if not history:
        await update.message.reply_text("История пуста.", reply_markup=main_menu())
        return

    keyboard = [
        [InlineKeyboardButton(date, callback_data=f"date_{date}")]
        for date in sorted(history.keys(), reverse=True)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите дату:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("date_"):
        date_str = data.split("_")[1]
        user_id = str(query.from_user.id)
        entry = user_data[user_id]["history"].get(date_str, [])

        text = f"Запись от {date_str}:\n\n"
        for q, a in zip(QUESTIONS, entry):
            text += f"{q}\n{a}\n\n"

        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_dates")]
        ]))

    elif data == "back_to_dates":
        await show_history(query, context)

# --- Response Handler ---

async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()

    if text == "Подписаться":
        await add_user_from_button(update, context)
        return
    elif text == "Отписаться":
        await unsubscribe(update, context)
        return
    elif text == "Мои записи":
        await show_history(update, context)
        return

    if user_id not in user_data:
        user_data[user_id] = {"answers": [], "subscribed": False}

    answers = user_data[user_id].get("answers", [])

    answers.append(text)
    user_data[user_id]["answers"] = answers
    save_data(user_data)

    await update.message.reply_text("Записано! Спасибо.", reply_markup=main_menu())

    if len(answers) == len(QUESTIONS):
        date_str = datetime.now(pytz.timezone('Europe/Moscow')).strftime('%Y-%m-%d')
        if "history" not in user_data[user_id]:
            user_data[user_id]["history"] = {}
        user_data[user_id]["history"][date_str] = answers
        user_data[user_id]["answers"] = []
        save_data(user_data)
        await update.message.reply_text("Все ответы записаны! До завтра.", reply_markup=main_menu())

# --- Daily Reminder ---

async def schedule_daily_reminder(application):
    tz = pytz.timezone('Europe/Moscow')
    while True:
        now_dt = datetime.now(tz)
        target_time = now_dt.replace(hour=23, minute=00, second=0, microsecond=0)
        if now_dt >= target_time:
            target_time += timedelta(days=1)
        wait_seconds = (target_time - now_dt).total_seconds()
        logging.info(f"⏰ Жду {wait_seconds:.0f} секунд до следующего напоминания")
        await asyncio.sleep(wait_seconds)

        for user_id in list(user_data.keys()):
            if user_data[user_id].get("subscribed", False):
                logging.info(f"📨 Отправляю вопросы пользователю {user_id}")
                try:
                    for question in QUESTIONS:
                        await application.bot.send_message(chat_id=int(user_id), text=question)
                except Exception as e:
                    logging.error(f"❌ Ошибка отправки пользователю {user_id}: {e}")

# --- Main ---

async def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("history", show_history))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_response))
    application.add_handler(CallbackQueryHandler(button_handler))

    await application.initialize()

    asyncio.create_task(schedule_daily_reminder(application))

    logging.info("Запуск polling...")
    await application.run_polling()

# --- Run ---

if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(main())
        loop.run_forever()
    except RuntimeError:
        asyncio.run(main())