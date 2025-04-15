from flask import Flask, request
import telebot
import schedule
import time
import threading
import os
import psycopg2
from psycopg2.extras import DictCursor

app = Flask(__name__)

# Настройка Telegram-бота
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = "6424513154"  # Твой ID
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Настройка PostgreSQL
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("PG_DBNAME"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT")
        sslmode="require"
    )

# Инициализация базы
def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id BIGINT PRIMARY KEY,
                    paid BOOLEAN DEFAULT FALSE,
                    lesson INTEGER DEFAULT 1,
                    advanced_course_paid BOOLEAN DEFAULT FALSE
                )
            """)
            conn.commit()

init_db()

# Уроки (заглушки, позже добавим video file_id)
lessons = {
    1: {"type": "text", "content": "Урок 1"},
    2: {"type": "text", "content": "Урок 2"},
    3: {"type": "text", "content": "Урок 3"},
    4: {"type": "text", "content": "Урок 4"},
    5: {"type": "text", "content": "Урок 5"}
}

# PDF для предложения нового курса (ждём file_id)
advanced_course_pdfs = [
    # {"file_id": "<pdf_file_id>", "name": "Тизер курса.pdf"},
    # {"file_id": "<pdf_file_id>", "name": "Чек-лист.pdf"}
]

# Маршрут для домашней страницы
@app.route('/')
def home():
    return "Hello, this is your Telegram Bot!"

# Маршрут для вебхука
@app.route(f'/bot{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
        return 'OK', 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return 'Error', 500

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
            user = cur.fetchone()
            if not user:
                cur.execute(
                    "INSERT INTO users (chat_id, paid, lesson, advanced_course_paid) VALUES (%s, %s, %s, %s)",
                    (chat_id, False, 1, False)
                )
                conn.commit()
    welcome_message = (
        "🌟 Добро пожаловать в курс по эпоксидной смоле! 🌟\n"
        "Я твой помощник, который поможет тебе освоить все тонкости.\n"
        "Чтобы начать, напиши /buy, чтобы оплатить курс.\n"
        "Если у тебя есть вопросы, напиши /help."
    )
    bot.reply_to(message, welcome_message)

# Обработчик команды /help
@bot.message_handler(commands=['help'])
def send_help(message):
    help_message = (
        "📋 Помощь по курсу:\n"
        "- /start — Начать работу с ботом\n"
        "- /buy — Оплатить мини-курс\n"
        "- /progress — Проверить прогресс\n"
        "- /next_lesson — Выдать следующий урок (для тестов)\n"
        "- /help — Показать это сообщение\n"
        "Если у тебя есть вопросы, напиши мне!"
    )
    bot.reply_to(message, help_message)

# Обработчик команды /progress
@bot.message_handler(commands=['progress'])
def show_progress(message):
    chat_id = message.chat.id
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT lesson, paid FROM users WHERE chat_id = %s", (chat_id,))
            user = cur.fetchone()
            if not user or not user["paid"]:
                bot.reply_to(message, "Вы ещё не начали курс. Используйте /buy.")
                return
            lesson = user["lesson"]
            if lesson <= 5:
                bot.reply_to(message, f"Вы на уроке {lesson}.")
            else:
                bot.reply_to(message, "Курс завершён! Проверьте предложение нового курса.")

# Обработчик команды /next_lesson (для тестов)
@bot.message_handler(commands=['next_lesson'])
def next_lesson(message):
    chat_id = message.chat.id
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT lesson, paid FROM users WHERE chat_id = %s", (chat_id,))
            user = cur.fetchone()
            if not user or not user["paid"]:
                bot.reply_to(message, "Сначала оплатите курс с помощью /buy.")
                return
            lesson_number = user["lesson"]
            if lesson_number <= 5:
                send_lesson(chat_id, lesson_number)
            else:
                bot.reply_to(message, "Курс завершён! Проверьте предложение нового курса.")

# Обработчик команды /buy (мини-курс)
@bot.message_handler(commands=['buy'])
def send_invoice(message):
    chat_id = message.chat.id
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT paid FROM users WHERE chat_id = %s", (chat_id,))
            user = cur.fetchone()
            if user and user["paid"]:
                bot.reply_to(message, "Вы уже оплатили мини-курс! Первый урок уже выдан. 🎉")
                return
    try:
        bot.send_invoice(
            chat_id=chat_id,
            title="Мини-курс по эпоксидной смоле",
            description="Доступ к курсу (5 уроков) с пошаговыми инструкциями",
            invoice_payload="mini_course_payment",
            provider_token=os.getenv("LIQPAY_PUBLIC_KEY"),
            currency="UAH",
            prices=[telebot.types.LabeledPrice(label="Мини-курс", amount=100000)]  # 1000 UAH
        )
    except Exception as e:
        bot.reply_to(message, "Ошибка при создании счёта. Попробуйте позже.")
        print(f"Invoice error: {e}")

# Обработчик предпроверки платежа
@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout_query(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# Обработчик успешного платежа
@bot.message_handler(content_types=['successful_payment'])
def process_successful_payment(message):
    chat_id = message.chat.id
    payload = message.successful_payment.invoice_payload
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            if payload == "mini_course_payment":
                cur.execute(
                    "UPDATE users SET paid = %s WHERE chat_id = %s",
                    (True, chat_id)
                )
                bot.send_message(
                    chat_id,
                    "Привет! Спасибо большое, что приобрёл наш мини-курс! 🎉\n"
                    "Вот твой первый урок. Следующий урок будет через 2 дня."
                )
                if ADMIN_CHAT_ID:
                    bot.send_message(
                        ADMIN_CHAT_ID,
                        f"Новый платёж! Пользователь {chat_id} оплатил мини-курс на 1000 UAH."
                    )
                send_lesson(chat_id, 1)
                schedule_lesson_delivery(chat_id)
            elif payload == "advanced_course_payment":
                cur.execute(
                    "UPDATE users SET advanced_course_paid = %s WHERE chat_id = %s",
                    (True, chat_id)
                )
                bot.send_message(
                    chat_id,
                    "Спасибо за покупку продвинутого курса! 🎓 Доступ скоро будет предоставлен."
                )
                if ADMIN_CHAT_ID:
                    bot.send_message(
                        ADMIN_CHAT_ID,
                        f"Новый платёж! Пользователь {chat_id} оплатил продвинутый курс на 1000 UAH."
                    )
            conn.commit()

# Функция для отправки урока
def send_lesson(chat_id, lesson_number):
    lesson = lessons.get(lesson_number)
    if lesson:
        try:
            if lesson["type"] == "text":
                bot.send_message(chat_id, lesson["content"])
            elif lesson["type"] == "video":
                bot.send_video(chat_id, lesson["file_id"])
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET lesson = %s WHERE chat_id = %s",
                        (lesson_number + 1, chat_id)
                    )
                    conn.commit()
            if lesson_number < 5:
                bot.send_message(chat_id, f"Следующий урок будет через 2 дня.")
            elif lesson_number == 5:
                send_advanced_course_offer(chat_id)
        except Exception as e:
            bot.send_message(chat_id, "Ошибка при отправке урока. Свяжитесь с поддержкой.")
            print(f"Lesson delivery error: {e}")
    else:
        bot.send_message(chat_id, "Курс завершён! Спасибо за участие! 🎓")

# Функция для отправки предложения нового курса
def send_advanced_course_offer(chat_id):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT advanced_course_paid FROM users WHERE chat_id = %s", (chat_id,))
            user = cur.fetchone()
            if user and user["advanced_course_paid"]:
                bot.send_message(chat_id, "Вы уже приобрели продвинутый курс! 🎓")
                return
    bot.send_message(
        chat_id,
        "🎉 Поздравляем с завершением мини-курса! 🎉\n"
        "Только для вас — эксклюзивное предложение!\n"
        "Купите наш продвинутый курс по эпоксидной смоле СЕЙЧАС со скидкой 50%!\n"
        "Обычная цена: 2000 UAH, для вас — всего 1000 UAH!\n"
        "Вот что вас ждёт:"
    )
    for pdf in advanced_course_pdfs:
        bot.send_document(chat_id, pdf["file_id"], caption=pdf["name"])
    try:
        bot.send_invoice(
            chat_id=chat_id,
            title="Продвинутый курс по эпоксидной смоле",
            description="Полный курс с углублёнными техниками (скидка 50%)",
            invoice_payload="advanced_course_payment",
            provider_token=os.getenv("LIQPAY_PUBLIC_KEY"),
            currency="UAH",
            prices=[telebot.types.LabeledPrice(label="Продвинутый курс", amount=100000)]  # 1000 UAH
        )
    except Exception as e:
        bot.send_message(chat_id, "Ошибка при создании счёта. Свяжитесь с поддержкой.")
        print(f"Invoice error: {e}")

# Функция для планирования выдачи уроков
def schedule_lesson_delivery(chat_id):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT lesson FROM users WHERE chat_id = %s", (chat_id,))
            lesson_number = cur.fetchone()["lesson"]
    if lesson_number <= 5:
        schedule.every(2).days.do(send_lesson, chat_id, lesson_number)

# Запуск schedule в отдельном потоке
def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=run_schedule, daemon=True).start()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
