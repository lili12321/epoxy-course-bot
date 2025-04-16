import os
import base64
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, Dispatcher, ConversationHandler, MessageHandler, Filters
import psycopg2
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Настройка Telegram-бота
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = "6424513154"  # Твой ID
LIQPAY_PUBLIC_KEY = os.getenv("LIQPAY_PUBLIC_KEY")
LIQPAY_PRIVATE_KEY = os.getenv("LIQPAY_PRIVATE_KEY")
bot = Bot(token=TELEGRAM_TOKEN)

# Список уроков (5 уроков, раз в два дня: дни 1, 3, 5, 7, 9)
LESSONS = [
    {"day": 1, "file_id": "file_id_lesson_1", "description": "Урок 1: Введение в эпоксидную смолу"},
    {"day": 3, "file_id": "file_id_lesson_2", "description": "Урок 2: Основы работы с материалами"},
    {"day": 5, "file_id": "file_id_lesson_3", "description": "Урок 3: Техники заливки"},
    {"day": 7, "file_id": "file_id_lesson_4", "description": "Урок 4: Создание простых изделий"},
    {"day": 9, "file_id": "file_id_lesson_5", "description": "Урок 5: Финальный проект"}
]

# PDF-файлы (заглушки, замени file_id на реальные)
PDF_FILES = [
    {"file_id": "file_id_pdf_1", "caption": "PDF 1: Пример работы с эпоксидной смолой"},
    {"file_id": "file_id_pdf_2", "caption": "PDF 2: Техники безопасности"},
    {"file_id": "file_id_pdf_3", "caption": "PDF 3: Идеи для творчества"}
]

# Состояния для ConversationHandler
EMAIL, PHONE = range(2)

# Настройка подключения к PostgreSQL
def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("PG_DBNAME"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
            sslmode="require"
        )
        logger.info("Successfully connected to PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        raise

# Инициализация базы
def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    email TEXT,
                    phone TEXT,
                    has_access BOOLEAN DEFAULT FALSE,
                    course_start_date TIMESTAMP,
                    last_lesson_sent INTEGER DEFAULT 0
                )
            """)
            conn.commit()
    logger.info("Database initialized")

# Обработчик команды /start
def start(update, context):
    user = update.effective_user
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user.id, user.username, user.first_name, user.last_name)
            )
            conn.commit()

    welcome_message = (
        "🌟 Добро пожаловать в курс по эпоксидной смоле! 🌟\n"
        "Я твой помощник, который поможет тебе освоить все тонкости.\n"
        "Пожалуйста, укажи свои контактные данные для связи. Напиши /setcontact.\n"
        "Чтобы оплатить курс, используй /buy.\n"
        "Если у тебя есть вопросы, напиши /help."
    )
    update.message.reply_text(welcome_message)

# Обработчик команды /setcontact (начало сбора контактов)
def set_contact(update, context):
    update.message.reply_text("Пожалуйста, укажи свой email:")
    return EMAIL

# Обработчик email
def get_email(update, context):
    user = update.effective_user
    email = update.message.text
    context.user_data['email'] = email
    update.message.reply_text("Теперь укажи свой номер телефона:")
    return PHONE

# Обработчик телефона
def get_phone(update, context):
    user = update.effective_user
    phone = update.message.text

    # Сохраняем email и телефон в базе
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET email = %s, phone = %s
                WHERE user_id = %s
                """,
                (context.user_data['email'], phone, user.id)
            )
            conn.commit()

    update.message.reply_text("Спасибо! Контактные данные сохранены. Теперь ты можешь оплатить курс с помощью /buy.")
    return ConversationHandler.END

# Обработчик отмены ввода контактов
def cancel(update, context):
    update.message.reply_text("Ввод контактов отменён. Ты можешь указать их позже с помощью /setcontact.")
    return ConversationHandler.END

