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

# 📜 Logging sozlamalari
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 🔑 Token va Admin ma'lumotlari
TOKEN = "7400356855:AAH16xmEED2fc0NaaQH9XFEJuhqZn-D3nvY"  # Tokenni tekshiring!
ADMIN_ID = 7865739071
ADMIN_USERNAME = "@Mr_Beck07"

# 🌐 Webhook sozlamalari
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://bs-bot-production.up.railway.app{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.environ.get("PORT", 8080))  # Railway PORT muhit o‘zgaruvchisi

# 🤖 Botni ishga tushirish funksiyasi
async def initialize_bot():
    global bot
    try:
        logging.info("🤖 Botni ishga tushirish...")
        bot = Bot(
            token=TOKEN,
            default=DefaultBotProperties(parse_mode="HTML")
        )
        bot_info = await bot.get_me()
        logging.info(f"✅ Bot muvaffaqiyatli ulandi: @{bot_info.username}")
        return bot
    except Exception as e:
        logging.error(f"❌ Botni ulashda xato: {str(e)}")
        raise Exception(f"Botni ishga tushirib bo‘lmadi: {str(e)}")

# 📦 Dispatcher va storage
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# 🗄️ SQLite bazasini yaratish
conn = sqlite3.connect("database.db", check_same_thread=False)  # Thread-safe qilish uchun
cursor = conn.cursor()

