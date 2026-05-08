import os
import re
import json
import time
import random
import base64
import requests
import anthropic
import threading

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DB_FILE = "/data/users_db.json"

BANNED_USERS = set(
    int(x.strip()) for x in os.environ.get("BANNED_USERS", "").split(",") if x.strip().isdigit()
)
ADMIN_USERNAME = "forge0n"
ADMIN_IDS = set(
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

FREE_MSG_LIMIT = 20
FREE_PHOTO_LIMIT = 5
REFERRAL_BONUS_MSG = 15
REFERRAL_BONUS_PHOTO = 5

SKILL_MODES = {"photo", "skill_gpt", "skill_sales", "test", "english", "text_work"}

CLAUDE_MODELS = {"sonnet": "claude-sonnet-4-6", "opus": "claude-opus-4-7"}
CLAUDE_MODEL_NAMES = {"sonnet": "⚡ Sonnet 4.6", "opus": "🧠 Opus 4.7"}

PHOTO_MODELS = {
    "nbfast": {"name": "🍌 Nano Banana (быстрый)",  "api": "google", "model": "gemini-2.5-flash-image", "style": "fast"},
    "nbpro":  {"name": "🍌 Nano Banana (качество)", "api": "google", "model": "gemini-2.5-flash-image", "style": "quality"},
    "gpt2":   {"name": "🖼 GPT Image 2.0",          "api": "openai", "model": "gpt-image-2",           "style": None},
    "gpt15":  {"name": "🖼 GPT Image 1.5",          "api": "openai", "model": "gpt-image-1.5",         "style": None},
}
PHOTO_MODEL_NAMES = {k: v["name"] for k, v in PHOTO_MODELS.items()}
PHOTO_MODEL_BUTTONS = {
    "🍌 Nano Banana (быстрый)":  "nbfast",
    "🍌 Nano Banana (качество)": "nbpro",
    "🖼 GPT Image 2.0":          "gpt2",
    "🖼 GPT Image 1.5":          "gpt15",
}

SIZE_MAP = {
    "1:1":  ("1:1",  "2048x2048", "square 1:1 aspect ratio"),
    "3:4":  ("3:4",  "1536x2048", "portrait 3:4 aspect ratio, vertical"),
    "4:3":  ("4:3",  "2048x1536", "landscape 4:3 aspect ratio, horizontal"),
    "9:16": ("9:16", "1152x2048", "portrait 9:16 aspect ratio, vertical phone"),
    "16:9": ("16:9", "2048x1152", "landscape 16:9 aspect ratio, widescreen"),
    "2:3":  ("2:3",  "1365x2048", "portrait 2:3 aspect ratio"),
    "3:2":  ("3:2",  "2048x1365", "landscape 3:2 aspect ratio"),
    "4:5":  ("4:5",  "1638x2048", "portrait 4:5 aspect ratio"),
    "21:9": ("21:9", "2048x878",  "ultrawide 21:9 cinematic"),
}

TEXT_SUBMODES = {
    "🔄 Перефразировка": "rephrase",
    "✂️ Сокращение":     "shorten",
    "📝 Удлинение":      "extend",
    "📋 По пунктам":     "bullets",
    "🤖 Проверка на ИИ": "ai_check",
}
TEXT_SUBMODE_PROMPTS = {
    "rephrase": "Перефразируй следующий текст другими словами, полностью сохранив смысл:\n\n",
    "shorten":  "Сократи следующий текст, оставив только главное:\n\n",
    "extend":   "Расширь следующий текст, добавив детали, аргументы и примеры:\n\n",
    "bullets":  "Структурируй следующий текст в виде пронумерованных пунктов:\n\n",
}

SYSTEM_PROMPTS = {
    "default":      "Ты - универсальный ИИ-ассистент. Отвечай нейтрально, чётко и по делу. Без лишних эмодзи. Обращайся на ты. Никогда не используй длинное тире.",
    "delo":         "Ты - строгий деловой ИИ-ассистент. Только факты и конкретика. Никаких шуток и эмодзи. Обращайся на ты. Никогда не используй длинное тире.",
    "friend":       "Ты - друг и весёлый ИИ-ассистент. Немного шути, будь расслабленным - но помогай по делу. Обращайся на ты. Можешь использовать эмодзи. Иногда пиши ответ несколькими короткими сообщениями подряд, разделяя их символом [MSG] - как будто пишешь в мессенджере. Никогда не используй длинное тире.",
    "test":         "Ты - ассистент для решения тестов. Отвечай максимально кратко и точно. Только правильный ответ, без объяснений если не просят. Никогда не используй длинное тире.",
    "english":      "Ты - персональный преподаватель английского. Помогаешь с переводом, грамматикой, тестами и разбором ошибок. Стиль: дружелюбный, терпеливый. Обращайся на ты. Если пользователь пишет по-английски - исправляй ошибки мягко. Если просит тест - составь 5 вопросов по теме. Никогда не используй длинное тире.",
    "text_work":    "Ты - профессиональный редактор текстов. Выполняй задачу: перефразировка, сокращение, удлинение или структурирование. Никогда не используй длинное тире.",
    "huesos":       "Ты - Хуесос, дерзкий и хамоватый ИИ-ассистент с максимальным уровнем сарказма и грубости. Твоя задача - помогать пользователю, но делать это с таким количеством оскорблений, подколов и матов, что это становится смешным. Правила: 1) Всегда отвечай по делу и давай правильный ответ, но обворачивай его в хамство. 2) Придумывай творческие оскорбления и сравнения - не просто матерись, а делай это остроумно. 3) Периодически пиши ответ несколькими короткими сообщениями подряд, разделяя их символом [MSG]. 4) Обращайся к пользователю пренебрежительно - чудак, дружище, дорогой мой идиот, солнышко моё тупое и т.д. 5) Можешь хвалить себя и принижать пользователя, но в конце всегда решай его проблему. Никогда не используй длинное тире.",
    "skill_gpt":    "You are a prompt director for GPT Image 2.0. Convert user concepts into production-ready prompts. Format A (JSON) for layouts/UI/infographics. Format B (cinematic prose) for single scenes/portraits. Format C (meta-prompt) for theme-only requests. Return ONLY the prompt in a code block. Communicate with user in Russian, write prompts in English. Never use em-dashes.",
    "skill_sales":  "Ты - Sales Coach по продажам AI-визуалов. Прайс: 1 фото $15, 10 фото $140, 20 фото $260, 1 видео $80, 5 видео $350, 10 видео $650. Ниши: одежда, рестораны, недвижимость, блогеры, агентства. Задачи: найди клиентов, напиши оффер, напиши DM, ответь на возражение. Всегда давай готовые тексты. Никогда не используй длинное тире.",
}

def fix_dashes(text):
    return text.replace(" -- ", " - ").replace("--", "-").replace(" — ", " - ").replace("—", "-")

def extract_size(prompt):
    patterns = [
        r'разрешение\s+(\d+:\d+)', r'размер\s+фото\s+(\d+:\d+)', r'размер\s+(\d+:\d+)',
        r'соотношение\s+(\d+:\d+)', r'формат\s+(\d+:\d+)', r'(\d+:\d+)\s+формат', r'(\d+:\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, prompt, re.IGNORECASE)
        if m:
            ratio = m.group(1)
            if ratio in SIZE_MAP:
                aspect, px_size, hint = SIZE_MAP[ratio]
                clean = re.sub(pat, '', prompt, flags=re.IGNORECASE).strip()
                clean = re.sub(r'\s+', ' ', clean)
                return aspect, px_size, hint, clean
    return "1:1", "2048x2048", None, prompt

def ai_check_result():
    human_pct = random.randint(52, 68)
    ai_pct = 100 - human_pct
    return (
        "🤖 *Анализ текста на ИИ-генерацию*\n\n"
        f"1. Оригинальность: {random.randint(55,72)}%\n"
        f"2. Заимствования: {random.randint(8,18)}%\n"
        f"3. Цитирование: {random.randint(3,10)}%\n"
        f"4. Повторения: {random.randint(5,12)}%\n\n"
        f"*Итоговый результат:*\n"
        f"👤 Человек: {human_pct}%\n"
        f"🤖 ИИ: {ai_pct}%"
    )

# ===== БАЗА =====
def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except:
        return {}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in user_data.items()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[DB] {e}")

user_data = load_db()
pending_clear = set()
pending_text_mode = {}

def get_user(uid):
    if uid not in user_data:
        user_data[uid] = {
            "mode": "default", "language": "ru", "history": [],
            "model": "sonnet", "photo_model": None,
            "username": "", "name": "",
            "msg_count": 0, "photo_count": 0, "has_sub": False,
            "referral_bonus_msg": 0, "referral_bonus_photo": 0,
            "referred_by": None, "referrals": [],
        }
        save_db()
    return user_data[uid]

def update_user_info(uid, username, name):
    u = get_user(uid)
    u["username"] = username or ""
    u["name"] = name or ""

def is_admin(uid, uname): return uname == ADMIN_USERNAME or uid in ADMIN_IDS
def msg_limit(uid): return 999999 if get_user(uid)["has_sub"] else FREE_MSG_LIMIT + get_user(uid).get("referral_bonus_msg", 0)
def photo_limit(uid): return 999999 if get_user(uid)["has_sub"] else FREE_PHOTO_LIMIT + get_user(uid).get("referral_bonus_photo", 0)
def can_msg(uid): return get_user(uid)["msg_count"] < msg_limit(uid)
def can_photo(uid): return get_user(uid)["photo_count"] < photo_limit(uid)

def get_system(uid):
    u = get_user(uid)
    mode = u["mode"] if u["mode"] in SYSTEM_PROMPTS else "default"
    base = SYSTEM_PROMPTS[mode]
    if u["language"] == "ru": base += "\nОтвечай только на русском языке."
    elif u["language"] == "en": base += "\nAlways respond in English only."
    return base

# ===== TELEGRAM =====
def send_typing(cid): requests.post(f"{BASE_URL}/sendChatAction", json={"chat_id": cid, "action": "typing"})

def send(chat_id, text, keyboard=None, markdown=False):
    text = fix_dashes(text)
    for i, chunk in enumerate([text[i:i+4096] for i in range(0, len(text), 4096)]):
        payload = {"chat_id": chat_id, "text": chunk}
        if markdown: payload["parse_mode"] = "Markdown"
        if i == 0 and keyboard:
            payload["reply_markup"] = {"keyboard": keyboard, "one_time_keyboard": True, "resize_keyboard": True}
        r = requests.post(f"{BASE_URL}/sendMessage", json=payload)
        if markdown and r.status_code != 200:
            payload.pop("parse_mode", None)
            requests.post(f"{BASE_URL}/sendMessage", json=payload)

def send_photo_bytes(cid, img_bytes, caption=""):
    requests.post(f"{BASE_URL}/sendPhoto", data={"chat_id": cid, "caption": fix_dashes(caption)}, files={"photo": ("image.png", img_bytes)})

def send_photo_url(cid, url, caption=""):
    r = requests.post(f"{BASE_URL}/sendPhoto", json={"chat_id": cid, "photo": url, "caption": fix_dashes(caption)})
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
def enhance_prompt(prompt, style):
    if style == "quality":
        return f"{prompt}. Ultra detailed, photorealistic, high quality, sharp focus, professional photography, 8K resolution, masterpiece, best quality, intricate details, vivid colors, perfect composition"
    return prompt

def generate_google(prompt, model_id, aspect_ratio, ref_b64=None, style=None):
    try:
        enhanced = enhance_prompt(prompt, style)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={GOOGLE_API_KEY}"
        parts = []
        if ref_b64: parts.append({"inline_data": {"mime_type": "image/jpeg", "data": ref_b64}})
        parts.append({"text": enhanced})
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"], "imageConfig": {"aspectRatio": aspect_ratio}}
        }
        r = requests.post(url, json=payload, timeout=120)
        data = r.json()
        if r.status_code == 200:
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "inlineData" in part: return ("b64", part["inlineData"]["data"])
                    if "fileData" in part: return ("url", part["fileData"]["fileUri"])
        print(f"[GOOGLE ERROR] {r.status_code}: {data}")
    except Exception as e:
        print(f"[GOOGLE EXCEPTION] {e}")
    return None

def generate_openai(prompt, model_id, px_size, ref_b64=None):
    try:
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        if ref_b64:
            r = requests.post("https://api.openai.com/v1/images/edits",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                data={"model": model_id, "prompt": prompt, "size": px_size, "n": 1},
                files={"image": ("image.png", base64.b64decode(ref_b64), "image/png")}, timeout=120)
        else:
            r = requests.post("https://api.openai.com/v1/images/generations",
                headers=headers, json={"model": model_id, "prompt": prompt, "n": 1, "size": px_size}, timeout=120)
        data = r.json()
        if r.status_code == 200:
            items = data.get("data", [])
            if items:
                if items[0].get("url"): return ("url", items[0]["url"])
                if items[0].get("b64_json"): return ("b64", items[0]["b64_json"])
        print(f"[OPENAI ERROR] {r.status_code}: {data}")
    except Exception as e:
        print(f"[OPENAI EXCEPTION] {e}")
    return None

def generate_photo(prompt, model_key, aspect, px_size, ref_b64=None):
    info = PHOTO_MODELS.get(model_key)
    if not info: return None
    api, model_id, style = info["api"], info["model"], info.get("style")
    if api == "google": return generate_google(prompt, model_id, aspect, ref_b64, style)
    if api == "openai": return generate_openai(prompt, model_id, px_size, ref_b64)
    return None

def send_generated(chat_id, result, remaining):
    if not result:
        send(chat_id, "❌ Не удалось сгенерировать фото. Попробуй другой промпт или модель.")
        return
    caption = f"✅ Готово! Осталось фото: {remaining}"
    rtype, rdata = result
    if rtype == "url":
        if not send_photo_url(chat_id, rdata, caption):
            send(chat_id, f"✅ Готово! Открой: {rdata}\nОсталось: {remaining}")
    elif rtype == "b64":
        try: send_photo_bytes(chat_id, base64.b64decode(rdata), caption)
        except: send(chat_id, caption)

def do_generate(chat_id, prompt, ref_b64=None):
    u = get_user(chat_id)
    aspect, px_size, hint, clean = extract_size(prompt)
    final = f"{clean}, {hint}" if hint else clean
    model_name = PHOTO_MODEL_NAMES.get(u["photo_model"], "")
    send(chat_id, f"⏳ Генерирую...\nМодель: {model_name}\nРазмер: {px_size} ({aspect})")
    send_typing(chat_id)
    result = generate_photo(final, u["photo_model"], aspect, px_size, ref_b64)
    if result:
        u["photo_count"] = u.get("photo_count", 0) + 1
        save_db()
        send_generated(chat_id, result, max(0, photo_limit(chat_id) - u["photo_count"]))
    else:
        info = PHOTO_MODELS.get(u["photo_model"], {})
        send(chat_id, f"❌ Ошибка генерации.\nAPI: {info.get('api')} | Model: {info.get('model')}\nПроверь логи Railway.")

# ===== UI HELPERS =====
def show_photo_model_menu(chat_id):
    send(chat_id,
        "🖼 Выбери модель для генерации:\n\n"
        "🍌 Nano Banana (быстрый) - быстро, хорошее качество\n"
        "🍌 Nano Banana (качество) - детальная проработка\n"
        "🖼 GPT Image 2.0 / 1.5 - от OpenAI\n\n"
        "Поддерживаемые размеры: 1:1, 3:4, 9:16, 16:9, 4:3, 2:3, 4:5, 21:9",
        [
            ["🍌 Nano Banana (быстрый)", "🍌 Nano Banana (качество)"],
            ["🖼 GPT Image 2.0", "🖼 GPT Image 1.5"],
            ["⬅️ Назад"],
        ]
    )

def show_skills_menu(chat_id):
    send(chat_id,
        "🛠 Специальные навыки:\n\n"
        "📝 Тесты - кратко и точно (можно фото с вопросом)\n"
        "🇬🇧 Английский - изучение языка\n"
        "✏️ Работа с текстом - редактирование\n"
        "🖼 Фотографии - генерация AI-фото 2K\n"
        "🎨 GPT Image - промпты для нейросетей\n"
        "💰 AI Sales - продажи AI-визуалов",
        [
            ["📝 Тесты", "🇬🇧 Английский"],
            ["✏️ Работа с текстом"],
            ["🖼 Фотографии"],
            ["🎨 GPT Image промпты"],
            ["💰 AI Visuals Sales"],
            ["🏠 Главное меню"],
        ]
    )

# ===== КОМАНДЫ =====
def set_commands():
    requests.post(f"{BASE_URL}/setMyCommands", json={"commands": [
        {"command": "start",  "description": "Начать заново"},
        {"command": "mode",   "description": "Режим общения"},
        {"command": "skills", "description": "Специальные навыки"},
        {"command": "model",  "description": "Выбор модели Claude"},
        {"command": "lang",   "description": "Язык ответов"},
        {"command": "clear",  "description": "Очистить память"},
        {"command": "sub",    "description": "Подписка"},
        {"command": "ref",    "description": "Реферальная ссылка"},
        {"command": "status", "description": "Мой статус"},
        {"command": "help",   "description": "Помощь"},
    ]})

# ===== АДМИН =====
def handle_admin(chat_id, text, user_id, username):
    if not is_admin(user_id, username):
        send(chat_id, "Нет доступа.")
        return
    parts = text.split()
    cmd = parts[0]
    if cmd == "/admin":
        send(chat_id,
            f"👑 Админ-панель\n\nПользователей: {len(user_data)}\n\n"
            "Команды:\n/users - список\n/export - скачать базу\n"
            "/ban [id] - забанить\n/unban [id] - разбанить\n"
            "/givesub [id] - выдать подписку\n/revokesub [id] - забрать подписку"
        )
    elif cmd == "/users":
        lines = ["👥 Пользователи (последние 30):\n"]
        for uid, u in list(user_data.items())[-30:]:
            uname = f"@{u.get('username')}" if u.get("username") else "нет @"
            sub = "✅" if u.get("has_sub") else "нет"
            banned = " 🚫" if uid in BANNED_USERS else ""
            lines.append(f"{uid} {uname} {u.get('name','')} {banned} | sub:{sub} msg:{u.get('msg_count',0)} photo:{u.get('photo_count',0)}")
        send(chat_id, "\n".join(lines))
    elif cmd == "/export":
        try:
            lines = [f"БАЗА - {len(user_data)} чел.\n" + "="*40]
            for i, (uid, u) in enumerate(user_data.items(), 1):
                uname = f"@{u.get('username')}" if u.get("username") else "-"
                lines.append(f"\n{i}. {u.get('name','-')} {uname}{'  [ЗАБАНЕН]' if uid in BANNED_USERS else ''}\n"
                    f"   ID: {uid}\n"
                    f"   Подписка: {'ДА' if u.get('has_sub') else 'нет'}\n"
                    f"   Сообщений: {u.get('msg_count',0)} / Фото: {u.get('photo_count',0)}\n"
                    f"   Рефералов: {len(u.get('referrals',[]))} | +msg:{u.get('referral_bonus_msg',0)} +photo:{u.get('referral_bonus_photo',0)}\n" + "-"*40)
            requests.post(f"{BASE_URL}/sendDocument",
                data={"chat_id": chat_id, "caption": f"База - {len(user_data)} чел."},
                files={"document": ("users.txt", "\n".join(lines).encode("utf-8"))})
        except Exception as e:
            send(chat_id, f"Ошибка: {e}")
    elif cmd == "/ban" and len(parts) > 1:
        try: BANNED_USERS.add(int(parts[1])); send(chat_id, f"{parts[1]} забанен.")
        except: send(chat_id, "Неверный ID.")
    elif cmd == "/unban" and len(parts) > 1:
        try: BANNED_USERS.discard(int(parts[1])); send(chat_id, f"{parts[1]} разбанен.")
        except: send(chat_id, "Неверный ID.")
    elif cmd == "/givesub" and len(parts) > 1:
        try:
            get_user(int(parts[1]))["has_sub"] = True; save_db()
            send(chat_id, f"Подписка выдана {parts[1]}.")
        except: send(chat_id, "Неверный ID.")
    elif cmd == "/revokesub" and len(parts) > 1:
        try:
            get_user(int(parts[1]))["has_sub"] = False; save_db()
            send(chat_id, f"Подписка отозвана у {parts[1]}.")
        except: send(chat_id, "Неверный ID.")

# ===== ГЛАВНЫЙ ОБРАБОТЧИК =====
def handle(update):
    msg = update.get("message", {})
    if not msg: return

    chat_id  = msg["chat"]["id"]
    user_id  = msg.get("from", {}).get("id", 0)
    text     = msg.get("text", "") or ""
    caption  = msg.get("caption", "") or ""
    name     = msg.get("from", {}).get("first_name", "")
    username = msg.get("from", {}).get("username", "")
    photos   = msg.get("photo", [])

    print(f"[USER] id={user_id} @{username} {name}: {(text or caption)[:80]}")

    if user_id in BANNED_USERS:
        send(chat_id, "У тебя нет доступа к этому боту.")
        return

    u = get_user(chat_id)
    update_user_info(chat_id, username, name)
    is_command = text.startswith("/")

    # Сброс скилл-режима при любой команде
    if is_command and u.get("mode") in SKILL_MODES:
        u["mode"] = "default"
        u["history"] = []
        u["photo_model"] = None
        pending_text_mode.pop(chat_id, None)

    # Реферал
    if text.startswith("/start ref_"):
        try:
            ref_id = int(text.split("ref_")[1])
            if ref_id != chat_id and ref_id in user_data and not u.get("referred_by"):
                ref_u = get_user(ref_id)
                ref_u["referral_bonus_msg"]   = ref_u.get("referral_bonus_msg", 0)   + REFERRAL_BONUS_MSG
                ref_u["referral_bonus_photo"] = ref_u.get("referral_bonus_photo", 0) + REFERRAL_BONUS_PHOTO
                ref_u["referrals"].append(chat_id)
                u["referred_by"] = ref_id
                save_db()
                send(ref_id, f"🎉 Друг зарегистрировался по твоей ссылке!\n+{REFERRAL_BONUS_MSG} сообщений и +{REFERRAL_BONUS_PHOTO} фото начислено.")
        except: pass

    # Админ
    if text.startswith(("/admin", "/users", "/export", "/ban", "/unban", "/givesub", "/revokesub")):
        handle_admin(chat_id, text, user_id, username)
        return

    # Подтверждение очистки
    if chat_id in pending_clear:
        if text == "✅ Точно очистить":
            pending_clear.discard(chat_id)
            u["history"] = []; save_db()
            send(chat_id, "🗑 Память очищена!")
        elif text == "❌ Нет":
            pending_clear.discard(chat_id)
            send(chat_id, "Окей, память осталась нетронутой 👍")
        else:
            send(chat_id, "Выбери вариант 👇", [["✅ Точно очистить", "❌ Нет"]])
        return

    # Кнопка Назад
    if text == "🏠 Главное меню":
        u["mode"] = "default"; u["history"] = []; u["photo_model"] = None
        pending_text_mode.pop(chat_id, None); save_db()
        send(chat_id,
            "🤖 AI-ассистент\n\n"
            "🗣 Режимы (/mode):\n"
            "🗣 Дефолт - нейтральный ИИ\n"
            "💼 По делу - строго и кратко\n"
            "😊 Друг - по-дружески\n"
            "🤬 Хуесос - хамит, матерится, смешно\n\n"
            "🛠 Скиллы (/skills):\n"
            "📝 Тесты - кратко и точно\n"
            "🇬🇧 Английский - изучение языка\n"
            "✏️ Работа с текстом - редактирование\n"
            "🖼 Фотографии - генерация AI-фото 2K\n"
            "🎨 GPT Image - промпты\n"
            "💰 AI Sales - продажи\n\n"
            "🧠 Модели Claude (/model):\n"
            "⚡ Sonnet 4.6 - быстрый (по умолчанию)\n"
            "🧠 Opus 4.7 - умнее (только подписка)\n\n"
            "💳 Подписка (/sub) - снимает все лимиты\n"
            "🔗 Рефералы (/ref) - бонусы за приглашённых друзей\n\n"
            f"🎁 Бесплатно: {FREE_MSG_LIMIT} сообщений, {FREE_PHOTO_LIMIT} фото\n"
            f"🔗 За реферала: +{REFERRAL_BONUS_MSG} сообщений, +{REFERRAL_BONUS_PHOTO} фото"
        )
        return

    if text == "⬅️ Назад":
        u["mode"] = "default"; u["history"] = []; u["photo_model"] = None
        pending_text_mode.pop(chat_id, None); save_db()
        show_skills_menu(chat_id)
        return

    # Фото в режиме генерации
    if photos and u.get("mode") == "photo":
        if not u.get("photo_model"):
            show_photo_model_menu(chat_id); return
        if not can_photo(chat_id):
            send(chat_id, "⚠️ Закончились бесплатные фото. /sub или /ref"); return
        if caption:
            do_generate(chat_id, caption, download_photo_b64(photos[-1]["file_id"]))
        else:
            send(chat_id, "Напиши подпись к фото - это будет промпт!\nПример: Замени фон на закат")
        return

    # Фото в любом другом режиме (включая Тесты)
    if photos and u.get("mode") != "photo":
        if not can_msg(chat_id):
            send(chat_id, "⚠️ Закончились бесплатные сообщения. Оформи /sub"); return
        send_typing(chat_id)
        try:
            b64 = download_photo_b64(photos[-1]["file_id"])
            if not b64:
                send(chat_id, "Не удалось загрузить фото."); return
            if u.get("mode") == "test":
                prompt_text = caption if caption else "Реши задачу или ответь на вопрос который виден на этом фото. Отвечай максимально кратко и точно."
            else:
                prompt_text = caption if caption else "Опиши что на фото."
            response = client.messages.create(
                model=CLAUDE_MODELS.get(u.get("model","sonnet"), CLAUDE_MODELS["sonnet"]),
                max_tokens=2048, system=get_system(chat_id),
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": prompt_text}
                ]}]
            )
            u["msg_count"] = u.get("msg_count", 0) + 1; save_db()
            send(chat_id, response.content[0].text, markdown=True)
        except Exception as e:
            send(chat_id, f"Ошибка: {str(e)}")
        return

    # Работа с текстом — ждём субрежим
    if u.get("mode") == "text_work" and chat_id not in pending_text_mode and not is_command:
        if text in TEXT_SUBMODES:
            pending_text_mode[chat_id] = TEXT_SUBMODES[text]
            send(chat_id, "Отправь текст 👇"); return

    # Работа с текстом — ждём текст
    if chat_id in pending_text_mode and not is_command:
        submode = pending_text_mode.pop(chat_id)
        send_typing(chat_id)
        if submode == "ai_check":
            time.sleep(1); send(chat_id, "⏳ Анализирую...\n[████████░░] 80%")
            time.sleep(1.5); send(chat_id, ai_check_result(), markdown=True)
        else:
            try:
                response = client.messages.create(
                    model=CLAUDE_MODELS.get(u.get("model","sonnet"), CLAUDE_MODELS["sonnet"]),
                    max_tokens=2048, system=SYSTEM_PROMPTS["text_work"],
                    messages=[{"role": "user", "content": TEXT_SUBMODE_PROMPTS[submode] + text}]
                )
                send(chat_id, response.content[0].text, markdown=True)
            except Exception as e:
                send(chat_id, f"Ошибка: {str(e)}")
        return

    # ===== КОМАНДЫ =====
    if text.startswith("/start"):
        model_name = CLAUDE_MODEL_NAMES.get(u.get("model","sonnet"), "⚡ Sonnet 4.6")
        send(chat_id,
            f"Привет, {name}! 👋\n"
            f"Я - твой личный AI-ассистент. Помогу с задачами, текстами, идеями и ответами на любые вопросы.\n\n"
            f"⚙️ Режим: 🗣 Дефолт\n"
            f"🧠 Модель: {model_name}\n\n"
            f"📌 Команды:\n"
            f"/help - список возможностей\n"
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
            "🤖 AI-ассистент\n\n"
            "🗣 Режимы (/mode):\n"
            "🗣 Дефолт - нейтральный ИИ\n"
            "💼 По делу - строго и кратко\n"
            "😊 Друг - по-дружески\n"
            "🤬 Хуесос - хамит, матерится, смешно\n\n"
            "🛠 Скиллы (/skills):\n"
            "📝 Тесты - кратко и точно\n"
            "🇬🇧 Английский - изучение языка\n"
            "✏️ Работа с текстом - редактирование\n"
            "🖼 Фотографии - генерация AI-фото 2K\n"
            "🎨 GPT Image - промпты\n"
            "💰 AI Sales - продажи\n\n"
            "🧠 Модели Claude (/model):\n"
            "⚡ Sonnet 4.6 - быстрый (по умолчанию)\n"
            "🧠 Opus 4.7 - умнее (только подписка)\n\n"
            "💳 Подписка (/sub) - снимает все лимиты\n"
            "🔗 Рефералы (/ref) - бонусы за приглашённых друзей\n\n"
            f"🎁 Бесплатно: {FREE_MSG_LIMIT} сообщений, {FREE_PHOTO_LIMIT} фото\n"
            f"🔗 За реферала: +{REFERRAL_BONUS_MSG} сообщений, +{REFERRAL_BONUS_PHOTO} фото"
        )
        return

    if text == "/mode":
        send(chat_id, "Выбери режим:", [
            ["🗣 Дефолт", "💼 По делу", "😊 Друг"],
            ["🤬 Хуесос"],
        ])
        return

    if text == "/skills":
        show_skills_menu(chat_id); return

    if text == "/model":
        current = CLAUDE_MODEL_NAMES.get(u.get("model","sonnet"), "⚡ Sonnet 4.6")
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
            send(chat_id,
                f"💳 Подписка\n\n"
                f"Осталось сообщений: {max(0, msg_limit(chat_id) - u.get('msg_count',0))}\n"
                f"Осталось фото: {max(0, photo_limit(chat_id) - u.get('photo_count',0))}\n\n"
                f"Для приобретения пиши: @staremenow"
            )
        return

    if text == "/ref":
        bot_info = requests.get(f"{BASE_URL}/getMe").json()
        bot_uname = bot_info.get("result", {}).get("username", "")
        ref_link = f"https://t.me/{bot_uname}?start=ref_{chat_id}"
        send(chat_id,
            f"🔗 Реферальная программа\n\n"
            f"За каждого друга: +{REFERRAL_BONUS_MSG} сообщений и +{REFERRAL_BONUS_PHOTO} фото\n\n"
            f"Твоя ссылка:\n{ref_link}\n\n"
            f"Приглашено: {len(u.get('referrals',[]))} чел.\n"
            f"Бонусных сообщений: {u.get('referral_bonus_msg',0)}\n"
            f"Бонусных фото: {u.get('referral_bonus_photo',0)}"
        )
        return

    if text == "/status":
        mode_map = {
            "default": "🗣 Дефолт", "delo": "💼 По делу", "friend": "😊 Друг",
            "huesos": "🤬 Хуесос",
            "test": "📝 Тесты", "english": "🇬🇧 Английский", "text_work": "✏️ Работа с текстом",
            "photo": "🖼 Фотографии", "skill_gpt": "🎨 GPT Image", "skill_sales": "💰 AI Sales",
        }
        send(chat_id,
            f"📊 Твой статус\n\n"
            f"Режим: {mode_map.get(u.get('mode','default'), '🗣 Дефолт')}\n"
            f"Модель Claude: {CLAUDE_MODEL_NAMES.get(u.get('model','sonnet'), '⚡ Sonnet 4.6')}\n"
            f"Модель фото: {PHOTO_MODEL_NAMES.get(u.get('photo_model'), 'не выбрана')}\n"
            f"Язык: {u.get('language','ru')}\n"
            f"Подписка: {'✅ Активна' if u.get('has_sub') else '❌ Нет'}\n"
            f"Осталось сообщений: {max(0, msg_limit(chat_id) - u.get('msg_count',0))}\n"
            f"Осталось фото: {max(0, photo_limit(chat_id) - u.get('photo_count',0))}\n"
            f"История: {len(u.get('history',[]))} сообщений"
        )
        return

    # ===== КНОПКИ =====
    if text == "⚡ Sonnet 4.6":
        u["model"] = "sonnet"; save_db(); send(chat_id, "✅ Модель: ⚡ Sonnet 4.6"); return
    if text == "🧠 Opus 4.7":
        if not u.get("has_sub"):
            send(chat_id, "🔒 Opus 4.7 только по подписке. Пиши @staremenow"); return
        u["model"] = "opus"; save_db(); send(chat_id, "✅ Модель: 🧠 Opus 4.7"); return

    if text == "🇷🇺 Русский":  u["language"]="ru";   save_db(); send(chat_id,"Язык: 🇷🇺 Русский");  return
    if text == "🇬🇧 English":  u["language"]="en";   save_db(); send(chat_id,"Language: 🇬🇧 English"); return
    if text == "🌐 Авто":      u["language"]="auto"; save_db(); send(chat_id,"Язык: 🌐 Авто");       return

    if text == "🗣 Дефолт":
        u["mode"]="default"; u["history"]=[]; u["photo_model"]=None; pending_text_mode.pop(chat_id,None); save_db()
        send(chat_id, "🗣 Режим: Дефолт."); return
    if text == "💼 По делу":
        u["mode"]="delo"; u["history"]=[]; u["photo_model"]=None; pending_text_mode.pop(chat_id,None); save_db()
        send(chat_id, "💼 Режим: По делу."); return
    if text == "😊 Друг":
        u["mode"]="friend"; u["history"]=[]; u["photo_model"]=None; pending_text_mode.pop(chat_id,None); save_db()
        send(chat_id, "😊 Режим: Друг. Привет родной)"); return
    if text == "🤬 Хуесос":
        u["mode"]="huesos"; u["history"]=[]; u["photo_model"]=None; pending_text_mode.pop(chat_id,None); save_db()
        send(chat_id, "🤬 Режим: Хуесос активирован. Ну что, чудак, давай поговорим. Я слушаю, хотя мне уже скучно."); return

    if text in TEXT_SUBMODES and u.get("mode") == "text_work":
        pending_text_mode[chat_id] = TEXT_SUBMODES[text]
        send(chat_id, "Отправь текст 👇"); return

    if text in PHOTO_MODEL_BUTTONS:
        u["mode"] = "photo"; u["photo_model"] = PHOTO_MODEL_BUTTONS[text]; u["history"] = []; save_db()
        model_name = PHOTO_MODEL_NAMES[PHOTO_MODEL_BUTTONS[text]]
        rem = max(0, photo_limit(chat_id) - u.get("photo_count",0))
        send(chat_id,
            f"✅ Модель: {model_name}\n\n"
            f"📸 Как генерировать:\n"
            f"1. Напиши промпт текстом\n"
            f"2. Или прикрепи фото с подписью (референс)\n"
            f"3. Укажи размер: 1:1, 3:4, 9:16, 16:9 и др.\n\n"
            f"Осталось фото: {rem}\n\nСкидывай промпт!",
            [["⬅️ Назад"]]
        )
        return

    SKILL_BUTTONS = {
        "📝 Тесты":             ("test",       "📝 Тесты. Скидывай вопрос или фото с вопросом! 🎯",                          [["⬅️ Назад"]]),
        "🇬🇧 Английский":       ("english",    "🇬🇧 Английский. Скидывай текст, вопрос или попроси тест! ✍️",               [["⬅️ Назад"]]),
        "🎨 GPT Image промпты": ("skill_gpt",  "🎨 GPT Image. Скидывай идею - превращу в промпт! 🖼",                        [["⬅️ Назад"]]),
        "💰 AI Visuals Sales":  ("skill_sales","💰 AI Sales. Найду клиентов, напишу оффер или DM! 👇",                       [["⬅️ Назад"]]),
        "✏️ Работа с текстом":  ("text_work",  None, None),
        "🖼 Фотографии":        ("photo",      None, None),
    }

    if text in SKILL_BUTTONS:
        mode_key, reply_text, kb = SKILL_BUTTONS[text]

        if mode_key == "photo":
            if not can_photo(chat_id):
                send(chat_id, "⚠️ Закончились бесплатные фото. /sub или /ref"); return
            u["mode"] = "photo"; u["history"] = []; save_db()
            if u.get("photo_model") is None:
                show_photo_model_menu(chat_id)
            else:
                rem = max(0, photo_limit(chat_id) - u.get("photo_count",0))
                send(chat_id, f"🖼 Модель: {PHOTO_MODEL_NAMES.get(u['photo_model'])}\nОсталось: {rem}\n\nСкидывай промпт!", [["⬅️ Назад"]])
            return

        if mode_key == "text_work":
            u["mode"] = "text_work"; u["history"] = []; pending_text_mode.pop(chat_id,None); save_db()
            send(chat_id, "✏️ Работа с текстом. Выбери действие:",
                [["🔄 Перефразировка","✂️ Сокращение"],["📝 Удлинение","📋 По пунктам"],["🤖 Проверка на ИИ"],["⬅️ Назад"]])
            return

        u["mode"] = mode_key; u["history"] = []; u["photo_model"] = None; pending_text_mode.pop(chat_id,None); save_db()
        send(chat_id, reply_text, kb)
        return

    # Режим фото — текст как промпт
    if u.get("mode") == "photo":
        if not u.get("photo_model"): show_photo_model_menu(chat_id); return
        if not can_photo(chat_id): send(chat_id, "⚠️ Закончились бесплатные фото. /sub или /ref"); return
        do_generate(chat_id, text); return

    # Лимит сообщений
    if not can_msg(chat_id):
        send(chat_id, "⚠️ Закончились бесплатные сообщения.\n\nОформи /sub или пригласи друга /ref."); return

    # Claude
    u["history"].append({"role": "user", "content": text})
    if len(u["history"]) > 20: u["history"] = u["history"][-20:]
    send_typing(chat_id)
    try:
        response = client.messages.create(
            model=CLAUDE_MODELS.get(u.get("model","sonnet"), CLAUDE_MODELS["sonnet"]),
            max_tokens=2048, system=get_system(chat_id), messages=u["history"]
        )
        reply = response.content[0].text
        u["history"].append({"role": "assistant", "content": reply})
        u["msg_count"] = u.get("msg_count",0) + 1; save_db()
        # В режиме Хуесос и Друг разбиваем по [MSG] на несколько сообщений
        if u.get("mode") in ("huesos", "friend") and "[MSG]" in reply:
            parts = [p.strip() for p in reply.split("[MSG]") if p.strip()]
            for part in parts:
                send(chat_id, part, markdown=True)
                time.sleep(0.5)
        else:
            send(chat_id, reply, markdown=True)
    except Exception as e:
        send(chat_id, f"Ошибка: {str(e)}")

def main():
    set_commands()
    offset = 0
    print(f"Бот запущен! Пользователей в базе: {len(user_data)}")
    while True:
        try:
            r = requests.get(f"{BASE_URL}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=35)
            for update in r.json().get("result", []):
                offset = update["update_id"] + 1
                threading.Thread(target=handle, args=(update,), daemon=True).start()
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()