# Обработчик команды /buy
def buy(update, context):
    user = update.effective_user
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT has_access, email, phone FROM users WHERE user_id = %s",
                (user.id,)
            )
            result = cur.fetchone()

    if not result:
        update.message.reply_text("Пожалуйста, сначала зарегистрируйся с помощью /start.")
        return

    has_access, email, phone = result

    if has_access:
        update.message.reply_text("✅ Вы уже оплатили курс! Используй /course, чтобы получать уроки.")
        return

    if not email or not phone:
        update.message.reply_text("Пожалуйста, укажи свои контактные данные с помощью /setcontact перед оплатой.")
        return

    # Формируем данные для LiqPay (оплата мини-курса)
    amount = "100"  # Стоимость мини-курса (замени на свою)
    currency = "UAH"
    description = f"Оплата мини-курса по эпоксидной смоле для {user.id}"
    order_id = f"mini_course_{user.id}_{int(context.bot.get_me().id)}"

    data = {
        "public_key": LIQPAY_PUBLIC_KEY,
        "version": "3",
        "action": "pay",
        "amount": amount,
        "currency": currency,
        "description": description,
        "order_id": order_id,
        "result_url": f"https://web-production-0cbe.up.railway.app/payment_callback?user_id={user.id}",
        "server_url": "https://web-production-0cbe.up.railway.app/payment_callback"
    }
    data_str = base64.b64encode(json.dumps(data).encode()).decode()
    signature = base64.b64encode(
        hmac.new(LIQPAY_PRIVATE_KEY.encode(), data_str.encode(), hashlib.sha1).digest()
    ).decode()

    payment_url = f"https://www.liqpay.ua/api/3/checkout?data={data_str}&signature={signature}"
    update.message.reply_text(
        f"💳 Для оплаты мини-курса перейдите по ссылке:\n{payment_url}\n"
        "После оплаты первый урок будет выдан сразу, а остальные — раз в два дня."
    )

# Функция для отправки предложения полноценного курса
def send_full_course_offer(user_id):
    # Формируем данные для LiqPay (оплата полноценного курса)
    amount = "189"  # Стоимость полноценного курса со скидкой
    currency = "EUR"
    description = f"Оплата полноценного курса по эпоксидной смоле для {user_id}"
    order_id = f"full_course_{user_id}_{int(bot.get_me().id)}"

    data = {
        "public_key": LIQPAY_PUBLIC_KEY,
        "version": "3",
        "action": "pay",
        "amount": amount,
        "currency": currency,
        "description": description,
        "order_id": order_id,
        "result_url": f"https://web-production-0cbe.up.railway.app/full_course_callback?user_id={user_id}",
        "server_url": "https://web-production-0cbe.up.railway.app/full_course_callback"
    }
    data_str = base64.b64encode(json.dumps(data).encode()).decode()
    signature = base64.b64encode(
        hmac.new(LIQPAY_PRIVATE_KEY.encode(), data_str.encode(), hashlib.sha1).digest()
    ).decode()

    payment_url = f"https://www.liqpay.ua/api/3/checkout?data={data_str}&signature={signature}"

    # Формируем сообщение с предложением
    offer_message = (
        "🎉 Поздравляем с завершением мини-курса! Вы сделали большой шаг в освоении эпоксидной смолы!\n\n"
        "🔥 **Только сегодня!** Поскольку вы прошли мой мини-курс, у вас есть уникальная возможность приобрести "
        "полноценный курс «Мастер эпоксидной смолы» со скидкой 50%! Освойте новую профессию и создавайте невероятные изделия!\n\n"
        f"💸 Цена: **189 €** вместо ~~378 €~~\n"
        f"⏳ Акция действует 24 часа!\n\n"
        f"[Оплатить полноценный курс]({payment_url})\n\n"
        "А пока ознакомьтесь с дополнительными материалами:"
    )
    bot.send_message(chat_id=user_id, text=offer_message, parse_mode="Markdown")

    # Отправляем PDF-файлы
    for pdf in PDF_FILES:
        bot.send_document(chat_id=user_id, document=pdf["file_id"], caption=pdf["caption"])

