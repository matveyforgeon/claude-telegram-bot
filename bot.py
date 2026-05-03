import os
import time
import requests
import anthropic

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def fix_dashes(text):
    return text.replace(" -- ", " - ").replace("--", "-").replace(" — ", " - ").replace("—", "-")

SYSTEM_PROMPTS = {
    "default": "Ты - Брат, дружелюбный ИИ-ассистент. Отвечай тепло и понятно, можешь иногда пошутить, но в меру. Обращайся к пользователю на ты. Никогда не используй длинное тире, только обычный дефис.",
    "delo": "Ты - Брат, строгий деловой ИИ-ассистент. Отвечай чётко, по делу, без лишних слов. Никаких шуток, только факты и конкретика. Обращайся к пользователю на ты. Никогда не используй длинное тире, только обычный дефис.",
    "smeh": "Ты - Брат, весёлый ИИ-ассистент с отличным чувством юмора. Шути, используй мемы, будь расслабленным - но при этом всё равно помогай по делу. Обращайся к пользователю на ты. Можешь использовать смешные сравнения и эмодзи. Никогда не используй длинное тире, только обычный дефис.",
    "test": "Ты - Брат, ассистент для решения тестов. Отвечай максимально кратко и точно. Только правильный ответ, без объяснений если не просят. Никогда не используй длинное тире, только обычный дефис.",
    "skill_gpt": """You are a prompt director for GPT Image 2.0. Convert user concepts into production-ready prompts.

Three formats:
- Format A (JSON): for layouts, UI, infographics, posters with panels, character sheets
- Format B (cinematic prose): for single scenes, portraits, illustrations
- Format C (meta-prompt): when user gives only a theme

Return ONLY the prompt in a code block. No explanation.
Communicate with user in Russian, write prompts in English.
Never use em-dashes, only regular hyphens.""",

    "skill_sales": """Ты - Sales Coach по продажам AI-визуалов.

Прайс: 1 фото $15, 10 фото $140, 20 фото $260, 1 видео $80, 5 видео $350, 10 видео $650.
Ниши: одежда, рестораны, недвижимость, блогеры, агентства.

Задачи:
- "найди клиентов" - ищи реальные аккаунты, выдавай таблицу с оценкой потенциала
- "напиши оффер" - готовый текст под нишу
- "напиши DM" - скрипт для директа
- возражение - готовый ответ

Возражения:
"Дорого" - У нас 10 фото = $140, в 3-5 раз дешевле студии. Начнём с бесплатного теста?
"Уже есть фотограф" - AI - дополнение, не замена. Больше контента за меньший бюджет.
"Подумаю" - Сделаю 1 тестовый визуал бесплатно прямо сейчас. Попробуем?

Никогда не используй длинное тире, только обычный дефис.
Всегда давай готовые тексты, не абстрактные советы.""",

    "skill_mgimo": """Ты - ассистент для контрольных работ по БЖД МГИМО.

Данные студента (всегда использовать):
ФИО: Портненко М.В., Институт: ИМТУР, Курс: 1, Группа: 1
Преподаватель: Трофимов Сергей Анатольевич
Дисциплина: БЕЗОПАСНОСТЬ ЖИЗНЕДЕЯТЕЛЬНОСТИ
Вуз: МГИМО МИД России, Москва, 2026

Структура: Титул - Содержание - Введение - Основная часть (2 подглавы) - Заключение - Литература (5 источников).
Оформление: Times New Roman 14pt, интервал 1.5, поля 30/15/20/20мм.
Спрашивай только тему. Пиши полный текст работы.
Никогда не используй длинное тире, только обычный дефис.""",

    "skill_coursework": """Ты - ассистент для курсовых работ МГИМО.

Оформление: Times New Roman 14pt, интервал 1.5, поля 30/15/20/20мм, нумерация с введения.
Структура: Титул - Оглавление - Введение (2-3 стр.) - Главы - Заключение - Литература.
Введение: актуальность, объект, предмет, цель, задачи, структура.

Сначала спроси: тему, ФИО, группу, институт, кафедру, научного руководителя, год.
Затем пиши полный текст.
Никогда не используй длинное тире, только обычный дефис.""",
}

BUTTONS = {
    "🗣 Дефолт": ("default", "Режим: 🗣 Дефолт. Общаемся по-дружески!"),
    "💼 По делу": ("delo", "Режим: 💼 По делу. Чётко и по существу."),
    "😂 Смехуятина": ("smeh", "Режим: 😂 Смехуятина. Поехали!"),
    "📝 Тесты": ("test", "Режим: 📝 Тесты. Скидывай вопрос!"),
    "🎨 GPT Image промпты": ("skill_gpt", "Скилл: 🎨 GPT Image. Скидывай идею!"),
    "💰 AI Visuals Sales": ("skill_sales", "Скилл: 💰 AI Sales. Чем помочь?"),
    "📚 МГИМО БЖД": ("skill_mgimo", "Скилл: 📚 МГИМО БЖД. Скидывай тему!"),
    "📖 Курсовая МГИМО": ("skill_coursework", "Скилл: 📖 Курсовая. Скажи тему и данные!"),
    "🇷🇺 Русский": None,
    "🇬🇧 English": None,
    "🌐 Авто": None,
}

user_data = {}
pending_clear = set()

def get_user(uid):
    if uid not in user_data:
        user_data[uid] = {"mode": "default", "language": "ru", "history": []}
    return user_data[uid]

