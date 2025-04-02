import sqlite3
import logging
import re
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import os

# Logging sozlamalari
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 🔑 Token va Admin ID
TOKEN = "7400356855:AAH16xmEED2fc0NaaQH9XFEJuhqZn-D3nvY"
ADMIN_ID = 7865739071
ADMIN_USERNAME = "@Mr_Beck07"

# Webhook sozlamalari
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://bs-bot-production.up.railway.app{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.environ.get("PORT", 8080))

# 📌 Botni ishga tushirish funksiyasi
async def initialize_bot():
    global bot
    try:
        logging.info("Botni ishga tushirish...")
        bot = Bot(
            token=TOKEN,
            default=DefaultBotProperties(parse_mode="HTML")
        )
        await bot.get_me()
        logging.info("Bot muvaffaqiyatli ulandi.")
        return bot
    except Exception as e:
        logging.error(f"Botni ulashda xato: {str(e)}")
        raise Exception("Botni ishga tushirib bo‘lmadi.")

# 📌 Dispatcher va storage
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# 📂 SQLite bazasini yaratish
conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# 📌 Foydalanuvchilar jadvali
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        full_name TEXT,
        work_place TEXT,
        position TEXT,
        approved INTEGER DEFAULT 0
    )
""")

# 📌 Lokatsiyalar jadvali
cursor.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        code TEXT PRIMARY KEY,
        name TEXT,
        latitude REAL,
        longitude REAL,
        photo1 TEXT,
        photo2 TEXT,
        additional_info TEXT
    )
""")

