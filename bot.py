import os
import io
import time
import base64
import requests
import anthropic

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
FREETHEAI_KEY = os.environ.get("FREETHEAI_KEY", "")

BANNED_USERS = set(
    int(x.strip()) for x in os.environ.get("BANNED_USERS", "").split(",") if x.strip().isdigit()
)
ADMIN_USERNAME = "forge0n"
ADMIN_IDS = set(
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
)
MGIMO_ALLOWED = ADMIN_IDS.copy()

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
FREETHEAI_URL = "https://api.freetheai.xyz/v1/images/generations"
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Лимиты
FREE_MSG_LIMIT = 20
FREE_PHOTO_LIMIT = 5
REFERRAL_BONUS_MSG = 15
REFERRAL_BONUS_PHOTO = 5

# Модели Claude
CLAUDE_MODELS = {
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
}
CLAUDE_MODEL_NAMES = {
    "sonnet": "⚡ Sonnet 4.6",
    "opus": "🧠 Opus 4.7",
}

# Модели для генерации фото
PHOTO_MODELS = {
    "nbpro": "img/nano-banana-pro",
    "gpt2": "img/gpt-image-2",
    "nb2": "img/nano-banana-2",
    "gpt15": "img/gpt-image-1.5",
    "seed45": "img/seedream-4.5",
    "seed5": "img/seedream-5.0-lite",
    "grok": "img/grok-imagine",
}
PHOTO_MODEL_NAMES = {
    "nbpro":  "🍌 Nano Banana Pro",
    "gpt2":   "🖼 GPT Image 2.0",
    "nb2":    "🍌 Nano Banana 2",
    "gpt15":  "🖼 GPT Image 1.5",
    "seed45": "🌱 Seedream 4.5",
    "seed5":  "🌱 Seedream 5.0 Lite",
    "grok":   "⚡ Grok Imagine",
}

def fix_dashes(text):
    return text.replace(" -- ", " - ").replace("--", "-").replace(" — ", " - ").replace("—", "-")

SYSTEM_PROMPTS = {
    "default": "Ты - универсальный ИИ-ассистент. Отвечай нейтрально, чётко и по делу. Без лишних эмодзи, без личности и шуток. Обращайся к пользователю на ты. Никогда не используй длинное тире, только обычный дефис.",
    "delo": "Ты - строгий деловой ИИ-ассистент. Отвечай максимально чётко и кратко, только факты и конкретика. Никаких шуток и эмодзи. Обращайся к пользователю на ты. Никогда не используй длинное тире, только обычный дефис.",
    "friend": "Ты - друг и весёлый ИИ-ассистент с отличным чувством юмора. Немного шути, будь расслабленным - но при этом всё равно помогай по делу. Обращайся к пользователю на ты как к самому близкому человеку. Можешь использовать эмодзи. Никогда не используй длинное тире, только обычный дефис.",
    "test": "Ты - ассистент для решения тестов. Отвечай максимально кратко и точно. Только правильный ответ, без объяснений если не просят. Никогда не используй длинное тире, только обычный дефис.",
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

user_data = {}
pending_clear = set()

def get_user(uid):
    if uid not in user_data:
        user_data[uid] = {
            "mode": "default",
            "language": "ru",
            "history": [],
            "model": "sonnet",
            "photo_model": None,      # сбрасывается при смене режима
            "msg_count": 0,
            "photo_count": 0,
            "has_sub": False,
            "referral_bonus_msg": 0,
            "referral_bonus_photo": 0,
            "referred_by": None,
            "referrals": [],
        }
    return user_data[uid]

def is_admin(user_id, username):
    return username == ADMIN_USERNAME or user_id in ADMIN_IDS

def can_use_mgimo(user_id, username):
    return is_admin(user_id, username) or user_id in MGIMO_ALLOWED

def msg_limit(uid):
    u = get_user(uid)
    if u["has_sub"]: return 999999
    return FREE_MSG_LIMIT + u.get("referral_bonus_msg", 0)

def photo_limit(uid):
    u = get_user(uid)
    if u["has_sub"]: return 999999
    return FREE_PHOTO_LIMIT + u.get("referral_bonus_photo", 0)

def can_msg(uid):
    u = get_user(uid)
    return u["msg_count"] < msg_limit(uid)

def can_photo(uid):
    u = get_user(uid)
    return u["photo_count"] < photo_limit(uid)

def get_system(uid):
    u = get_user(uid)
    base = SYSTEM_PROMPTS[u["mode"]]
    if u["language"] == "ru":
        base += "\nОтвечай только на русском языке."
    elif u["language"] == "en":
        base += "\nAlways respond in English only."
    return base

def send_typing(chat_id):
    requests.post(f"{BASE_URL}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})

def send(chat_id, text, keyboard=None, markdown=False):
    text = fix_dashes(text)
    chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk}
        if markdown:
            payload["parse_mode"] = "Markdown"
        if i == 0 and keyboard:
            payload["reply_markup"] = {
                "keyboard": keyboard,
                "one_time_keyboard": True,
                "resize_keyboard": True
            }
        r = requests.post(f"{BASE_URL}/sendMessage", json=payload)
        if markdown and r.status_code != 200:
            payload.pop("parse_mode", None)
            requests.post(f"{BASE_URL}/sendMessage", json=payload)

def send_photo_url(chat_id, url, caption=""):
    requests.post(f"{BASE_URL}/sendPhoto", json={
        "chat_id": chat_id,
        "photo": url,
        "caption": fix_dashes(caption)
    })

def get_file_url(file_id):
    r = requests.get(f"{BASE_URL}/getFile", params={"file_id": file_id})
    path = r.json().get("result", {}).get("file_path", "")
    return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}" if path else None