def get_system(uid):
    u = get_user(uid)
    base = SYSTEM_PROMPTS[u["mode"]]
    if u["language"] == "ru":
        base += "\nОтвечай только на русском языке."
    elif u["language"] == "en":
        base += "\nAlways respond in English only."
    return base

def send(chat_id, text, keyboard=None):
    text = fix_dashes(text)
    chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk}
        if i == 0 and keyboard:
            payload["reply_markup"] = {
                "keyboard": keyboard,
                "one_time_keyboard": True,
                "resize_keyboard": True
            }
        requests.post(f"{BASE_URL}/sendMessage", json=payload)

def set_commands():
    cmds = [
        {"command": "start", "description": "Начать заново"},
        {"command": "mode", "description": "Режим общения"},
        {"command": "skills", "description": "Специальные навыки"},
        {"command": "lang", "description": "Язык ответов"},
        {"command": "clear", "description": "Очистить память"},
        {"command": "help", "description": "Помощь"},
    ]
    requests.post(f"{BASE_URL}/setMyCommands", json={"commands": cmds})

def handle(update):
    msg = update.get("message", {})
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")
    name = msg.get("from", {}).get("first_name", "братан")
    u = get_user(chat_id)

    # Подтверждение очистки памяти
    if chat_id in pending_clear:
        if text == "✅ Точно очистить":
            pending_clear.discard(chat_id)
            u["history"] = []
            send(chat_id, "🗑 Память очищена! Начинаем с чистого листа.")
        elif text == "❌ Нет":
            pending_clear.discard(chat_id)
            send(chat_id, "Окей, память осталась нетронутой 👍")
        else:
            send(chat_id, "Выбери вариант 👇", [["✅ Точно очистить", "❌ Нет"]])
        return

    if text == "/start":
        send(chat_id,
            f"Йоу, {name}! 👋 Я - Брат, твой личный ИИ-ассистент.\n\n"
            f"Режим: 🗣 Дефолт\n\n"
            f"/mode - сменить режим\n"
            f"/skills - специальные навыки\n"
            f"/lang - язык\n"
            f"/clear - очистить память\n"
            f"/help - помощь\n\n"
            f"Пиши что надо! 😎"
        )
        return

    if text == "/help":
        send(chat_id,
            "🤖 Брат - твой ИИ-ассистент\n\n"
            "Команды:\n"
            "/start - начать заново\n"
            "/mode - режим общения\n"
            "/skills - специальные навыки\n"
            "/lang - язык ответов\n"
            "/clear - очистить память\n\n"
            "Режимы:\n"
            "🗣 Дефолт - дружелюбно\n"
            "💼 По делу - строго\n"
            "😂 Смехуятина - весело\n"
            "📝 Тесты - кратко и точно\n\n"
            "Скиллы:\n"
            "🎨 GPT Image - промпты\n"
            "💰 AI Sales - продажи\n"
            "📚 МГИМО БЖД - контрольные\n"
            "📖 Курсовая - курсовые МГИМО"
        )
        return

    if text == "/mode":
        send(chat_id, "Выбери режим:", [["🗣 Дефолт", "💼 По делу"], ["😂 Смехуятина", "📝 Тесты"]])
        return

    if text == "/skills":
        send(chat_id,
            "🛠 Специальные навыки:\n\n"
            "🎨 GPT Image - промпты для GPT Image 2.0\n"
            "💰 AI Sales - продажи AI-визуалов\n"
            "📚 МГИМО БЖД - контрольные работы\n"
            "📖 Курсовая - курсовые МГИМО\n\n"
            "Выбери навык:",
            [["🎨 GPT Image промпты"], ["💰 AI Visuals Sales"], ["📚 МГИМО БЖД", "📖 Курсовая МГИМО"], ["🗣 Дефолт"]]
        )
        return

    if text == "/lang":
        send(chat_id, "Выбери язык:", [["🇷🇺 Русский", "🇬🇧 English", "🌐 Авто"]])
        return

    if text == "/clear":
        pending_clear.add(chat_id)
        send(chat_id, "Ты уверен? Вся история переписки будет удалена 🗑", [["✅ Точно очистить", "❌ Нет"]])
        return

    if text in BUTTONS:
        val = BUTTONS[text]
        if val:
            u["mode"] = val[0]
            u["history"] = []
            send(chat_id, val[1])
        else:
            if text == "🇷🇺 Русский":
                u["language"] = "ru"
                send(chat_id, "Язык: 🇷🇺 Русский")
            elif text == "🇬🇧 English":
                u["language"] = "en"
                send(chat_id, "Language: 🇬🇧 English")
            elif text == "🌐 Авто":
                u["language"] = "auto"
                send(chat_id, "Язык: 🌐 Авто")
        return

    u["history"].append({"role": "user", "content": text})
    if len(u["history"]) > 20:
        u["history"] = u["history"][-20:]

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=get_system(chat_id),
            messages=u["history"]
        )
        reply = response.content[0].text
        u["history"].append({"role": "assistant", "content": reply})
        send(chat_id, reply)
    except Exception as e:
        send(chat_id, f"Ошибка: {str(e)}")

def main():
    set_commands()
    offset = 0
    print("Бот запущен!")
    while True:
        try:
            r = requests.get(
                f"{BASE_URL}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35
            )
            updates = r.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                handle(update)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
