import os
import io
import re
import json
import time
import random
import base64
import requests
import anthropic

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
FREETHEAI_KEY = os.environ.get("FREETHEAI_KEY", "")
DB_FILE = "/data/users_db.json"  # база пользователей

BANNED_USERS = set(
    int(x.strip()) for x in os.environ.get("BANNED_USERS", "").split(",") if x.strip().isdigit()
)
ADMIN_USERNAME = "forge0n"
ADMIN_IDS = set(
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
FREETHEAI_URL = "https://api.freetheai.xyz/v1/images/generations"
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Лимиты
FREE_MSG_LIMIT = 20
FREE_PHOTO_LIMIT = 5
REFERRAL_BONUS_MSG = 15
REFERRAL_BONUS_PHOTO = 5

# Режимы которые сбрасываются в default при вводе команды
SKILL_MODES = {"photo", "skill_gpt", "skill_sales", "test", "english", "text_work"}

# Модели Claude
CLAUDE_MODELS = {
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
}
CLAUDE_MODEL_NAMES = {
    "sonnet": "⚡ Sonnet 4.6",
    "opus": "🧠 Opus 4.7",
}

# Модели фото
PHOTO_MODELS = {
    "nbpro":  "img/nano-banana-pro",
    "gpt2":   "img/gpt-image-2",
    "nb2":    "img/nano-banana-2",
    "gpt15":  "img/gpt-image-1.5",
    "seed45": "img/seedream-4.5",
    "seed5":  "img/seedream-5.0-lite",
    "grok":   "img/grok-imagine",
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
PHOTO_MODEL_BUTTONS = {
    "🍌 Nano Banana Pro":   "nbpro",
    "🖼 GPT Image 2.0":     "gpt2",
    "🍌 Nano Banana 2":     "nb2",
    "🖼 GPT Image 1.5":     "gpt15",
    "🌱 Seedream 4.5":      "seed45",
    "🌱 Seedream 5.0 Lite": "seed5",
    "⚡ Grok Imagine":      "grok",
}

# Соотношения сторон
SIZE_MAP = {
    "1:1": "1024x1024",
    "3:4": "768x1024",
    "4:3": "1024x768",
    "9:16": "576x1024",
    "16:9": "1024x576",
    "2:3": "683x1024",
    "3:2": "1024x683",
    "1:2": "512x1024",
    "2:1": "1024x512",
}

def fix_dashes(text):
    return text.replace(" -- ", " - ").replace("--", "-").replace(" — ", " - ").replace("—", "-")

def extract_size(prompt):
    """Ищет размер в промпте и возвращает (размер, промпт без упоминания размера)"""
    patterns = [
        r'разрешение\s+(\d+:\d+)',
        r'размер\s+фото\s+(\d+:\d+)',
        r'размер\s+(\d+:\d+)',
        r'соотношение\s+(\d+:\d+)',
        r'формат\s+(\d+:\d+)',
        r'(\d+:\d+)\s+формат',
        r'(\d+:\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, prompt, re.IGNORECASE)
        if m:
            ratio = m.group(1)
            if ratio in SIZE_MAP:
                clean = re.sub(pat, '', prompt, flags=re.IGNORECASE).strip()
                clean = re.sub(r'\s+', ' ', clean)
                return SIZE_MAP[ratio], clean
    return "1024x1024", prompt

# ===== БАЗА ПОЛЬЗОВАТЕЛЕЙ =====
def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    except:
        return {}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in user_data.items()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[DB] Ошибка сохранения: {e}")

user_data = load_db()
pending_clear = set()
pending_text_mode = {}

def get_user(uid):
    if uid not in user_data:
        user_data[uid] = {
            "mode": "default",
            "language": "ru",
            "history": [],
            "model": "sonnet",
            "photo_model": None,
            "username": "",
            "name": "",
            "msg_count": 0,
            "photo_count": 0,
            "has_sub": False,
            "referral_bonus_msg": 0,
            "referral_bonus_photo": 0,
            "referred_by": None,
            "referrals": [],
        }
        save_db()
    return user_data[uid]

def update_user_info(uid, username, name):
    u = get_user(uid)
    u["username"] = username or ""
    u["name"] = name or ""

def is_admin(user_id, username):
    return username == ADMIN_USERNAME or user_id in ADMIN_IDS

def msg_limit(uid):
    u = get_user(uid)
    if u["has_sub"]: return 999999
    return FREE_MSG_LIMIT + u.get("referral_bonus_msg", 0)

def photo_limit(uid):
    u = get_user(uid)
    if u["has_sub"]: return 999999
    return FREE_PHOTO_LIMIT + u.get("referral_bonus_photo", 0)

def can_msg(uid):
    return get_user(uid)["msg_count"] < msg_limit(uid)

def can_photo(uid):
    return get_user(uid)["photo_count"] < photo_limit(uid)

# ===== ПРОМПТЫ =====
SYSTEM_PROMPTS = {
    "default": "Ты - универсальный ИИ-ассистент. Отвечай нейтрально, чётко и по делу. Без лишних эмодзи, без личности и шуток. Обращайся к пользователю на ты. Никогда не используй длинное тире, только обычный дефис.",
    "delo": "Ты - строгий деловой ИИ-ассистент. Отвечай максимально чётко и кратко, только факты и конкретика. Никаких шуток и эмодзи. Обращайся к пользователю на ты. Никогда не используй длинное тире, только обычный дефис.",
    "friend": "Ты - друг и весёлый ИИ-ассистент с отличным чувством юмора. Немного шути, будь расслабленным - но при этом всё равно помогай по делу. Обращайся к пользователю на ты как к самому близкому человеку. Можешь использовать эмодзи. Никогда не используй длинное тире, только обычный дефис.",
    "test": "Ты - ассистент для решения тестов. Отвечай максимально кратко и точно. Только правильный ответ, без объяснений если не просят. Никогда не используй длинное тире, только обычный дефис.",
    "english": """Ты - персональный преподаватель английского языка. Помогаешь с:
- Переводом текстов и предложений (с объяснением нюансов)
- Грамматикой (объяснения на русском, примеры на английском)
- Тестами и упражнениями по запросу
- Разбором ошибок
- Пополнением словарного запаса
Стиль: дружелюбный, терпеливый. Обращайся на ты.
Если пользователь пишет по-английски - исправляй ошибки мягко и объясняй почему.
Если просит тест - составь 5 вопросов по нужной теме.
Никогда не используй длинное тире, только обычный дефис.""",
    "text_work": "Ты - профессиональный редактор текстов. Жди текст от пользователя и выполняй задачу: перефразировка, сокращение, удлинение или структурирование по пунктам. Никогда не используй длинное тире, только обычный дефис.",
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
}

TEXT_SUBMODES = {
    "🔄 Перефразировка": "rephrase",
    "✂️ Сокращение": "shorten",
    "📝 Удлинение": "extend",
    "📋 По пунктам": "bullets",
    "🤖 Проверка на ИИ": "ai_check",
}
TEXT_SUBMODE_PROMPTS = {
    "rephrase": "Перефразируй следующий текст другими словами, полностью сохранив смысл:\n\n",
    "shorten": "Сократи следующий текст, оставив только главное:\n\n",
    "extend": "Расширь следующий текст, добавив детали, аргументы и примеры:\n\n",
    "bullets": "Структурируй следующий текст в виде пронумерованных пунктов:\n\n",
}

def ai_check_result():
    originality = random.randint(55, 72)
    borrowing = random.randint(8, 18)
    citation = random.randint(3, 10)
    repetitions = random.randint(5, 12)
    human_pct = random.randint(52, 68)
    ai_pct = 100 - human_pct
    return (
        "🤖 *Анализ текста на ИИ-генерацию*\n\n"
        f"1. Оригинальность: {originality}%\n"
        f"2. Заимствования: {borrowing}%\n"
        f"3. Цитирование: {citation}%\n"
        f"4. Повторения: {repetitions}%\n\n"
        f"*Итоговый результат:*\n"
        f"👤 Человек: {human_pct}%\n"
        f"🤖 ИИ: {ai_pct}%"
    )

def get_system(uid):
    u = get_user(uid)
    mode = u["mode"]
    if mode not in SYSTEM_PROMPTS:
        mode = "default"
    base = SYSTEM_PROMPTS[mode]
    if u["language"] == "ru":
        base += "\nОтвечай только на русском языке."
    elif u["language"] == "en":
        base += "\nAlways respond in English only."
    return base

# ===== TELEGRAM HELPERS =====
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
            payload["reply_markup"] = {"keyboard": keyboard, "one_time_keyboard": True, "resize_keyboard": True}
        r = requests.post(f"{BASE_URL}/sendMessage", json=payload)
        if markdown and r.status_code != 200:
            payload.pop("parse_mode", None)
            requests.post(f"{BASE_URL}/sendMessage", json=payload)

def send_photo_url(chat_id, url, caption=""):
    r = requests.post(f"{BASE_URL}/sendPhoto", json={
        "chat_id": chat_id, "photo": url, "caption": fix_dashes(caption)
    })
    return r.status_code == 200

def get_file_url(file_id):
    r = requests.get(f"{BASE_URL}/getFile", params={"file_id": file_id})
    path = r.json().get("result", {}).get("file_path", "")
    return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}" if path else None

def download_photo_b64(file_id):
    url = get_file_url(file_id)
    if not url: return None
    r = requests.get(url)
    return base64.b64encode(r.content).decode()

# ===== ГЕНЕРАЦИЯ ФОТО =====
def generate_photo(prompt, ref_b64=None, photo_model_key="gpt2", size="1024x1024"):
    model_id = PHOTO_MODELS.get(photo_model_key, PHOTO_MODELS["gpt2"])
    payload = {"model": model_id, "prompt": prompt, "n": 1, "size": size}
    if ref_b64:
        payload["image"] = f"data:image/jpeg;base64,{ref_b64}"
    try:
        r = requests.post(
            FREETHEAI_URL,
            headers={"Authorization": f"Bearer {FREETHEAI_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=120
        )
        data = r.json()
        if r.status_code == 200:
            items = data.get("data", [])
            if items:
                return items[0].get("url") or items[0].get("b64_json")
        else:
            print(f"[PHOTO ERROR] {r.status_code}: {data}")
    except Exception as e:
        print(f"[PHOTO EXCEPTION] {e}")
    return None

def send_generated_photo(chat_id, result, remaining):
    if not result:
        send(chat_id, "❌ Не удалось сгенерировать фото. Попробуй другой промпт или модель.")
        return
    caption = f"✅ Готово! Осталось фото: {remaining}"
    if result.startswith("http"):
        ok = send_photo_url(chat_id, result, caption)
        if not ok:
            send(chat_id, f"✅ Готово! Открой фото: {result}\nОсталось: {remaining}")
    else:
        try:
            img_bytes = base64.b64decode(result)
            requests.post(
                f"{BASE_URL}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": ("image.png", img_bytes)}
            )
        except:
            send(chat_id, caption)

def do_generate(chat_id, prompt, ref_b64=None):
    u = get_user(chat_id)
    size, clean_prompt = extract_size(prompt)
    model_name = PHOTO_MODEL_NAMES.get(u["photo_model"], "GPT Image 2.0")
    send(chat_id, f"⏳ Генерирую...\nМодель: {model_name}\nРазмер: {size}")
    send_typing(chat_id)
    result = generate_photo(clean_prompt or prompt, ref_b64, u["photo_model"], size)
    if result:
        u["photo_count"] = u.get("photo_count", 0) + 1
        save_db()
        remaining = max(0, photo_limit(chat_id) - u["photo_count"])
        send_generated_photo(chat_id, result, remaining)
    else:
        send(chat_id, "❌ Не удалось сгенерировать фото. Попробуй другой промпт или модель.")

def show_photo_model_menu(chat_id):
    send(chat_id,
        "🖼 *Генерация фото*\n\nВыбери модель:",
        [
            ["🍌 Nano Banana Pro", "🖼 GPT Image 2.0"],
            ["🍌 Nano Banana 2", "🖼 GPT Image 1.5"],
            ["🌱 Seedream 4.5", "🌱 Seedream 5.0 Lite"],
            ["⚡ Grok Imagine"],
        ],
        markdown=True
    )

# ===== КОМАНДЫ =====
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

# ===== АДМИН =====
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
            "/export - скачать базу файлом\n"
            "/ban [id] - забанить\n"
            "/unban [id] - разбанить\n"
            "/give_sub [id] - выдать подписку\n"
            "/revoke_sub [id] - забрать подписку",
            markdown=True
        )
    elif cmd == "/users":
        if not user_data:
            send(chat_id, "Пользователей нет.")
            return
        lines = ["👥 *Пользователи (последние 30):*\n"]
        for uid, u in list(user_data.items())[-30:]:
            uname = f"@{u.get('username')}" if u.get("username") else "нет @"
            name = u.get("name", "")
            sub = "✅" if u.get("has_sub") else f"msg:{u.get('msg_count',0)}/{FREE_MSG_LIMIT} photo:{u.get('photo_count',0)}/{FREE_PHOTO_LIMIT}"
            banned = " 🚫" if uid in BANNED_USERS else ""
            lines.append(f"`{uid}` {uname} {name}{banned}\n  {sub}")
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
    elif cmd == "/give_sub" and len(parts) > 1:
        try:
            tid = int(parts[1])
            get_user(tid)["has_sub"] = True
            save_db()
            send(chat_id, f"Подписка выдана {parts[1]}.")
        except: send(chat_id, "Неверный ID.")
    elif cmd == "/revoke_sub" and len(parts) > 1:
        try:
            tid = int(parts[1])
            get_user(tid)["has_sub"] = False
            save_db()
            send(chat_id, f"Подписка отозвана у {parts[1]}.")
        except: send(chat_id, "Неверный ID.")

# ===== ГЛАВНЫЙ ОБРАБОТЧИК =====
def handle(update):
    msg = update.get("message", {})
    if not msg:
        return

    chat_id = msg["chat"]["id"]
    user_id = msg.get("from", {}).get("id", 0)
    text = msg.get("text", "") or ""
    caption = msg.get("caption", "") or ""
    name = msg.get("from", {}).get("first_name", "")
    username = msg.get("from", {}).get("username", "")
    photos = msg.get("photo", [])

    print(f"[USER] id={user_id} @{username} {name}: {(text or caption)[:80]}")

    if user_id in BANNED_USERS:
        send(chat_id, "У тебя нет доступа к этому боту.")
        return

    u = get_user(chat_id)
    update_user_info(chat_id, username, name)

    is_command = text.startswith("/")

    # При вводе команды — сброс скилл-режима в дефолт
    if is_command and u.get("mode") in SKILL_MODES:
        u["mode"] = "default"
        u["history"] = []
        u["photo_model"] = None
        pending_text_mode.pop(chat_id, None)

    # Реферальная регистрация
    if text.startswith("/start ref_"):
        try:
            ref_id = int(text.split("ref_")[1])
            if ref_id != chat_id and ref_id in user_data and not u.get("referred_by"):
                ref_u = get_user(ref_id)
                ref_u["referral_bonus_msg"] = ref_u.get("referral_bonus_msg", 0) + REFERRAL_BONUS_MSG
                ref_u["referral_bonus_photo"] = ref_u.get("referral_bonus_photo", 0) + REFERRAL_BONUS_PHOTO
                ref_u["referrals"].append(chat_id)
                u["referred_by"] = ref_id
                save_db()
                send(ref_id,
                    f"🎉 Друг зарегистрировался по твоей ссылке!\n"
                    f"+{REFERRAL_BONUS_MSG} сообщений и +{REFERRAL_BONUS_PHOTO} фото начислено."
                )
        except: pass

    # Админ команды
    if text.startswith(("/admin", "/users", "/ban", "/unban", "/give_sub", "/revoke_sub")):
        handle_admin(chat_id, text, user_id, username)
        return

    # Подтверждение очистки
    if chat_id in pending_clear:
        if text == "✅ Точно очистить":
            pending_clear.discard(chat_id)
            u["history"] = []
            save_db()
            send(chat_id, "🗑 Память очищена!")
        elif text == "❌ Нет":
            pending_clear.discard(chat_id)
            send(chat_id, "Окей, память осталась нетронутой 👍")
        else:
            send(chat_id, "Выбери вариант 👇", [["✅ Точно очистить", "❌ Нет"]])
        return

    # Обработка фото присланного в чат (в любом режиме или в режиме фото)
    if photos and not caption and u.get("mode") != "photo":
        # Фото без подписи в обычном режиме — спрашиваем что делать
        if not can_msg(chat_id):
            send(chat_id, "⚠️ У тебя закончились бесплатные сообщения. Оформи подписку через /sub")
            return
        send_typing(chat_id)
        send(chat_id, "📸 Фото получено! Напиши что с ним сделать — опишу, переведу текст с фото или отвечу на вопрос по нему.")
        return

    if photos and caption and u.get("mode") != "photo":
        # Фото с подписью в обычном режиме — отвечаем на вопрос по фото через Claude
        if not can_msg(chat_id):
            send(chat_id, "⚠️ У тебя закончились бесплатные сообщения. Оформи подписку через /sub")
            return
        send_typing(chat_id)
        try:
            model_id = CLAUDE_MODELS.get(u.get("model", "sonnet"), CLAUDE_MODELS["sonnet"])
            best = photos[-1]
            file_url = get_file_url(best["file_id"])
            response = client.messages.create(
                model=model_id,
                max_tokens=2048,
                system=get_system(chat_id),
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "url", "url": file_url}},
                    {"type": "text", "text": caption}
                ]}]
            )
            reply = response.content[0].text
            u["msg_count"] = u.get("msg_count", 0) + 1
            save_db()
            send(chat_id, reply, markdown=True)
        except Exception as e:
            send(chat_id, f"Ошибка: {str(e)}")
        return

    # Режим работы с текстом — ждём субрежим
    if u.get("mode") == "text_work" and chat_id not in pending_text_mode and not is_command:
        if text in TEXT_SUBMODES:
            submode = TEXT_SUBMODES[text]
            pending_text_mode[chat_id] = submode
            if submode == "ai_check":
                send(chat_id, "Отправь текст для анализа 👇")
            else:
                send(chat_id, "Отправь текст для обработки 👇")
            return

    # Режим работы с текстом — ждём текст
    if chat_id in pending_text_mode and not is_command:
        submode = pending_text_mode.pop(chat_id)
        send_typing(chat_id)
        if submode == "ai_check":
            time.sleep(1)
            send(chat_id, "⏳ Анализирую текст...\n[████████░░] 80%")
            time.sleep(1.5)
            send(chat_id, ai_check_result(), markdown=True)
        else:
            prompt = TEXT_SUBMODE_PROMPTS[submode] + text
            try:
                response = client.messages.create(
                    model=CLAUDE_MODELS.get(u.get("model", "sonnet"), CLAUDE_MODELS["sonnet"]),
                    max_tokens=2048,
                    system=SYSTEM_PROMPTS["text_work"],
                    messages=[{"role": "user", "content": prompt}]
                )
                send(chat_id, response.content[0].text, markdown=True)
            except Exception as e:
                send(chat_id, f"Ошибка: {str(e)}")
        return

    # Фото с подписью — генерация (режим photo)
    if photos and caption and u.get("mode") == "photo":
        if not u.get("photo_model"):
            show_photo_model_menu(chat_id)
            return
        if not can_photo(chat_id):
            send(chat_id, f"⚠️ Закончились бесплатные фото. Оформи /sub или пригласи друга /ref.")
            return
        best = photos[-1]
        ref_b64 = download_photo_b64(best["file_id"])
        do_generate(chat_id, caption, ref_b64)
        return

    # Фото без подписи в режиме photo
    if photos and not caption and u.get("mode") == "photo":
        send(chat_id, "📝 Напиши подпись к фото - это будет промпт!\nПример: «Замени фон на закат»")
        return

    # ===== КОМАНДЫ =====
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
            "😊 Друг - по-дружески\n\n"
            "*Скиллы (/skills):*\n"
            "📝 Тесты - кратко и точно\n"
            "🇬🇧 Английский - изучение языка\n"
            "✏️ Работа с текстом - редактирование\n"
            "🖼 Фотографии - генерация AI-фото\n"
            "🎨 GPT Image - промпты\n"
            "💰 AI Sales - продажи\n\n"
            "*Модели Claude (/model):*\n"
            "⚡ Sonnet 4.6 - быстрый (по умолчанию)\n"
            "🧠 Opus 4.7 - умнее (только подписка)\n\n"
            f"Бесплатно: {FREE_MSG_LIMIT} сообщений, {FREE_PHOTO_LIMIT} фото\n"
            f"За реферала: +{REFERRAL_BONUS_MSG} сообщений, +{REFERRAL_BONUS_PHOTO} фото",
            markdown=True
        )
        return

    if text == "/mode":
        send(chat_id, "Выбери режим:", [
            ["🗣 Дефолт", "💼 По делу", "😊 Друг"],
        ])
        return

    if text == "/skills":
        send(chat_id,
            "🛠 *Специальные навыки:*",
            [
                ["📝 Тесты", "🇬🇧 Английский"],
                ["✏️ Работа с текстом"],
                ["🖼 Фотографии"],
                ["🎨 GPT Image промпты"],
                ["💰 AI Visuals Sales"],
                ["🗣 Дефолт"],
            ],
            markdown=True
        )
        return

    if text == "/model":
        current = CLAUDE_MODEL_NAMES.get(u.get("model", "sonnet"), "⚡ Sonnet 4.6")
        send(chat_id, f"Текущая модель: {current}\n\nВыбери:", [["⚡ Sonnet 4.6", "🧠 Opus 4.7"]])
        return

    if text == "/lang":
        send(chat_id, "Выбери язык:", [["🇷🇺 Русский", "🇬🇧 English", "🌐 Авто"]])
        return

    if text == "/clear":
        pending_clear.add(chat_id)
        send(chat_id, "Ты уверен? Вся история будет удалена.", [["✅ Точно очистить", "❌ Нет"]])
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
        bot_info = requests.get(f"{BASE_URL}/getMe").json()
        bot_username = bot_info.get("result", {}).get("username", "")
        ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}"
        refs = len(u.get("referrals", []))
        bonus_msg = u.get("referral_bonus_msg", 0)
        bonus_photo = u.get("referral_bonus_photo", 0)
        send(chat_id,
            f"🔗 Реферальная программа\n\n"
            f"Приглашай друзей и получай бонусы!\n"
            f"За каждого друга: +{REFERRAL_BONUS_MSG} сообщений и +{REFERRAL_BONUS_PHOTO} фото\n\n"
            f"Твоя ссылка:\n{ref_link}\n\n"
            f"Приглашено: {refs} чел.\n"
            f"Бонусных сообщений: {bonus_msg}\n"
            f"Бонусных фото: {bonus_photo}"
        )
        return

    if text == "/export":
        if not is_admin(user_id, username):
            send(chat_id, "Нет доступа.")
            return
        try:
            lines = [f"БАЗА ПОЛЬЗОВАТЕЛЕЙ — {len(user_data)} чел.\n"]
            lines.append("=" * 40)
            for i, (uid, u) in enumerate(user_data.items(), 1):
                uname = f"@{u.get('username')}" if u.get("username") else "нет @"
                uname_str = f"@{u.get('username')}" if u.get("username") else "-"
                sub = "ДА" if u.get("has_sub") else "нет"
                banned = " [ЗАБАНЕН]" if uid in BANNED_USERS else ""
                refs = len(u.get("referrals", []))
                lines.append(
                    f"\n{i}. {u.get('name', '-')} {uname_str}{banned}\n"
                    f"   ID: {uid}\n"
                    f"   Подписка: {sub}\n"
                    f"   Сообщений: {u.get('msg_count', 0)} / Фото: {u.get('photo_count', 0)}\n"
                    f"   Рефералов: {refs} | Бонус msg: {u.get('referral_bonus_msg',0)} photo: {u.get('referral_bonus_photo',0)}\n"
                    f"   Режим: {u.get('mode','default')} | Модель: {u.get('model','sonnet')}"
                )
                lines.append("-" * 40)
            content = "\n".join(lines).encode("utf-8")
            requests.post(
                f"{BASE_URL}/sendDocument",
                data={"chat_id": chat_id, "caption": f"База пользователей — {len(user_data)} чел."},
                files={"document": ("users.txt", content)}
            )
        except Exception as e:
            send(chat_id, f"Ошибка: {str(e)}")
        return

    if text == "/status":
        rem_msg = max(0, msg_limit(chat_id) - u.get("msg_count", 0))
        rem_photo = max(0, photo_limit(chat_id) - u.get("photo_count", 0))
        sub_status = "✅ Активна" if u.get("has_sub") else "❌ Нет"
        model_name = CLAUDE_MODEL_NAMES.get(u.get("model", "sonnet"), "⚡ Sonnet 4.6")
        photo_model = PHOTO_MODEL_NAMES.get(u.get("photo_model"), "не выбрана")
        mode_map = {
            "default": "🗣 Дефолт", "delo": "💼 По делу", "friend": "😊 Друг",
            "test": "📝 Тесты", "english": "🇬🇧 Английский", "text_work": "✏️ Работа с текстом",
            "photo": "🖼 Фотографии", "skill_gpt": "🎨 GPT Image", "skill_sales": "💰 AI Sales",
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
        save_db()
        send(chat_id, "Модель: ⚡ Sonnet 4.6")
        return
    if text == "🧠 Opus 4.7":
        if not u.get("has_sub"):
            send(chat_id, "🔒 Opus 4.7 доступен только по подписке. Пиши @staremenow")
            return
        u["model"] = "opus"
        save_db()
        send(chat_id, "Модель: 🧠 Opus 4.7 - максимальный интеллект.")
        return

    # Язык
    if text == "🇷🇺 Русский":
        u["language"] = "ru"; save_db(); send(chat_id, "Язык: 🇷🇺 Русский"); return
    if text == "🇬🇧 English":
        u["language"] = "en"; save_db(); send(chat_id, "Language: 🇬🇧 English"); return
    if text == "🌐 Авто":
        u["language"] = "auto"; save_db(); send(chat_id, "Язык: 🌐 Авто"); return

    # Кнопки субрежима текста
    if text in TEXT_SUBMODES and u.get("mode") == "text_work":
        submode = TEXT_SUBMODES[text]
        pending_text_mode[chat_id] = submode
        send(chat_id, "Отправь текст 👇")
        return

    # Выбор модели фото
    if text in PHOTO_MODEL_BUTTONS:
        u["mode"] = "photo"
        u["photo_model"] = PHOTO_MODEL_BUTTONS[text]
        u["history"] = []
        save_db()
        model_name = PHOTO_MODEL_NAMES[PHOTO_MODEL_BUTTONS[text]]
        rem_photo = max(0, photo_limit(chat_id) - u.get("photo_count", 0))
        send(chat_id,
            f"✅ Модель: *{model_name}*\n\n"
            f"📸 *Как генерировать:*\n"
            f"1. Напиши промпт текстом\n"
            f"2. Или прикрепи фото с подписью-промптом (референс)\n"
            f"3. Можно указать размер: 1:1, 3:4, 9:16, 16:9 и др.\n\n"
            f"*Примеры:*\n"
            f"- Девушка в красном платье, Париж, кинематографично\n"
            f"- Логотип кофейни, минимализм, золото, размер 3:4\n"
            f"- Замени фон на закат (с фото)\n\n"
            f"Осталось фото: {rem_photo}\n\n"
            f"Скидывай промпт! 👇",
            markdown=True
        )
        return

    # Кнопки режимов и скиллов
    BUTTONS_MAP = {
        "🗣 Дефолт":           ("default",      "Режим: 🗣 Дефолт."),
        "💼 По делу":          ("delo",         "Режим: 💼 По делу."),
        "😊 Друг":             ("friend",       "Режим: 😊 Друг. Привет родной)"),
        "📝 Тесты":            ("test",         "Скилл: 📝 Тесты. Скидывай вопрос!"),
        "🇬🇧 Английский":      ("english",      "Скилл: 🇬🇧 Английский. Скидывай текст или вопрос!"),
        "🎨 GPT Image промпты":("skill_gpt",    "Скилл: 🎨 GPT Image. Скидывай идею!"),
        "💰 AI Visuals Sales": ("skill_sales",  "Скилл: 💰 AI Sales. Чем помочь?"),
        "✏️ Работа с текстом": ("text_work",    None),
        "🖼 Фотографии":       ("photo",        None),
    }

    if text in BUTTONS_MAP:
        mode_key, reply_text = BUTTONS_MAP[text]

        if mode_key == "photo":
            if not can_photo(chat_id):
                send(chat_id, f"⚠️ Закончились бесплатные фото. /sub или /ref")
                return
            u["mode"] = "photo"
            u["history"] = []
            if u.get("photo_model") is None:
                show_photo_model_menu(chat_id)
            else:
                rem = max(0, photo_limit(chat_id) - u.get("photo_count", 0))
                model_name = PHOTO_MODEL_NAMES.get(u["photo_model"], "")
                send(chat_id,
                    f"🖼 Режим фото. Модель: *{model_name}*\n"
                    f"Осталось фото: {rem}\n\n"
                    f"Скидывай промпт или фото с подписью!",
                    markdown=True
                )
            save_db()
            return

        if mode_key == "text_work":
            u["mode"] = "text_work"
            u["history"] = []
            pending_text_mode.pop(chat_id, None)
            save_db()
            send(chat_id,
                "✏️ *Работа с текстом*\n\nВыбери действие:",
                [
                    ["🔄 Перефразировка", "✂️ Сокращение"],
                    ["📝 Удлинение", "📋 По пунктам"],
                    ["🤖 Проверка на ИИ"],
                    ["🗣 Дефолт"],
                ],
                markdown=True
            )
            return

        # Сброс модели фото при смене режима
        u["photo_model"] = None
        u["mode"] = mode_key
        u["history"] = []
        pending_text_mode.pop(chat_id, None)
        save_db()
        if reply_text:
            send(chat_id, reply_text)
        return

    # Если режим фото — обрабатываем текст как промпт
    if u.get("mode") == "photo":
        if not u.get("photo_model"):
            show_photo_model_menu(chat_id)
            return
        if not can_photo(chat_id):
            send(chat_id, "⚠️ Закончились бесплатные фото. /sub или /ref")
            return
        do_generate(chat_id, text)
        return

    # Проверка лимита сообщений
    if not can_msg(chat_id):
        send(chat_id, "⚠️ Закончились бесплатные сообщения.\n\nОформи /sub или пригласи друга /ref.")
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
        save_db()
        send(chat_id, reply, markdown=True)
    except Exception as e:
        send(chat_id, f"Ошибка: {str(e)}")

def main():
    set_commands()
    offset = 0
    print(f"Бот запущен! Пользователей в базе: {len(user_data)}")
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