# 📋 Jadval yaratish funksiyasi
def init_db():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            work_place TEXT,
            position TEXT,
            approved INTEGER DEFAULT 0
        )
    """)
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS db_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            comment TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("SELECT user_id FROM db_comments LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE db_comments ADD COLUMN user_id INTEGER")
        logging.info("📋 user_id ustuni db_comments jadvaliga qo‘shildi.")
    conn.commit()

# 🗄️ Bazani ishga tushirish
init_db()

# 🛠️ Holatlar (States)
class UserRegistration(StatesGroup):
    full_name = State()
    work_place = State()
    position = State()

class UserCommentState(StatesGroup):
    waiting_for_comment = State()

class UserSearchLocationState(StatesGroup):
    waiting_for_location_code = State()

class AddLocationState(StatesGroup):
    waiting_for_first_photo = State()
    waiting_for_second_photo = State()
    waiting_for_additional_info = State()
    waiting_for_command = State()

# 🎨 Inline tugmalar
def get_user_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help"),
         InlineKeyboardButton(text="📞 Aloqa", callback_data="contact")]
    ])

def get_location_action_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Kommentariya yozish", callback_data="write_comment"),
         InlineKeyboardButton(text="🔍 Lokatsiya qidirish", callback_data="search_location")],
        [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help"),
         InlineKeyboardButton(text="📞 Aloqa", callback_data="contact")]
    ])

# 🚀 /start buyrug‘i
@dp.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    cursor.execute("SELECT approved FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if result:
        if result[0] == 1:
            await message.reply("✅ Siz tasdiqlangansiz! Lokatsiya kodini yuboring (masalan, 3700):",
                                reply_markup=get_user_keyboard(), protect_content=True)
        else:
            await message.reply("⏳ Ma'lumotlaringiz adminga yuborilgan. Admin ruxsatini kuting.",
                                reply_markup=get_user_keyboard(), protect_content=True)
        return

    await message.reply("👋 Assalomu alaykum! Ro‘yxatdan o‘tish uchun ma'lumotlaringizni kiriting.\n"
                        "👤 Familiyangiz va ismingizni yozing:",
                        reply_markup=get_user_keyboard(), protect_content=True)
    await state.set_state(UserRegistration.full_name)

# 📝 Ro‘yxatdan o‘tish jarayoni
@dp.message(UserRegistration.full_name)
async def process_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.reply("🏢 Ish joyingizni yozing:", reply_markup=get_user_keyboard(), protect_content=True)
    await state.set_state(UserRegistration.work_place)

@dp.message(UserRegistration.work_place)
async def process_work_place(message: Message, state: FSMContext):
    await state.update_data(work_place=message.text)
    await message.reply("💼 Lavozimingizni yozing:", reply_markup=get_user_keyboard(), protect_content=True)
    await state.set_state(UserRegistration.position)

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

        await bot.send_message(ADMIN_ID, f"📋 Yangi foydalanuvchi:\n"
                                       f"🆔 ID: {user_id}\n"
                                       f"👤 {full_name}\n"
                                       f"🏢 {work_place}\n"
                                       f"💼 {position}\n\n"
                                       f"✅ /approve {user_id}\n"
                                       f"❌ /reject {user_id}\n"
                                       f"⛔ /revoke {user_id}",
                                       protect_content=True)
        await message.reply("✅ Ma'lumotlaringiz adminga yuborildi. ⏳ Admin ruxsatini kuting.",
                            reply_markup=get_user_keyboard(), protect_content=True)
        await state.clear()
    except Exception as e:
        logging.error(f"❌ Foydalanuvchi qo‘shishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik: {str(e)}", protect_content=True)

# 🛠️ Admin buyruqlari
@dp.message(Command("help"))
async def help_command(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Bu buyruq faqat admin uchun!", protect_content=True)
    await message.reply("🛠️ Admin buyruqlari:\n"
                        "✅ /approve id - Foydalanuvchini tasdiqlash\n"
                        "❌ /reject id - Foydalanuvchini rad etish\n"
                        "⛔ /revoke id - Foydalanuvchi ruxsatini bekor qilish\n"
                        "📋 /list_users - Tasdiqlangan foydalanuvchilar ro‘yxati\n"
                        "📍 /add [kod nom] url - Lokatsiya qo‘shish\n"
                        "🗑️ /delete kod - Lokatsiyani o‘chirish\n"
                        "🌍 /list_locations - Lokatsiyalar ro‘yxati\n"
                        "🔄 /reset_add - Lokatsiya qo‘shishni qayta boshlash\n"
                        "💬 /add_comment tekst - Kommentariya qo‘shish\n"
                        "📜 /view_comments - Kommentariyalarni ko‘rish\n"
                        "ℹ️ /help - Yordam", protect_content=True)

@dp.message(Command("approve"))
async def approve_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Bu buyruq faqat admin uchun!", protect_content=True)
    try:
        user_id = int(message.text.split()[1])
        cursor.execute("UPDATE users SET approved = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return await message.reply("❌ Foydalanuvchi topilmadi!", protect_content=True)
        await message.reply(f"✅ Foydalanuvchi (ID: {user_id}) tasdiqlandi.", protect_content=True)
        await bot.send_message(user_id, "✅ Admin sizga ruxsat berdi. Lokatsiya kodini yuboring (masalan, 3700):",
                              reply_markup=get_user_keyboard(), protect_content=True)
    except (IndexError, ValueError):
        await message.reply("❌ Format: /approve foydalanuvchi_id", protect_content=True)
    except Exception as e:
        logging.error(f"❌ Tasdiqlashda xato: {str(e)}")
        await message.reply(f"❌ Xatolik: {str(e)}", protect_content=True)

@dp.message(Command("reject"))
async def reject_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Bu buyruq faqat admin uchun!", protect_content=True)
    try:
        user_id = int(message.text.split()[1])
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return await message.reply("❌ Foydalanuvchi topilmadi!", protect_content=True)
        await message.reply(f"❌ Foydalanuvchi (ID: {user_id}) rad etildi.", protect_content=True)
        await bot.send_message(user_id, "❌ Admin sizni rad etdi. /start bilan qayta ro‘yxatdan o‘ting.",
                              reply_markup=get_user_keyboard(), protect_content=True)
    except (IndexError, ValueError):
        await message.reply("❌ Format: /reject foydalanuvchi_id", protect_content=True)
    except Exception as e:
        logging.error(f"❌ Rad etishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik: {str(e)}", protect_content=True)

@dp.message(Command("revoke"))
async def revoke_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Bu buyruq faqat admin uchun!", protect_content=True)
    try:
        user_id = int(message.text.split()[1])
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return await message.reply("❌ Foydalanuvchi topilmadi!", protect_content=True)
        await message.reply(f"⛔ Foydalanuvchi (ID: {user_id}) ruxsati bekor qilindi.", protect_content=True)
        await bot.send_message(user_id, "⛔ Admin ruxsatingizni bekor qildi. /start bilan qayta ro‘yxatdan o‘ting.",
                              reply_markup=get_user_keyboard(), protect_content=True)
    except (IndexError, ValueError):
        await message.reply("❌ Format: /revoke foydalanuvchi_id", protect_content=True)
    except Exception as e:
        logging.error(f"❌ Ruxsat bekor qilishda xato: {str(e)}")
        await message.reply(f"❌ Xatolik: {str(e)}", protect_content=True)

@dp.message(Command("list_users"))
async def list_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Bu buyruq faqat admin uchun!", protect_content=True)
    cursor.execute("SELECT user_id, full_name, work_place, position FROM users WHERE approved = 1")
    users = cursor.fetchall()
    if not users:
        return await message.reply("📋 Tasdiqlangan foydalanuvchilar yo‘q.", protect_content=True)
    response = f"📋 Tasdiqlangan foydalanuvchilar ({len(users)}):\n\n"
    for user in users:
        response += f"🆔 {user[0]}\n👤 {user[1]}\n🏢 {user[2]}\n💼 {user[3]}\n\n"
    await message.reply(response, protect_content=True)

@dp.message(Command("list_locations"))
async def list_locations(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Bu buyruq faqat admin uchun!", protect_content=True)
    cursor.execute("SELECT code, name, latitude, longitude, additional_info FROM locations")
    locations = cursor.fetchall()
    if not locations:
        return await message.reply("🌍 Lokatsiyalar yo‘q.", protect_content=True)
    response = f"🌍 Lokatsiyalar ({len(locations)}):\n\n"
    for i, loc in enumerate(locations, 1):
        map_url = f"http://maps.google.com/maps?q={loc[2]},{loc[3]}&z=16"
        response += f"{i}. 📍 {loc[0]} - {loc[1]}\n🌐 {loc[2]}, {loc[3]}\n"
        if loc[4]:
            response += f"📝 {loc[4]}\n"
        response += f"<a href='{map_url}'>Xaritada</a>\n\n"
    await message.reply(response, protect_content=True, disable_web_page_preview=True)

@dp.message(Command("add_comment"))
async def add_comment(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Bu buyruq faqat admin uchun!", protect_content=True)
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        return await message.reply("❌ Format: /add_comment komment", protect_content=True)
    comment = parts[1].strip()
    cursor.execute("INSERT INTO db_comments (user_id, comment) VALUES (?, ?)", (ADMIN_ID, comment))
    conn.commit()
    await message.reply(f"💬 Kommentariya qo‘shildi: {comment}", protect_content=True)

@dp.message(Command("view_comments"))
async def view_comments(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Bu buyruq faqat admin uchun!", protect_content=True)
    cursor.execute("SELECT dc.id, dc.user_id, dc.comment, dc.timestamp, u.full_name FROM db_comments dc "
                   "LEFT JOIN users u ON dc.user_id = u.user_id ORDER BY dc.timestamp DESC")
    comments = cursor.fetchall()
    if not comments:
        return await message.reply("📜 Kommentariyalar yo‘q.", protect_content=True)
    response = f"📜 Kommentariyalar ({len(comments)}):\n\n"
    for c in comments:
        full_name = c[4] or "Noma'lum"
        response += f"🆔 {c[0]}\n👤 {full_name} (ID: {c[1]})\n💬 {c[2]}\n⏰ {c[3]}\n\n"
    await message.reply(response, protect_content=True)

# 📍 Lokatsiya qo‘shish jarayoni
@dp.message(Command("reset_add"))
async def reset_add(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Bu buyruq faqat admin uchun!", protect_content=True)
    await state.clear()
    await message.reply("🔄 Lokatsiya qo‘shish qayta boshlandi. Birinchi rasmni yuboring.", protect_content=True)
    await state.set_state(AddLocationState.waiting_for_first_photo)

@dp.message(lambda message: message.from_user.id == ADMIN_ID and message.photo, AddLocationState.waiting_for_first_photo)
async def process_first_photo(message: Message, state: FSMContext):
    photo1 = message.photo[-1].file_id
    await state.update_data(photo1=photo1)
    await message.reply("📸 Birinchi rasm qabul qilindi. Ikkichi rasmni yuboring.", protect_content=True)
    await state.set_state(AddLocationState.waiting_for_second_photo)

@dp.message(lambda message: message.from_user.id == ADMIN_ID and message.photo, AddLocationState.waiting_for_second_photo)
async def process_second_photo(message: Message, state: FSMContext):
    photo2 = message.photo[-1].file_id
    await state.update_data(photo2=photo2)
    await message.reply("📸 Ikkita rasm qabul qilindi. Qo'shimcha ma'lumot yuboring (yo'q deb yozing agar kerak bo'lmasa):",
                        protect_content=True)
    await state.set_state(AddLocationState.waiting_for_additional_info)

@dp.message(AddLocationState.waiting_for_additional_info)
async def process_additional_info(message: Message, state: FSMContext):
    additional_info = message.text.strip() if message.text.strip().lower() != "yo'q" else None
    await state.update_data(additional_info=additional_info)
    await message.reply("📝 Ma'lumot qabul qilindi. /add [kod nom] url yuboring.\nMasalan: /add [3700 Aktash] http://maps.google.com/maps?q=39.919719,65.929442",
                        protect_content=True)
    await state.set_state(AddLocationState.waiting_for_command)

@dp.message(Command("add"))
async def add_location(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Bu buyruq faqat admin uchun!", protect_content=True)
    current_state = await state.get_state()
    if current_state != AddLocationState.waiting_for_command.state:
        await message.reply("❌ Oldin ikkita rasm va ma'lumot yuboring! /reset_add bilan qayta boshlang.", protect_content=True)
        await state.set_state(AddLocationState.waiting_for_first_photo)
        return
    match = re.match(r"/add\s+\[(\d+)\s+(.+?)\]\s+(http://maps.google.com/maps\?q=(-?\d+\.\d+),(-?\d+\.\d+)[^\s]*)", message.text)
    if not match:
        return await message.reply("❌ Format: /add [3700 Aktash] http://maps.google.com/maps?q=39.919719,65.929442", protect_content=True)
    code, name, url, lat, lon = match.groups()
    user_data = await state.get_data()
    photo1, photo2, additional_info = user_data.get("photo1"), user_data.get("photo2"), user_data.get("additional_info")
    if not photo1 or not photo2:
        await message.reply("❌ Ikkita rasm yuborilmadi! /reset_add bilan qayta boshlang.", protect_content=True)
        await state.set_state(AddLocationState.waiting_for_first_photo)
        return
    cursor.execute("INSERT OR REPLACE INTO locations (code, name, latitude, longitude, photo1, photo2, additional_info) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)", (code, name, float(lat), float(lon), photo1, photo2, additional_info))
    conn.commit()
    await message.reply(f"✅ [{code} {name}] qo‘shildi!\n📍 <a href='{url}'>Xaritada</a>",
                        protect_content=True, disable_web_page_preview=True)
    await state.clear()

@dp.message(Command("delete"))
async def delete_location(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Bu buyruq faqat admin uchun!", protect_content=True)
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        return await message.reply("❌ Format: /delete 3700", protect_content=True)
    code = parts[1].strip()
    cursor.execute("DELETE FROM locations WHERE code = ?", (code,))
    conn.commit()
    await message.reply(f"🗑️ [{code}] o‘chirildi.", protect_content=True)

# 📍 Foydalanuvchi lokatsiya so‘rashi
@dp.message()
async def get_location(message: Message, state: FSMContext):
    # Agar holat mavjud bo‘lsa, bu funksiya ishlamasligi kerak
    current_state = await state.get_state()
    if current_state is not None:
        return  # Holat mavjud bo‘lsa, hech narsa qilmaymiz

    if not message.text or message.text.startswith("/"):
        return
    user_id = message.from_user.id
    cursor.execute("SELECT approved FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if not result or result[0] == 0:
        return await message.reply("❌ Admin ruxsatini olmagansiz. ⏳ Tasdiqni kuting.", reply_markup=get_user_keyboard(), protect_content=True)
    code = message.text.strip()
    if not code.isdigit():
        return await message.reply("❌ Kod faqat raqamlardan iborat bo‘lishi kerak (masalan, 3700)!", reply_markup=get_user_keyboard(), protect_content=True)
    cursor.execute("SELECT name, latitude, longitude, photo1, photo2, additional_info FROM locations WHERE code = ?", (code,))
    result = cursor.fetchone()
    if not result:
        return await message.reply("❌ Kod topilmadi! Admin bilan bog‘laning.", reply_markup=get_user_keyboard(), protect_content=True)
    name, lat, lon, photo1, photo2, additional_info = result
    map_url = f"http://maps.google.com/maps?q={lat},{lon}&z=16"
    caption = f"📍 [{code} {name}]\n🌍 <a href='{map_url}'>Xaritada</a>"
    if additional_info:
        caption += f"\n📝 {additional_info}"
    media = [
        types.InputMediaPhoto(media=photo1, caption=caption, parse_mode="HTML"),
        types.InputMediaPhoto(media=photo2)
    ]
    await bot.send_media_group(chat_id=user_id, media=media, protect_content=True)
    cursor.execute("INSERT INTO db_comments (user_id, comment) VALUES (?, ?)", (user_id, f"{code} kodli lokatsiyani oldi"))
    conn.commit()
    await message.reply("📍 Yuqoridagi lokatsiya yuborildi. Tanlang:", reply_markup=get_location_action_keyboard(), protect_content=True)
    await state.update_data(location_code=code)

# 🎮 Inline tugmalar bilan ishlash
@dp.callback_query()
async def process_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    cursor.execute("SELECT approved FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if not result or result[0] == 0:
        await callback.message.reply("❌ Admin ruxsatini olmagansiz!", reply_markup=get_user_keyboard(), protect_content=True)
        return await callback.answer()

    if callback.data == "write_comment":
        user_data = await state.get_data()
        location_code = user_data.get("location_code")
        if not location_code:
            await callback.message.reply("❌ Avval lokatsiya kodini yuboring!", reply_markup=get_user_keyboard(), protect_content=True)
            return await callback.answer()
        await callback.message.reply("❓ Nima maqsadda bordiz va nima o'zgartirdingiz? Javobingizni yozing:",
                                    reply_markup=get_user_keyboard(), protect_content=True)
        await state.set_state(UserCommentState.waiting_for_comment)
        await state.update_data(location_code=location_code, has_commented=False)  # Kommentariya yozilmagan deb belgilaymiz

    elif callback.data == "search_location":
        await callback.message.reply("🔍 Yangi lokatsiya kodini yuboring (masalan, 3700):", reply_markup=get_user_keyboard(), protect_content=True)
        await state.set_state(UserSearchLocationState.waiting_for_location_code)

    elif callback.data == "help":
        await callback.message.edit_text("ℹ️ Lokatsiya kodini yuboring (masalan, 3700).", reply_markup=get_user_keyboard(), protect_content=True)

    elif callback.data == "contact":
        await callback.message.edit_text(f"📞 {ADMIN_USERNAME} ga yozing.", reply_markup=get_user_keyboard(), protect_content=True)

    await callback.answer()

# 💬 Foydalanuvchi kommentariyasini qabul qilish
@dp.message(UserCommentState.waiting_for_comment)
async def process_user_comment(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = await state.get_data()
    location_code = user_data.get("location_code")
    has_commented = user_data.get("has_commented", False)

    if not location_code:
        await message.reply("❌ Lokatsiya kodi topilmadi. Iltimos, qaytadan lokatsiya kodini yuboring.",
                            reply_markup=get_user_keyboard(), protect_content=True)
        await state.clear()
        return

    if has_commented:
        await message.reply("❌ Siz allaqachon kommentariya yozdingiz. Yangi lokatsiya kodini yuboring (masalan, 3700):",
                            reply_markup=get_user_keyboard(), protect_content=True)
        await state.clear()
        return

    comment_text = message.text.strip()
    try:
        cursor.execute("INSERT INTO db_comments (user_id, comment) VALUES (?, ?)",
                       (user_id, f"[{location_code}] bo'yicha: {comment_text}"))
        conn.commit()
        await message.reply("✅ Sizning javobingiz saqlandi. Rahmat!\nYangi lokatsiya kodini yuboring (masalan, 3700):",
                            reply_markup=get_user_keyboard(), protect_content=True)
        await state.update_data(has_commented=True)  # Kommentariya yozildi deb belgilaymiz
        await state.clear()  # Holatni tozalaymiz va asosiy menyuga qaytamiz
    except Exception as e:
        logging.error(f"❌ Foydalanuvchi kommentariyasini saqlashda xato: {str(e)}")
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)
        await state.clear()

# 🔍 Foydalanuvchi yangi lokatsiya kodi yuborishi
@dp.message(UserSearchLocationState.waiting_for_location_code)
async def process_search_location(message: Message, state: FSMContext):
    await get_location(message, state)
    await state.clear()

# 📸 Foydalanuvchi rasm yuborsa
@dp.message(lambda message: message.from_user.id != ADMIN_ID and message.photo)
async def handle_user_photo(message: Message):
    await message.reply("❌ Faqat lokatsiya kodi yuborishingiz mumkin (masalan, 3700)!", reply_markup=get_user_keyboard(), protect_content=True)

# 🌐 Webhook sozlash
async def on_startup():
    try:
        await bot.set_webhook(WEBHOOK_URL)
        logging.info(f"✅ Webhook o‘rnatildi: {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"❌ Webhook o‘rnatishda xato: {str(e)}")
        raise

async def on_shutdown():
    try:
        await bot.delete_webhook()
        await bot.session.close()
        conn.close()
        logging.info("✅ Bot o‘chirildi.")
    except Exception as e:
        logging.error(f"❌ Botni o‘chirishda xato: {str(e)}")

# 🚀 Botni ishga tushirish
async def main():
    global bot
    try:
        bot = await initialize_bot()
        app = web.Application()
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_requests_handler.register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)
        logging.info(f"🚀 Webhook server ishga tushdi. Port: {WEBAPP_PORT}")
        await web._run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)
    except Exception as e:
        logging.error(f"❌ Ishga tushirishda xato: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())