def download_photo_b64(file_id):
    url = get_file_url(file_id)
    if not url: return None
    r = requests.get(url)
    return base64.b64encode(r.content).decode()

def generate_photo(prompt, ref_images_b64=None, photo_model_key="gpt2"):
    model_id = PHOTO_MODELS.get(photo_model_key, PHOTO_MODELS["gpt2"])
    payload = {
        "model": model_id,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
    }
    if ref_images_b64:
        # Добавляем референс-изображения если есть
        payload["image"] = f"data:image/jpeg;base64,{ref_images_b64[0]}"

    r = requests.post(
        FREETHEAI_URL,
        headers={
            "Authorization": f"Bearer {FREETHEAI_KEY}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=120
    )
    data = r.json()
    if r.status_code == 200:
        items = data.get("data", [])
        if items:
            return items[0].get("url") or items[0].get("b64_json")
    return None

def show_photo_model_menu(chat_id):
    send(chat_id,
        "🖼 *Режим генерации фото*\n\n"
        "Выбери модель для генерации:",
        [
            ["🍌 Nano Banana Pro", "🖼 GPT Image 2.0"],
            ["🍌 Nano Banana 2", "🖼 GPT Image 1.5"],
            ["🌱 Seedream 4.5", "🌱 Seedream 5.0 Lite"],
            ["⚡ Grok Imagine"],
        ],
        markdown=True
    )

PHOTO_MODEL_BUTTONS = {
    "🍌 Nano Banana Pro":  "nbpro",
    "🖼 GPT Image 2.0":    "gpt2",
    "🍌 Nano Banana 2":    "nb2",
    "🖼 GPT Image 1.5":    "gpt15",
    "🌱 Seedream 4.5":     "seed45",
    "🌱 Seedream 5.0 Lite":"seed5",
    "⚡ Grok Imagine":     "grok",
}

def set_commands():
    cmds = [
        {"command": "start", "description": "Начать заново"},
        {"command": "mode", "description": "Режим общения"},
        {"command": "skills", "description": "Специальные навыки"},
        {"command": "model", "description": "Выбор модели Claude"},
        {"command": "lang", "description": "Язык ответов"},
        {"command": "clear", "description": "Очистить память"},
        {"command": "sub", "description": "Подписка"},
        {"command": "ref", "description": "Реферальная ссылка"},
        {"command": "status", "description": "Мой статус"},
        {"command": "help", "description": "Помощь"},
    ]
    requests.post(f"{BASE_URL}/setMyCommands", json={"commands": cmds})

def handle_admin(chat_id, text, user_id, username):
    if not is_admin(user_id, username):
        send(chat_id, "Нет доступа.")
        return
    parts = text.split()
    cmd = parts[0]

    if cmd == "/admin":
        send(chat_id,
            "👑 *Админ-панель*\n\n"
            f"Всего пользователей: {len(user_data)}\n\n"
            "Команды:\n"
            "/users - список пользователей\n"
            "/ban [id] - забанить\n"
            "/unban [id] - разбанить\n"
            "/givesub [id] - выдать подписку\n"
            "/givemgimo [id] - доступ к МГИМО",
            markdown=True
        )
    elif cmd == "/users":
        if not user_data:
            send(chat_id, "Пользователей нет.")
            return
        lines = ["👥 *Последние пользователи:*\n"]
        for uid, u in list(user_data.items())[-30:]:
            sub = "✅" if u.get("has_sub") else f"msg:{u.get('msg_count',0)}/{FREE_MSG_LIMIT} photo:{u.get('photo_count',0)}/{FREE_PHOTO_LIMIT}"
            banned = " 🚫" if uid in BANNED_USERS else ""
            lines.append(f"`{uid}`{banned} - {sub}")
        send(chat_id, "\n".join(lines), markdown=True)
    elif cmd == "/ban" and len(parts) > 1:
        try:
            BANNED_USERS.add(int(parts[1]))
            send(chat_id, f"✅ {parts[1]} забанен.")
        except: send(chat_id, "Неверный ID.")
    elif cmd == "/unban" and len(parts) > 1:
        try:
            BANNED_USERS.discard(int(parts[1]))
            send(chat_id, f"✅ {parts[1]} разбанен.")
        except: send(chat_id, "Неверный ID.")
    elif cmd == "/givesub" and len(parts) > 1:
        try:
            get_user(int(parts[1]))["has_sub"] = True
            send(chat_id, f"✅ Подписка выдана {parts[1]}.")
        except: send(chat_id, "Неверный ID.")
    elif cmd == "/givemgimo" and len(parts) > 1:
        try:
            MGIMO_ALLOWED.add(int(parts[1]))
            send(chat_id, f"✅ Доступ к МГИМО выдан {parts[1]}.")
        except: send(chat_id, "Неверный ID.")

def handle(update):
    msg = update.get("message", {})
    if not msg:
        return

    chat_id = msg["chat"]["id"]
    user_id = msg.get("from", {}).get("id", 0)
    text = msg.get("text", "") or ""
    caption = msg.get("caption", "") or ""
    name = msg.get("from", {}).get("first_name", "пользователь")
    username = msg.get("from", {}).get("username", "")
    photos = msg.get("photo", [])

    print(f"[USER] id={user_id} @{username} {name}: {(text or caption)[:80]}")

    if user_id in BANNED_USERS:
        send(chat_id, "У тебя нет доступа к этому боту.")
        return

    u = get_user(chat_id)

    # Реферальная регистрация
    if text.startswith("/start ref_") and not u.get("referred_by"):
        try:
            ref_id = int(text.split("ref_")[1])
            if ref_id != chat_id and ref_id in user_data:
                ref_u = get_user(ref_id)
                if ref_u.get("has_sub"):
                    ref_u["referral_bonus_msg"] = ref_u.get("referral_bonus_msg", 0) + REFERRAL_BONUS_MSG
                    ref_u["referral_bonus_photo"] = ref_u.get("referral_bonus_photo", 0) + REFERRAL_BONUS_PHOTO
                    ref_u["referrals"].append(chat_id)
                    u["referred_by"] = ref_id
                    send(ref_id, f"🎉 Друг зарегистрировался по твоей ссылке!\n+{REFERRAL_BONUS_MSG} сообщений +{REFERRAL_BONUS_PHOTO} фото.")
        except: pass

    # Админ команды
    if text.startswith(("/admin", "/users", "/ban", "/unban", "/givesub", "/givemgimo")):
        handle_admin(chat_id, text, user_id, username)
        return

    # Подтверждение очистки
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

    # Обработка фото в режиме генерации
    if u.get("mode") == "photo" and (photos or (caption and not text)):
        prompt = caption.strip() if caption else ""

        # Если фото есть но нет подписи — просим промпт
        if photos and not prompt:
            send(chat_id, "📝 Напиши подпись к фото - это будет промпт для генерации!\nПример: «Сделай фон закатным, добавь драму»")
            return

        # Если текст без фото — тоже генерируем
        if text and not photos:
            prompt = text

        if not prompt:
            send(chat_id, "Напиши промпт для генерации фото 👇")
            return

        # Проверка модели выбрана ли
        if not u.get("photo_model"):
            show_photo_model_menu(chat_id)
            return

        # Проверка лимита фото
        if not can_photo(chat_id):
            rem_msg = max(0, msg_limit(chat_id) - u.get("msg_count", 0))
            send(chat_id,
                f"⚠️ У тебя закончились бесплатные фото ({FREE_PHOTO_LIMIT} шт.).\n\n"
                f"Оформи подписку через /sub или пригласи друга через /ref (+{REFERRAL_BONUS_PHOTO} фото за каждого)."
            )
            return

        # Скачиваем референс-фото если есть (берём лучшее качество, до 5 фото)
        ref_images = []
        if photos:
            send_typing(chat_id)
            # Берём по одному фото высокого качества
            best = photos[-1]  # последнее = самое большое
            b64 = download_photo_b64(best["file_id"])
            if b64:
                ref_images.append(b64)

        model_name = PHOTO_MODEL_NAMES.get(u["photo_model"], "GPT Image 2.0")
        send(chat_id, f"⏳ Генерирую фото...\nМодель: {model_name}\nПромпт: {prompt[:100]}")
        send_typing(chat_id)

        try:
            result = generate_photo(prompt, ref_images if ref_images else None, u["photo_model"])
            if result:
                u["photo_count"] = u.get("photo_count", 0) + 1
                remaining = max(0, photo_limit(chat_id) - u["photo_count"])
                if result.startswith("http"):
                    send_photo_url(chat_id, result, f"✅ Готово! Осталось фото: {remaining}")
                else:
                    # base64 — отправляем как файл
                    img_bytes = base64.b64decode(result)
                    requests.post(
                        f"{BASE_URL}/sendPhoto",
                        data={"chat_id": chat_id, "caption": f"✅ Готово! Осталось фото: {remaining}"},
                        files={"photo": ("image.png", img_bytes)}
                    )
            else:
                send(chat_id, "❌ Не удалось сгенерировать фото. Попробуй другой промпт или модель.")
        except Exception as e:
            send(chat_id, f"Ошибка генерации: {str(e)}")
        return

    # Команды
    if text.startswith("/start"):
        model_name = CLAUDE_MODEL_NAMES.get(u.get("model", "sonnet"), "⚡ Sonnet 4.6")
        send(chat_id,
            f"Привет, {name}! 👋\n"
            f"Я - твой личный AI-ассистент. Помогу с задачами, текстами, идеями и ответами на любые вопросы.\n\n"
            f"⚙️ Режим: 🗣 Дефолт\n"
            f"🧠 Модель: {model_name}\n\n"
            f"📌 Команды:\n"
            f"/help - список возможностей\n"
            f"/mode - сменить режим\n"
            f"/skills - специальные навыки\n"
            f"/lang - язык\n"
            f"/clear - очистить память\n"
            f"/sub - подписка\n"
            f"/ref - реферальная ссылка\n"
            f"/status - мой статус\n\n"
            f"💬 Пиши, что нужно - разберёмся!"
        )
        return

    if text == "/help":
        send(chat_id,
            "🤖 *AI-ассистент*\n\n"
            "*Режимы (/mode):*\n"
            "🗣 Дефолт - нейтральный ИИ\n"
            "💼 По делу - строго и кратко\n"
            "😊 Друг - по-дружески\n"
            "📝 Тесты - кратко и точно\n"
            "🖼 Фотографии - генерация AI-фото\n\n"
            "*Скиллы (/skills):*\n"
            "🎨 GPT Image - промпты\n"
            "💰 AI Sales - продажи\n"
            "📚 МГИМО БЖД - контрольные\n"
            "📖 Курсовая - курсовые МГИМО\n\n"
            "*Модели Claude (/model):*\n"
            "⚡ Sonnet 4.6 - быстрый (по умолчанию)\n"
            "🧠 Opus 4.7 - умнее (только подписка)\n\n"
            "*Фото (бесплатно):*\n"
            f"{FREE_PHOTO_LIMIT} фото | +{REFERRAL_BONUS_PHOTO} за реферала\n\n"
            "*Сообщения (бесплатно):*\n"
            f"{FREE_MSG_LIMIT} сообщений | +{REFERRAL_BONUS_MSG} за реферала\n\n"
            "/sub - подписка\n"
            "/ref - пригласи друга\n"
            "/status - твой статус",
            markdown=True
        )
        return

    if text == "/mode":
        send(chat_id, "Выбери режим:", [
            ["🗣 Дефолт", "💼 По делу"],
            ["😊 Друг", "📝 Тесты"],
            ["🖼 Фотографии"]
        ])
        return

    if text == "/skills":
        send(chat_id,
            "🛠 *Специальные навыки:*\n\n"
            "🎨 GPT Image - промпты для нейросетей\n"
            "💰 AI Sales - продажи AI-визуалов\n"
            "📚 МГИМО БЖД - контрольные работы\n"
            "📖 Курсовая - курсовые МГИМО\n\n"
            "Выбери навык:",
            [["🎨 GPT Image промпты"], ["💰 AI Visuals Sales"], ["📚 МГИМО БЖД", "📖 Курсовая МГИМО"], ["🗣 Дефолт"]],
            markdown=True
        )
        return

    if text == "/model":
        current = CLAUDE_MODEL_NAMES.get(u.get("model", "sonnet"), "⚡ Sonnet 4.6")
        send(chat_id, f"Текущая модель Claude: {current}\n\nВыбери модель:", [["⚡ Sonnet 4.6", "🧠 Opus 4.7"]])
        return

    if text == "/lang":
        send(chat_id, "Выбери язык:", [["🇷🇺 Русский", "🇬🇧 English", "🌐 Авто"]])
        return

    if text == "/clear":
        pending_clear.add(chat_id)
        send(chat_id, "Ты уверен? Вся история переписки будет удалена.", [["✅ Точно очистить", "❌ Нет"]])
        return

    if text == "/sub":
        if u.get("has_sub"):
            send(chat_id, "✅ У тебя активна подписка! Лимиты сняты.")
        else:
            rem_msg = max(0, msg_limit(chat_id) - u.get("msg_count", 0))
            rem_photo = max(0, photo_limit(chat_id) - u.get("photo_count", 0))
            send(chat_id,
                f"💳 *Подписка*\n\n"
                f"Осталось сообщений: {rem_msg}\n"
                f"Осталось фото: {rem_photo}\n\n"
                f"Для приобретения подписки пиши: @staremenow",
                markdown=True
            )
        return

    if text == "/ref":
        if not u.get("has_sub"):
            send(chat_id, "Реферальная система доступна только для подписчиков. Оформи подписку через /sub")
            return
        refs = len(u.get("referrals", []))
        bonus_msg = u.get("referral_bonus_msg", 0)
        bonus_photo = u.get("referral_bonus_photo", 0)
        bot_info = requests.get(f"{BASE_URL}/getMe").json()
        bot_username = bot_info.get("result", {}).get("username", "")
        ref_link = f"https://t.me/{bot_username}?start=ref{chat_id}"
        send(chat_id,
            f"🔗 *Реферальная программа*\n\n"
            f"За каждого приглашённого друга:\n"
            f"+{REFERRAL_BONUS_MSG} сообщений\n"
            f"+{REFERRAL_BONUS_PHOTO} фото\n\n"
            f"Твоя ссылка:\n{ref_link}\n\n"
            f"Приглашено друзей: {refs}\n"
            f"Бонусных сообщений: {bonus_msg}\n"
            f"Бонусных фото: {bonus_photo}",
            markdown=True
        )
        return

    if text == "/status":
        rem_msg = max(0, msg_limit(chat_id) - u.get("msg_count", 0))
        rem_photo = max(0, photo_limit(chat_id) - u.get("photo_count", 0))
        sub_status = "✅ Активна" if u.get("has_sub") else "❌ Нет"
        model_name = CLAUDE_MODEL_NAMES.get(u.get("model", "sonnet"), "⚡ Sonnet 4.6")
        photo_model = PHOTO_MODEL_NAMES.get(u.get("photo_model"), "не выбрана")
        mode_map = {
            "default": "🗣 Дефолт", "delo": "💼 По делу", "friend": "😊 Друг",
            "test": "📝 Тесты", "photo": "🖼 Фотографии",
            "skill_gpt": "🎨 GPT Image", "skill_sales": "💰 AI Sales",
            "skill_mgimo": "📚 МГИМО БЖД", "skill_coursework": "📖 Курсовая",
        }
        send(chat_id,
            f"📊 *Твой статус*\n\n"
            f"Режим: {mode_map.get(u.get('mode','default'), '🗣 Дефолт')}\n"
            f"Модель Claude: {model_name}\n"
            f"Модель фото: {photo_model}\n"
            f"Язык: {u.get('language', 'ru')}\n"
            f"Подписка: {sub_status}\n"
            f"Осталось сообщений: {rem_msg}\n"
            f"Осталось фото: {rem_photo}\n"
            f"История: {len(u.get('history', []))} сообщений",
            markdown=True
        )
        return

    # Выбор модели Claude
    if text == "⚡ Sonnet 4.6":
        u["model"] = "sonnet"
        send(chat_id, "Модель: ⚡ Sonnet 4.6 - быстрый и экономный.")
        return
    if text == "🧠 Opus 4.7":
        if not u.get("has_sub"):
            send(chat_id, "🔒 Opus 4.7 доступен только по подписке.\nОформи через /sub или пиши @staremenow")
            return
        u["model"] = "opus"
        send(chat_id, "Модель: 🧠 Opus 4.7 - максимальный интеллект.")
        return

    # Выбор языка
    if text == "🇷🇺 Русский":
        u["language"] = "ru"
        send(chat_id, "Язык: 🇷🇺 Русский")
        return
    if text == "🇬🇧 English":
        u["language"] = "en"
        send(chat_id, "Language: 🇬🇧 English")
        return
    if text == "🌐 Авто":
        u["language"] = "auto"
        send(chat_id, "Язык: 🌐 Авто")
        return

    # Выбор режима Фотографии
    if text == "🖼 Фотографии":
        if not can_photo(chat_id):
            send(chat_id,
                f"⚠️ У тебя закончились бесплатные фото ({FREE_PHOTO_LIMIT} шт.).\n\n"
                f"Оформи подписку через /sub или пригласи друга через /ref (+{REFERRAL_BONUS_PHOTO} фото)."
            )
            return
        # Сбрасываем режим и модель фото
        old_mode = u.get("mode")
        if old_mode != "photo":
            u["photo_model"] = None
        u["mode"] = "photo"
        u["history"] = []
        show_photo_model_menu(chat_id)
        return

    # Выбор модели фото
    if text in PHOTO_MODEL_BUTTONS:
        if u.get("mode") != "photo":
            u["mode"] = "photo"
        u["photo_model"] = PHOTO_MODEL_BUTTONS[text]
        model_name = PHOTO_MODEL_NAMES[PHOTO_MODEL_BUTTONS[text]]
        rem_photo = max(0, photo_limit(chat_id) - u.get("photo_count", 0))
        send(chat_id,
            f"✅ Модель выбрана: *{model_name}*\n\n"
            f"📸 *Как генерировать фото:*\n\n"
            f"1. Просто напиши промпт на русском или английском\n"
            f"2. Или прикрепи до 5 фото с подписью-промптом (референс)\n\n"
            f"*Примеры промптов:*\n"
            f"- «Девушка в красном платье на фоне Парижа, кинематографично»\n"
            f"- «Логотип кофейни, минимализм, золото и чёрный»\n"
            f"- «Поменяй фон на темно оранжевый закат» (с прикреплённым фото)\n\n"
            f"Осталось фото: {rem_photo}\n\n"
            f"Скидывай промпт! 👇",
            markdown=True
        )
        return

    # Остальные режимы/скиллы
    BUTTONS_MAP = {
        "🗣 Дефолт": ("default", "Режим: 🗣 Дефолт."),
        "💼 По делу": ("delo", "Режим: 💼 По делу. Чётко и по фактам."),
        "😊 Друг": ("friend", "Режим: 😊 Друг. Привет родной)"),
        "📝 Тесты": ("test", "Режим: 📝 Тесты. Скидывай вопрос!"),
        "🎨 GPT Image промпты": ("skill_gpt", "Скилл: 🎨 GPT Image. Скидывай идею!"),
        "💰 AI Visuals Sales": ("skill_sales", "Скилл: 💰 AI Sales. Чем помочь?"),
        "📚 МГИМО БЖД": ("skill_mgimo", None),
        "📖 Курсовая МГИМО": ("skill_coursework", None),
    }

    if text in BUTTONS_MAP:
        mode_key, reply_text = BUTTONS_MAP[text]
        if mode_key in ("skill_mgimo", "skill_coursework") and not can_use_mgimo(user_id, username):
            send(chat_id, "🔒 Этот скилл доступен только по запросу. Напиши @staremenow для получения доступа.")
            return
        # При смене режима сбрасываем модель фото
        if mode_key != "photo":
            u["photo_model"] = None
        u["mode"] = mode_key
        u["history"] = []
        if reply_text:
            send(chat_id, reply_text)
        else:
            send(chat_id, f"Режим активирован. Скидывай задачу!")
        return

    # Если режим фото но пришёл текст без фото
    if u.get("mode") == "photo":
        if not u.get("photo_model"):
            show_photo_model_menu(chat_id)
            return
        # Обрабатываем как промпт
        if not can_photo(chat_id):
            send(chat_id,
                f"⚠️ У тебя закончились бесплатные фото.\n"
                f"Оформи подписку через /sub или пригласи друга через /ref."
            )
            return
        prompt = text
        model_name = PHOTO_MODEL_NAMES.get(u["photo_model"], "GPT Image 2.0")
        send(chat_id, f"⏳ Генерирую...\nМодель: {model_name}")
        send_typing(chat_id)
        try:
            result = generate_photo(prompt, None, u["photo_model"])
            if result:
                u["photo_count"] = u.get("photo_count", 0) + 1
                remaining = max(0, photo_limit(chat_id) - u["photo_count"])
                if result.startswith("http"):
                    send_photo_url(chat_id, result, f"✅ Готово! Осталось фото: {remaining}")
                else:
                    img_bytes = base64.b64decode(result)
                    requests.post(
                        f"{BASE_URL}/sendPhoto",
                        data={"chat_id": chat_id, "caption": f"✅ Готово! Осталось фото: {remaining}"},
                        files={"photo": ("image.png", img_bytes)}
                    )
            else:
                send(chat_id, "❌ Не удалось сгенерировать фото. Попробуй другой промпт или модель.")
        except Exception as e:
            send(chat_id, f"Ошибка: {str(e)}")
        return

    # Проверка лимита сообщений
    if not can_msg(chat_id):
        send(chat_id,
            "⚠️ У тебя закончились бесплатные сообщения.\n\n"
            "Оформи подписку через /sub или пригласи друга через /ref."
        )
        return

    # Основной запрос к Claude
    u["history"].append({"role": "user", "content": text})
    if len(u["history"]) > 20:
        u["history"] = u["history"][-20:]

    send_typing(chat_id)

    try:
        model_id = CLAUDE_MODELS.get(u.get("model", "sonnet"), CLAUDE_MODELS["sonnet"])
        response = client.messages.create(
            model=model_id,
            max_tokens=2048,
            system=get_system(chat_id),
            messages=u["history"]
        )
        reply = response.content[0].text
        u["history"].append({"role": "assistant", "content": reply})
        u["msg_count"] = u.get("msg_count", 0) + 1
        send(chat_id, reply, markdown=True)
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
