send_message(chat_id, lesson["content"])
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

if name == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