# 📌 Baza haqida kommentariyalar jadvali
cursor.execute("""
    CREATE TABLE IF NOT EXISTS db_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        comment TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")

# user_id ustuni mavjudligini tekshirish va qo‘shish
try:
    cursor.execute("SELECT user_id FROM db_comments LIMIT 1")
except sqlite3.OperationalError:
    cursor.execute("ALTER TABLE db_comments ADD COLUMN user_id INTEGER")
    logging.info("user_id ustuni db_comments jadvaliga qo‘shildi.")

conn.commit()

# 🔹 Foydalanuvchi ma'lumotlarini so‘rash uchun holatlar
class UserRegistration(StatesGroup):
    full_name = State()
    work_place = State()
    position = State()

# 🔹 Foydalanuvchi kommentariyasini so‘rash uchun holat
class UserCommentState(StatesGroup):
    waiting_for_comment = State()

# 🔹 Foydalanuvchi lokatsiya qidirish uchun holat
class UserSearchLocationState(StatesGroup):
    waiting_for_location_code = State()

# 🔹 Admin lokatsiya qo‘shish uchun holatlar
class AddLocationState(StatesGroup):
    waiting_for_first_photo = State()
    waiting_for_second_photo = State()
    waiting_for_additional_info = State()
    waiting_for_command = State()

# 🔹 Inline tugmalar uchun umumiy funksiya
def get_user_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help"),
         InlineKeyboardButton(text="📞 Aloqa", callback_data="contact")]
    ])
    return keyboard

# 🔹 Lokatsiya yuborilganda chiqadigan inline tugmalar
def get_location_action_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Kommentariya yozish", callback_data="write_comment"),
            InlineKeyboardButton(text="🔍 BS lokatsiya qidirish", callback_data="search_location")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help"),
            InlineKeyboardButton(text="📞 Aloqa", callback_data="contact")
        ]
    ])
    return keyboard

# 🔹 /start buyrug‘i
@dp.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    cursor.execute("SELECT approved FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if result:
        if result[0] == 1:
            await message.reply("✅ Siz allaqachon tasdiqlangansiz. Tizimdan foydalanishingiz mumkin!\n"
                                "Lokatsiya kodini yuboring (masalan, 3700):",
                                reply_markup=get_user_keyboard(), protect_content=True)
        else:
            await message.reply("⏳ Ma'lumotlaringiz adminga yuborilgan. Admin ruxsatini kuting.",
                                reply_markup=get_user_keyboard(), protect_content=True)
        return

    await message.reply("👋 Assalomu alaykum! Ro‘yxatdan o‘tish uchun ma'lumotlaringizni kiriting.\n"
                        "👤 Familiyangiz va ismingizni yozing:",
                        reply_markup=get_user_keyboard(), protect_content=True)
    await state.set_state(UserRegistration.full_name)

# 🔹 Familiya va ism
@dp.message(UserRegistration.full_name)
async def process_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.reply("🏢 Ish joyingizni yozing:", reply_markup=get_user_keyboard(), protect_content=True)
    await state.set_state(UserRegistration.work_place)

# 🔹 Ish joyi
@dp.message(UserRegistration.work_place)
async def process_work_place(message: Message, state: FSMContext):
    await state.update_data(work_place=message.text)
    await message.reply("💼 Lavozimingizni yozing:", reply_markup=get_user_keyboard(), protect_content=True)
    await state.set_state(UserRegistration.position)

# 🔹 Lavozim va adminga yuborish
@dp.message(UserRegistration.position)
async def process_position(message: Message, state: FSMContext):
    user_data = await state.get_data()
    user_id = message.from_user.id
    full_name = user_data["full_name"]
    work_place = user_data["work_place"]
    position = message.text

    try:
        cursor.execute("INSERT OR REPLACE INTO users (user_id, full_name, work_place, position, approved) VALUES (?, ?, ?, ?, 0)",
                       (user_id, full_name, work_place, position))
        conn.commit()

        await bot.send_message(ADMIN_ID, f"📋 Yangi foydalanuvchi ro‘yxatdan o‘tdi:\n"
                                       f"🆔 ID: {user_id}\n"
                                       f"👤 Familiya va ism: {full_name}\n"
                                       f"🏢 Ish joyi: {work_place}\n"
                                       f"💼 Lavozim: {position}\n\n"
                                       f"✅ Tasdiqlash: /approve {user_id}\n"
                                       f"❌ Rad etish: /reject {user_id}\n"
                                       f"⛔ Ruxsatni bekor qilish: /revoke {user_id}",
                                       protect_content=True)

        await message.reply("✅ Ma'lumotlaringiz adminga yuborildi. ⏳ Admin ruxsatini kuting.",
                            reply_markup=get_user_keyboard(), protect_content=True)
        await state.clear()
    except Exception as e:
        logging.error(f"Foydalanuvchi qo‘shishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Admin yordam
@dp.message(Command("help"))
async def help_command(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    await message.reply("🛠 Admin imkoniyatlari:\n\n"
                        "✅ /approve foydalanuvchi_id - Foydalanuvchini tasdiqlash\n"
                        "❌ /reject foydalanuvchi_id - Foydalanuvchini rad etish\n"
                        "⛔ /revoke foydalanuvchi_id - Foydalanuvchi ruxsatini bekor qilish\n"
                        "📋 /list_users - Tasdiqlangan foydalanuvchilar ro‘yxati\n"
                        "📍 /add [kod nom] url - Lokatsiya qo‘shish\n"
                        "🗑 /delete kod - Lokatsiya o‘chirish\n"
                        "🌍 /list_locations - Lokatsiyalar ro‘yxati\n"
                        "🔄 /reset_add - Lokatsiya qo‘shishni qayta boshlash\n"
                        "💬 /add_comment komment - Kommentariya qo‘shish\n"
                        "📜 /view_comments - Kommentariyalarni ko‘rish\n"
                        "ℹ️ /help - Ushbu yordam menyusi",
                        protect_content=True)

# 🔹 Admin tasdiqlash
@dp.message(Command("approve"))
async def approve_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    command_parts = message.text.split()
    if len(command_parts) != 2:
        return await message.reply("❌ Xato! Format: /approve foydalanuvchi_id", protect_content=True)

    try:
        user_id = int(command_parts[1])
        cursor.execute("UPDATE users SET approved = 1 WHERE user_id = ?", (user_id,))
        if cursor.rowcount == 0:
            return await message.reply("❌ Bunday foydalanuvchi topilmadi!", protect_content=True)
        conn.commit()

        await message.reply(f"✅ Foydalanuvchi (🆔 {user_id}) tasdiqlandi.", protect_content=True)
        await bot.send_message(user_id, "✅ Admin sizga ruxsat berdi. Endi tizimdan foydalanishingiz mumkin!\n"
                                       "Lokatsiya kodini yuboring (masalan, 3700):",
                              reply_markup=get_user_keyboard(), protect_content=True)
    except Exception as e:
        logging.error(f"Tasdiqlashda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Admin rad etish (foydalanuvchi qayta ro‘yxatdan o‘tishi uchun ma'lumotlarni o‘chirish)
@dp.message(Command("reject"))
async def reject_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    command_parts = message.text.split()
    if len(command_parts) != 2:
        return await message.reply("❌ Xato! Format: /reject foydalanuvchi_id", protect_content=True)

    try:
        user_id = int(command_parts[1])
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        if cursor.rowcount == 0:
            return await message.reply("❌ Bunday foydalanuvchi topilmadi!", protect_content=True)
        conn.commit()

        await message.reply(f"❌ Foydalanuvchi (🆔 {user_id}) rad etildi.", protect_content=True)
        await bot.send_message(user_id, "❌ Admin sizning ro‘yxatingizni rad etdi. Qayta ro‘yxatdan o‘tish uchun /start buyrug‘ini bosing.",
                              reply_markup=get_user_keyboard(), protect_content=True)
    except Exception as e:
        logging.error(f"Rad etishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Admin ruxsatni bekor qilish (foydalanuvchi qayta ro‘yxatdan o‘tishi uchun ma'lumotlarni o‘chirish)
@dp.message(Command("revoke"))
async def revoke_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    command_parts = message.text.split()
    if len(command_parts) != 2:
        return await message.reply("❌ Xato! Format: /revoke foydalanuvchi_id", protect_content=True)

    try:
        user_id = int(command_parts[1])
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        if cursor.rowcount == 0:
            return await message.reply("❌ Bunday foydalanuvchi topilmadi!", protect_content=True)
        conn.commit()

        await message.reply(f"⛔ Foydalanuvchi (🆔 {user_id}) ruxsati bekor qilindi.", protect_content=True)
        await bot.send_message(user_id, "⛔ Admin sizning ruxsatingizni bekor qildi. Qayta ro‘yxatdan o‘tish uchun /start buyrug‘ini bosing.",
                              reply_markup=get_user_keyboard(), protect_content=True)
    except Exception as e:
        logging.error(f"Ruxsatni bekor qilishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Tasdiqlangan foydalanuvchilar ro‘yxati
@dp.message(Command("list_users"))
async def list_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    try:
        cursor.execute("SELECT user_id, full_name, work_place, position FROM users WHERE approved = 1")
        users = cursor.fetchall()

        if not users:
            return await message.reply("📋 Tasdiqlangan foydalanuvchilar mavjud emas.", protect_content=True)

        response = f"📋 Tasdiqlangan foydalanuvchilar ro‘yxati ({len(users)} ta):\n\n"
        for user in users:
            user_id, full_name, work_place, position = user
            response += f"🆔 ID: {user_id}\n👤 {full_name}\n🏢 {work_place}\n💼 {position}\n\n"
        await message.reply(response, protect_content=True)
    except Exception as e:
        logging.error(f"Ro‘yxatni olishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Lokatsiyalar ro‘yxati
@dp.message(Command("list_locations"))
async def list_locations(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    try:
        cursor.execute("SELECT code, name, latitude, longitude, additional_info FROM locations")
        locations = cursor.fetchall()

        if not locations:
            return await message.reply("🌍 Hozircha lokatsiyalar mavjud emas.", protect_content=True)

        response = f"🌍 Lokatsiyalar ro‘yxati ({len(locations)} ta):\n\n"
        for i, loc in enumerate(locations, 1):
            code, name, lat, lon, additional_info = loc
            map_url = f"http://maps.google.com/maps?q={lat},{lon}&z=16"
            response += f"{i}. 📍 Kod: {code}\n🏞 Nom: {name}\n🌐 Koordinatalar: {lat}, {lon}\n"
            if additional_info:
                response += f"📝 Qo'shimcha: {additional_info}\n"
            response += f"<a href='{map_url}'>Xaritada</a>\n\n"
        await message.reply(response, protect_content=True, disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Lokatsiyalarni olishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Kommentariya qo‘shish (Admin uchun)
@dp.message(Command("add_comment"))
async def add_comment(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        return await message.reply("❌ Xato! Format: /add_comment komment", protect_content=True)

    try:
        comment = parts[1].strip()
        cursor.execute("INSERT INTO db_comments (user_id, comment) VALUES (?, ?)", (ADMIN_ID, comment))
        conn.commit()
        await message.reply(f"💬 Kommentariya qo‘shildi: {comment}", protect_content=True)
    except Exception as e:
        logging.error(f"Kommentariya qo‘shishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Kommentariyalarni ko‘rish
@dp.message(Command("view_comments"))
async def view_comments(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    try:
        cursor.execute("""
            SELECT dc.id, dc.user_id, dc.comment, dc.timestamp, u.full_name 
            FROM db_comments dc 
            LEFT JOIN users u ON dc.user_id = u.user_id 
            ORDER BY dc.timestamp DESC
        """)
        comments = cursor.fetchall()

        if not comments:
            return await message.reply("📜 Hozircha kommentariyalar mavjud emas.", protect_content=True)

        response = f"📜 Kommentariyalar ({len(comments)} ta):\n\n"
        for comment in comments:
            comment_id, user_id, text, timestamp, full_name = comment
            full_name = full_name or "Noma'lum"
            response += f"🆔 ID: {comment_id}\n👤 {full_name} (ID: {user_id})\n💬 {text}\n⏰ {timestamp}\n\n"
        await message.reply(response, protect_content=True)
    except Exception as e:
        logging.error(f"Kommentariyalarni ko‘rishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Lokatsiya qo‘shish jarayonini qayta boshlash
@dp.message(Command("reset_add"))
async def reset_add(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    await state.clear()
    await message.reply("🔄 Lokatsiya qo‘shish jarayoni qayta boshlandi. Birinchi rasmni yuboring.",
                        protect_content=True)
    await state.set_state(AddLocationState.waiting_for_first_photo)

# 🔹 Birinchi rasm
@dp.message(lambda message: message.from_user.id == ADMIN_ID and message.photo, AddLocationState.waiting_for_first_photo)
async def process_first_photo(message: Message, state: FSMContext):
    photo1 = message.photo[-1].file_id
    await state.update_data(photo1=photo1)
    await message.reply("📸 Birinchi rasm qabul qilindi. Ikkichi rasmni yuboring.",
                        protect_content=True)
    await state.set_state(AddLocationState.waiting_for_second_photo)

# 🔹 Ikkichi rasm
@dp.message(lambda message: message.from_user.id == ADMIN_ID and message.photo, AddLocationState.waiting_for_second_photo)
async def process_second_photo(message: Message, state: FSMContext):
    photo2 = message.photo[-1].file_id
    await state.update_data(photo2=photo2)
    await message.reply("📸 Ikkita rasm qabul qilindi. Qo'shimcha ma'lumot yuboring (agar kerak bo'lmasa, 'yo'q' deb yozing):",
                        protect_content=True)
    await state.set_state(AddLocationState.waiting_for_additional_info)

# 🔹 Qo'shimcha ma'lumot
@dp.message(AddLocationState.waiting_for_additional_info)
async def process_additional_info(message: Message, state: FSMContext):
    additional_info = message.text.strip()
    if additional_info.lower() == "yo'q":
        additional_info = None
    await state.update_data(additional_info=additional_info)
    await message.reply("📝 Ma'lumot qabul qilindi. /add [kod nom] url yuboring.\nMasalan: /add [3700 Aktash] http://maps.google.com/maps?q=39.919719,65.929442",
                        protect_content=True)
    await state.set_state(AddLocationState.waiting_for_command)

# 🔹 Lokatsiya qo‘shish
@dp.message(Command("add"))
async def add_location(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    current_state = await state.get_state()
    if current_state != AddLocationState.waiting_for_command.state:
        await message.reply("❌ Oldin ikkita rasm va ma'lumot yuboring! /reset_add bilan qayta boshlashingiz mumkin.",
                            protect_content=True)
        await state.set_state(AddLocationState.waiting_for_first_photo)
        return

    match = re.match(r"/add\s+\[(\d+)\s+(.+?)\]\s+(http://maps.google.com/maps\?q=(-?\d+\.\d+),(-?\d+\.\d+)[^\s]*)", message.text)
    if not match:
        await message.reply("❌ Xato! Format: /add [3700 Aktash] http://maps.google.com/maps?q=39.919719,65.929442",
                            protect_content=True)
        return

    try:
        code, name, url, lat, lon = match.groups()
        lat, lon = float(lat), float(lon)
        user_data = await state.get_data()

        photo1 = user_data.get("photo1")
        photo2 = user_data.get("photo2")
        additional_info = user_data.get("additional_info")

        if not photo1 or not photo2:
            await message.reply("❌ Ikkita rasm yuborilmadi! /reset_add bilan qayta boshlang.",
                                protect_content=True)
            await state.set_state(AddLocationState.waiting_for_first_photo)
            return

        cursor.execute("INSERT OR REPLACE INTO locations (code, name, latitude, longitude, photo1, photo2, additional_info) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (code, name, lat, lon, photo1, photo2, additional_info))
        conn.commit()

        await message.reply(f"✅ [{code} {name}] lokatsiya qo‘shildi!\n📍 <a href='{url}'>Xaritada ko‘rish</a>",
                            protect_content=True, disable_web_page_preview=True)
        await state.clear()
    except Exception as e:
        logging.error(f"Lokatsiya qo‘shishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Lokatsiya o‘chirish
@dp.message(Command("delete"))
async def delete_location(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        return await message.reply("❌ Xato! Format: /delete 3700", protect_content=True)

    try:
        code = parts[1].strip()
        cursor.execute("DELETE FROM locations WHERE code = ?", (code,))
        conn.commit()
        await message.reply(f"🗑 [{code}] kodli joy o‘chirildi.", protect_content=True)
    except Exception as e:
        logging.error(f"O‘chirishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Foydalanuvchi lokatsiya so‘rashi
@dp.message()
async def get_location(message: Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        return

    user_id = message.from_user.id
    cursor.execute("SELECT approved FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if not result or result[0] == 0:
        return await message.reply("❌ Siz admin ruxsatini olmagansiz. ⏳ Tasdiqni kuting.",
                                   reply_markup=get_user_keyboard(), protect_content=True)

    try:
        # Kodni tozalash va faqat raqamlarni olish
        code = message.text.strip()
        # Agar kod faqat raqamlardan iborat bo‘lishini ta'minlash
        if not code.isdigit():
            return await message.reply("❌ Kod faqat raqamlardan iborat bo‘lishi kerak (masalan, 3700)!",
                                       reply_markup=get_user_keyboard(), protect_content=True)

        # Lokatsiyani qidirish
        cursor.execute("SELECT name, latitude, longitude, photo1, photo2, additional_info FROM locations WHERE code = ?", (code,))
        result = cursor.fetchone()

        if result:
            name, lat, lon, photo1, photo2, additional_info = result
            map_url = f"http://maps.google.com/maps?q={lat},{lon}&z=16"
            caption = f"📍 [{code} {name}]\n🌍 <a href='{map_url}'>Google xaritada ochish</a>"
            if additional_info:
                caption += f"\n📝 Qo'shimcha: {additional_info}"

            media = [
                types.InputMediaPhoto(media=photo1, caption=caption, parse_mode="HTML"),
                types.InputMediaPhoto(media=photo2)
            ]
            await bot.send_media_group(chat_id=user_id, media=media, protect_content=True)

            # Avtomatik kommentariya qo'shish
            comment = f"Foydalanuvchi {code} kodli lokatsiyani oldi va tekshirdi"
            cursor.execute("INSERT INTO db_comments (user_id, comment) VALUES (?, ?)", (user_id, comment))
            conn.commit()

            # Inline tugmalar bilan xabar yuborish
            await message.reply("Yuqoridagi rasmlar bilan lokatsiya yuborildi.\n"
                                "Quyidagi tugmalardan birini tanlang:",
                                reply_markup=get_location_action_keyboard(), protect_content=True)

            # Lokatsiya kodini saqlash
            await state.update_data(location_code=code)
        else:
            await message.reply("❌ Bunday kod topilmadi yoki hali qo‘shilmagan! Admin bilan bog‘laning.",
                                reply_markup=get_user_keyboard(), protect_content=True)
    except Exception as e:
        logging.error(f"So‘rovda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Inline tugmalar bilan ishlash
@dp.callback_query()
async def process_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    cursor.execute("SELECT approved FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if not result or result[0] == 0:
        await callback.message.reply("❌ Siz admin ruxsatini olmagansiz. ⏳ Tasdiqni kuting.",
                                     reply_markup=get_user_keyboard(), protect_content=True)
        await callback.answer()
        return

    if callback.data == "write_comment":
        user_data = await state.get_data()
        location_code = user_data.get("location_code")
        if not location_code:
            await callback.message.reply("❌ Avval lokatsiya kodini yuboring!",
                                         reply_markup=get_user_keyboard(), protect_content=True)
            await callback.answer()
            return

        await callback.message.reply("❓ Nima maqsadda bordiz va nima o'zgartirdingiz? Javobingizni yozing:",
                                     reply_markup=get_user_keyboard(), protect_content=True)
        await state.set_state(UserCommentState.waiting_for_comment)
        await callback.answer()

    elif callback.data == "search_location":
        await callback.message.reply("🔍 Yangi lokatsiya kodini yuboring (masalan, 3700):",
                                     reply_markup=get_user_keyboard(), protect_content=True)
        await state.set_state(UserSearchLocationState.waiting_for_location_code)
        await callback.answer()

    elif callback.data == "help":
        await callback.message.edit_text("ℹ️ Botdan foydalanish: Lokatsiya kodini yuboring (masalan, 3700).",
                                         reply_markup=get_user_keyboard(), protect_content=True)
        await callback.answer()

    elif callback.data == "contact":
        await callback.message.edit_text(f"📞 Aloqa: {ADMIN_USERNAME} ga yozing.",
                                         reply_markup=get_user_keyboard(), protect_content=True)
        await callback.answer()

# 🔹 Foydalanuvchi kommentariyasini qabul qilish
@dp.message(UserCommentState.waiting_for_comment)
async def process_user_comment(message: Message, state: FSMContext):
    user_id = message.from_user.id
    comment_text = message.text.strip()
    user_data = await state.get_data()
    location_code = user_data.get("location_code")

    try:
        cursor.execute("INSERT INTO db_comments (user_id, comment) VALUES (?, ?)",
                      (user_id, f"[{location_code}] bo'yicha: {comment_text}"))
        conn.commit()
        await message.reply("✅ Sizning javobingiz saqlandi. Rahmat!",
                           reply_markup=get_user_keyboard(), protect_content=True)
    except Exception as e:
        logging.error(f"Foydalanuvchi kommentariyasini saqlashda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

    # Holatni tozalash
    await state.clear()

# 🔹 Foydalanuvchi yangi lokatsiya kodi yuborishi
@dp.message(UserSearchLocationState.waiting_for_location_code)
async def process_search_location(message: Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        # Kodni tozalash va faqat raqamlarni olish
        code = message.text.strip()
        # Agar kod faqat raqamlardan iborat bo‘lishini ta'minlash
        if not code.isdigit():
            await message.reply("❌ Kod faqat raqamlardan iborat bo‘lishi kerak (masalan, 3700)!",
                                reply_markup=get_user_keyboard(), protect_content=True)
            return

        # Lokatsiyani qidirish
        cursor.execute("SELECT name, latitude, longitude, photo1, photo2, additional_info FROM locations WHERE code = ?", (code,))
        result = cursor.fetchone()

        if result:
            name, lat, lon, photo1, photo2, additional_info = result
            map_url = f"http://maps.google.com/maps?q={lat},{lon}&z=16"
            caption = f"📍 [{code} {name}]\n🌍 <a href='{map_url}'>Google xaritada ochish</a>"
            if additional_info:
                caption += f"\n📝 Qo'shimcha: {additional_info}"

            media = [
                types.InputMediaPhoto(media=photo1, caption=caption, parse_mode="HTML"),
                types.InputMediaPhoto(media=photo2)
            ]
            await bot.send_media_group(chat_id=user_id, media=media, protect_content=True)

            # Avtomatik kommentariya qo'shish
            comment = f"Foydalanuvchi {code} kodli lokatsiyani oldi va tekshirdi"
            cursor.execute("INSERT INTO db_comments (user_id, comment) VALUES (?, ?)", (user_id, comment))
            conn.commit()

            # Inline tugmalar bilan xabar yuborish
            await message.reply("Yuqoridagi rasmlar bilan lokatsiya yuborildi.\n"
                                "Quyidagi tugmalardan birini tanlang:",
                                reply_markup=get_location_action_keyboard(), protect_content=True)

            # Lokatsiya kodini saqlash
            await state.update_data(location_code=code)
        else:
            await message.reply("❌ Bunday kod topilmadi yoki hali qo‘shilmagan! Admin bilan bog‘laning.",
                                reply_markup=get_user_keyboard(), protect_content=True)

        # Holatni tozalash
        await state.clear()
    except Exception as e:
        logging.error(f"Lokatsiya qidirishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Foydalanuvchi rasm yuborsa
@dp.message(lambda message: message.from_user.id != ADMIN_ID and message.photo)
async def handle_user_photo(message: Message):
    await message.reply("❌ Faqat lokatsiya kodi yuborishingiz mumkin (masalan, 3700). Rasm yuborish mumkin emas!",
                        reply_markup=get_user_keyboard(), protect_content=True)

# 📌 Webhook sozlash
async def on_startup():
    try:
        await bot.set_webhook(WEBHOOK_URL)
        logging.info(f"Webhook set to {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Webhook o‘rnatishda xato: {str(e)}")

async def on_shutdown():
    try:
        await bot.delete_webhook()
        await bot.session.close()
        logging.info("Bot shutdown completed.")
    except Exception as e:
        logging.error(f"O‘chirishda xato: {str(e)}")

# 📌 Botni ishga tushirish
async def main():
    global bot
    try:
        bot = await initialize_bot()

        app = web.Application()
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            bot_settings=DefaultBotProperties(parse_mode="HTML")
        )
        webhook_requests_handler.register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)

        logging.info("Starting webhook server...")
        await web._run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)
    except Exception as e:
        logging.error(f"Ishga tushirishda xato: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())