# Функция для отправки следующего урока
def send_next_lesson(user_id, last_lesson_sent, course_start_date):
    current_date = datetime.utcnow()
    days_since_start = (current_date - course_start_date).days + 1  # +1, чтобы день начала считался первым

    # Находим следующий урок
    next_lesson = None
    for lesson in LESSONS:
        if lesson["day"] > last_lesson_sent and days_since_start >= lesson["day"]:
            next_lesson = lesson
            break

    if next_lesson:
        bot.send_document(
            chat_id=user_id,
            document=next_lesson["file_id"],
            caption=next_lesson["description"]
        )
        # Обновляем last_lesson_sent
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET last_lesson_sent = %s WHERE user_id = %s",
                    (next_lesson["day"], user_id)
                )
                conn.commit()

        # Если это последний урок (5-й урок, день 9), отправляем предложение полноценного курса
        if next_lesson["day"] == LESSONS[-1]["day"]:
            send_full_course_offer(user_id)

        return True
    return False

# Обработчик команды /course
def course(update, context):
    user = update.effective_user
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT has_access, course_start_date, last_lesson_sent FROM users WHERE user_id = %s",
                (user.id,)
            )
            result = cur.fetchone()

    if not result or not result[0]:
        update.message.reply_text(
            "❌ У вас нет доступа к курсу. Пожалуйста, оплатите курс с помощью команды /buy."
        )
        return

    has_access, course_start_date, last_lesson_sent = result

    if not course_start_date:
        update.message.reply_text("❌ Ошибка: дата начала курса не установлена. Свяжитесь с администратором.")
        return

    # Если все уроки мини-курса выданы
    if last_lesson_sent >= LESSONS[-1]["day"]:
        update.message.reply_text(
            "✅ Вы завершили мини-курс! Проверьте последнее сообщение с предложением приобрести полноценный курс."
        )
        return

    if send_next_lesson(user.id, last_lesson_sent, course_start_date):
        update.message.reply_text("✅ Новый урок отправлен!")
    else:
        update.message.reply_text("⏳ Пока новых уроков нет. Уроки выдаются раз в два дня. Попробуйте позже.")

# Обработчик команды /help
def help_command(update, context):
    help_message = (
        "ℹ️ Я бот для курса по эпоксидной смоле!\n"
        "Доступные команды:\n"
        "/start - Начать\n"
        "/setcontact - Указать контактные данные\n"
        "/buy - Оплатить курс\n"
        "/course - Получить следующий урок (после оплаты, раз в два дня)\n"
        "/help - Показать это сообщение\n\n"
        "Если у вас есть вопросы, пишите администратору: @your_admin_username"
    )
    update.message.reply_text(help_message)

