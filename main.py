from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from liqpay.sdk import LiqPay
import time
import os

# Настройки
BOT_TOKEN = "7918145407:AAEVjC2seqRbZVmapLAn3tNGRFKg7zD6FTA"
LIQPAY_PUBLIC_KEY = "sandbox_i55236513368"
LIQPAY_PRIVATE_KEY = "sandbox_vdQ3oP0si0V9rt13rGDSR81kcl2zGDagZUpznL7c"
LESSONS = [
    "Привет! Это твой первый урок. Удачи в обучении!",
    "Урок 2: Продолжаем изучение.",
    "Урок 3: Последний урок. Хочешь полный курс? Оплати здесь: [ссылка]"
]
USER_LESSON_STATE = {}  # Хранит состояние пользователей (номер урока)

# Инициализация LiqPay
liqpay = LiqPay(LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY)

# Обработчик команды /start
def start(update, context):
    chat_id = update.message.chat_id
    USER_LESSON_STATE[chat_id] = 0
    update.message.reply_text(LESSONS[0])
    send_payment_link(update, context)

# Функция отправки ссылки для оплаты
def send_payment_link(update, context):
    chat_id = update.message.chat_id
    params = {
        "action": "pay",
        "amount": "10.00",
        "currency": "UAH",
        "description": "Оплата курса",
        "order_id": str(chat_id) + str(time.time()),
        "version": "3",
        "result_url": "https://your-app.up.railway.app/success"
    }
    signature, data = liqpay.cnb_form(params)
    payment_link = f"https://www.liqpay.ua/api/3/checkout?data={data}&signature={signature}"
    update.message.reply_text(f"Оплати курс здесь: {payment_link}")

# Обработчик текста (проверка оплаты и отправка уроков)
def handle_text(update, context):
    chat_id = update.message.chat_id
    if chat_id not in USER_LESSON_STATE:
        start(update, context)
        return
    lesson_num = USER_LESSON_STATE[chat_id]
    if lesson_num < len(LESSONS) - 1:
        if time.time() - context.user_data.get(chat_id, 0) >= 172800:  # 2 дня = 172800 секунд
            lesson_num += 1
            update.message.reply_text(LESSONS[lesson_num])
            USER_LESSON_STATE[chat_id] = lesson_num
            context.user_data[chat_id] = time.time()
    else:
        update.message.reply_text("Ты прошел курс! Хочешь полный курс? Оплати здесь: [ссылка]")

# Настройка бота
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