# Маршрут для обработки оплаты мини-курса
@app.route("/payment_callback", methods=["GET", "POST"])
def payment_callback():
    logger.info("Received payment callback")
    if request.method == "POST":
        data = request.form.get("data")
        signature = request.form.get("signature")

        # Проверяем подпись
        expected_signature = base64.b64encode(
            hmac.new(LIQPAY_PRIVATE_KEY.encode(), data.encode(), hashlib.sha1).digest()
        ).decode()
        if signature != expected_signature:
            logger.error("Invalid signature in payment callback")
            return "Invalid signature", 400

        # Декодируем данные
        payment_data = json.loads(base64.b64decode(data).decode())
        if payment_data["status"] == "success":
            user_id = payment_data["order_id"].split("_")[2]
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE users
                        SET has_access = TRUE, course_start_date = %s
                        WHERE user_id = %s
                        """,
                        (datetime.utcnow(), user_id)
                    )
                    conn.commit()

            # Уведомляем пользователя
            bot.send_message(
                chat_id=user_id,
                text="🎉 Оплата прошла успешно! Первый урок будет отправлен прямо сейчас. Остальные уроки будут выдаваться раз в два дня."
            )

            # Уведомляем администратора
            bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"💰 Новый платеж! Пользователь {user_id} оплатил мини-курс."
            )

            # Отправляем первый урок
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT course_start_date, last_lesson_sent FROM users WHERE user_id = %s",
                        (user_id,)
                    )
                    result = cur.fetchone()
            course_start_date, last_lesson_sent = result
            send_next_lesson(user_id, last_lesson_sent, course_start_date)

    return "OK"

# Маршрут для обработки оплаты полноценного курса
@app.route("/full_course_callback", methods=["GET", "POST"])
def full_course_callback():
    logger.info("Received full course callback")
    if request.method == "POST":
        data = request.form.get("data")
        signature = request.form.get("signature")

        # Проверяем подпись
        expected_signature = base64.b64encode(
            hmac.new(LIQPAY_PRIVATE_KEY.encode(), data.encode(), hashlib.sha1).digest()
        ).decode()
        if signature != expected_signature:
            logger.error("Invalid signature in full course callback")
            return "Invalid signature", 400

        # Декодируем данные
        payment_data = json.loads(base64.b64decode(data).decode())
        if payment_data["status"] == "success":
            user_id = payment_data["order_id"].split("_")[2]
            
            # Получаем данные пользователя
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT username, first_name, last_name, email, phone FROM users WHERE user_id = %s",
                        (user_id,)
                    )
                    user_data = cur.fetchone()

            if user_data:
                username, first_name, last_name, email, phone = user_data
                # Формируем квитанцию об оплате
                payment_info = (
                    f"Сумма: {payment_data['amount']} {payment_data['currency']}\n"
                    f"Дата платежа: {datetime.fromtimestamp(payment_data['create_date']).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Описание: {payment_data['description']}"
                )

                # Уведомляем администратора с данными клиента
                admin_message = (
                    f"💰 Новый платеж! Пользователь {user_id} оплатил полноценный курс за 189 €.\n\n"
                    f"Данные клиента:\n"
                    f"Username: {username or 'Не указано'}\n"
                    f"Имя: {first_name or 'Не указано'}\n"
                    f"Фамилия: {last_name or 'Не указано'}\n"
                    f"Email: {email or 'Не указано'}\n"
                    f"Телефон: {phone or 'Не указано'}\n\n"
                    f"Квитанция об оплате:\n{payment_info}"
                )
                bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message)

            # Уведомляем пользователя
            bot.send_message(
                chat_id=user_id,
                text="Спасибо большое! Вы приобрели полноценный курс по большой акции со скидкой -50%! Поздравляем!"
            )

    return "OK"

# Маршрут для автоматической проверки уроков
@app.route("/check_lessons", methods=["GET"])
def check_lessons():
    logger.info("Checking lessons for users")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, course_start_date, last_lesson_sent FROM users WHERE has_access = TRUE"
            )
            users = cur.fetchall()

    for user_id, course_start_date, last_lesson_sent in users:
        if course_start_date:
            send_next_lesson(user_id, last_lesson_sent, course_start_date)

    logger.info("Finished checking lessons")
    return "Lessons checked"

# Вебхук для Telegram
@app.route(f"/bot{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    logger.info("Received Telegram webhook update")
    try:
        update = Update.de_json(request.get_json(), bot)
        dispatcher = updater.dispatcher
        dispatcher.process_update(update)
        return "OK"
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return "Error", 500

# Главная страница (для проверки)
@app.route("/")
def index():
    logger.info("Index route accessed")
    return "Bot is running!"

# Инициализация Telegram-бота
try:
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("buy", buy))
    dispatcher.add_handler(CommandHandler("course", course))
    dispatcher.add_handler(CommandHandler("help", help_command))

    # Добавляем ConversationHandler для сбора контактов
    contact_handler = ConversationHandler(
        entry_points=[CommandHandler("setcontact", set_contact)],
        states={
            EMAIL: [MessageHandler(Filters.text & ~Filters.command, get_email)],
            PHONE: [MessageHandler(Filters.text & ~Filters.command, get_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    dispatcher.add_handler(contact_handler)

    logger.info("Telegram bot initialized")
except Exception as e:
    logger.error(f"Failed to initialize Telegram bot: {e}")
    raise

if __name__ == "__main__":
    init_db()
    updater.start_polling()
    updater.idle()
   
