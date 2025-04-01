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

# Logging sozlamalari
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 🔑 Token va Admin ID
TOKEN = "7400356855:AAH16xmEED2fc0NaaQH9XFEJuhqZn-D3nvY"
ADMIN_ID = 7865739071  # Admin ID
ADMIN_USERNAME = "@Mr_Beck07"  # Admin username

# 📌 Botni ishga tushirish funksiyasi (faqat proxysiz)
async def initialize_bot():
    global bot
    try:
        logging.info("Proxysiz ulanishga urinish...")
        bot = Bot(
            token=TOKEN,
            default=DefaultBotProperties(parse_mode="HTML")
        )
        await bot.get_me()
        logging.info("Bot proxysiz muvaffaqiyatli ulandi.")
        return bot
    except Exception as e:
        logging.error(f"Proxysiz ulanishda xato: {str(e)}")
        raise Exception("Botni ishga tushirib bo‘lmadi: proxysiz ulanish muvaffaqiyatsiz.")

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

# 📌 Lokatsiyalar jadvali (qo'shimcha ma'lumotlar bilan)
cursor.execute("DROP TABLE IF EXISTS locations")
cursor.execute("""
    CREATE TABLE locations (
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
        comment TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

# 🔹 Foydalanuvchi ma'lumotlarini so‘rash uchun holatlar
class UserRegistration(StatesGroup):
    full_name = State()
    work_place = State()
    position = State()

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

# 🔹 /start buyrug‘i
@dp.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    cursor.execute("SELECT approved FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if result:
        if result[0] == 1:
            await message.reply("✅ Siz allaqachon tasdiqlangansiz. Tizimdan foydalanishingiz mumkin!",
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

# 🔹 Admin yordam (imkoniyatlar ro‘yxati)
@dp.message(Command("help"))
async def help_command(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    await message.reply("🛠 Admin imkoniyatlari:\n\n"
                        "✅ /approve foydalanuvchi_id - Foydalanuvchini tasdiqlash\n"
                        "❌ /reject foydalanuvchi_id - Foydalanuvchini rad etish\n"
                        "⛔ /revoke foydalanuvchi_id - Foydalanuvchi ruxsatini bekor qilish\n"
                        "📋 /list_users - Tasdiqlangan foydalanuvchilar ro‘yxati\n"
                        "📍 /add [kod nom] url - Lokatsiya qo‘shish (oldingi ikkita rasm va qo'shimcha ma'lumotdan so‘ng)\n"
                        "🗑 /delete kod - Lokatsiya o‘chirish\n"
                        "🌍 /list_locations - Lokatsiyalar ro‘yxati\n"
                        "🔄 /reset_add - Lokatsiya qo‘shish jarayonini qayta boshlash\n"
                        "💬 /add_comment komment - Baza haqida kommentariya qo‘shish\n"
                        "📜 /view_comments - Baza haqidagi kommentariyalarni ko‘rish\n"
                        "ℹ️ /help - Ushbu yordam menyusi",
                        protect_content=True)

# 🔹 Admin tasdiqlash
@dp.message(Command("approve"))
async def approve_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    command_parts = message.text.split()
    if len(command_parts) != 2:
        return await message.reply("❌ Xato! Format: /approve foydalanuvchi_id\nMasalan: /approve 12345",
                                   protect_content=True)

    try:
        user_id = int(command_parts[1])
        cursor.execute("UPDATE users SET approved = 1 WHERE user_id = ?", (user_id,))
        if cursor.rowcount == 0:
            return await message.reply("❌ Bunday foydalanuvchi topilmadi!", protect_content=True)
        conn.commit()

        await message.reply(f"✅ Foydalanuvchi (🆔 {user_id}) tasdiqlandi.", protect_content=True)
        await bot.send_message(user_id, "✅ Admin sizga ruxsat berdi. Endi tizimdan foydalanishingiz mumkin!",
                              reply_markup=get_user_keyboard(), protect_content=True)
    except ValueError:
        await message.reply("❌ Xato! Foydalanuvchi ID raqam bo‘lishi kerak.\nMasalan: /approve 12345",
                            protect_content=True)
    except Exception as e:
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Admin rad etish
@dp.message(Command("reject"))
async def reject_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    command_parts = message.text.split()
    if len(command_parts) != 2:
        return await message.reply("❌ Xato! Format: /reject foydalanuvchi_id\nMasalan: /reject 12345",
                                   protect_content=True)

    try:
        user_id = int(command_parts[1])
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        if cursor.rowcount == 0:
            return await message.reply("❌ Bunday foydalanuvchi topilmadi!", protect_content=True)
        conn.commit()

        await message.reply(f"❌ Foydalanuvchi (🆔 {user_id}) rad etildi.", protect_content=True)
        await bot.send_message(user_id, "❌ Admin sizning ro‘yxatingizni rad etdi. "
                                       "Qayta urinib ko‘rish uchun /start ni bosing.",
                              reply_markup=get_user_keyboard(), protect_content=True)
    except ValueError:
        await message.reply("❌ Xato! Foydalanuvchi ID raqam bo‘lishi kerak.\nMasalan: /reject 12345",
                            protect_content=True)
    except Exception as e:
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Admin ruxsatni bekor qilish
@dp.message(Command("revoke"))
async def revoke_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    command_parts = message.text.split()
    if len(command_parts) != 2:
        return await message.reply("❌ Xato! Format: /revoke foydalanuvchi_id\nMasalan: /revoke 12345",
                                   protect_content=True)

    try:
        user_id = int(command_parts[1])
        cursor.execute("UPDATE users SET approved = 0 WHERE user_id = ?", (user_id,))
        if cursor.rowcount == 0:
            return await message.reply("❌ Bunday foydalanuvchi topilmadi!", protect_content=True)
        conn.commit()

        await message.reply(f"⛔ Foydalanuvchi (🆔 {user_id}) ruxsati bekor qilindi.", protect_content=True)
        await bot.send_message(user_id, "⛔ Admin sizning ruxsatingizni bekor qildi. Endi tizimdan foydalana olmaysiz.",
                              reply_markup=get_user_keyboard(), protect_content=True)
    except ValueError:
        await message.reply("❌ Xato! Foydalanuvchi ID raqam bo‘lishi kerak.\nMasalan: /revoke 12345",
                            protect_content=True)
    except Exception as e:
        await message.reply(f"❌ Xatolik yuz berdi: {str(e)}", protect_content=True)

# 🔹 Tasdiqlangan foydalanuvchilarni ro‘yxatini ko‘rish
@dp.message(Command("list_users"))
async def list_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    cursor.execute("SELECT user_id, full_name, work_place, position FROM users WHERE approved = 1")
    users = cursor.fetchall()

    if not users:
        return await message.reply("📋 Tasdiqlangan foydalanuvchilar mavjud emas.", protect_content=True)

    response = f"📋 Tasdiqlangan foydalanuvchilar ro‘yxati ({len(users)} ta):\n\n"
    for user in users:
        user_id, full_name, work_place, position = user
        response += f"🆔 ID: {user_id}\n👤 Familiya va ism: {full_name}\n🏢 Ish joyi: {work_place}\n💼 Lavozim: {position}\n\n"

    await message.reply(response, protect_content=True)

# 🔹 Lokatsiyalar ro‘yxatini ko‘rish (qo'shimcha ma'lumotlar bilan)
@dp.message(Command("list_locations"))
async def list_locations(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    cursor.execute("SELECT code, name, latitude, longitude, additional_info FROM locations")
    locations = cursor.fetchall()

    if not locations:
        return await message.reply("🌍 Hozircha lokatsiyalar mavjud emas.", protect_content=True)

    response = f"🌍 Lokatsiyalar ro‘yxati ({len(locations)} ta):\n\n"
    for loc in locations:
        code, name, lat, lon, additional_info = loc
        map_url = f"http://maps.google.com/maps?q={lat},{lon}&z=16"
        response += f"📍 Kod: {code}\n🏞 Nom: {name}\n🌐 Koordinatalar: {lat}, {lon}\n"
        if additional_info:
            response += f"📝 Qo'shimcha ma'lumot: {additional_info}\n"
        response += f"<a href='{map_url}'>Xaritada</a>\n\n"

    await message.reply(response, protect_content=True, disable_web_page_preview=True)

# 🔹 Baza haqida kommentariya qo‘shish
@dp.message(Command("add_comment"))
async def add_comment(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        return await message.reply("❌ Xato! Format: /add_comment komment\nMasalan: /add_comment Bu baza 2025-yilda yangilandi",
                                   protect_content=True)

    comment = parts[1].strip()
    cursor.execute("INSERT INTO db_comments (comment) VALUES (?)", (comment,))
    conn.commit()

    await message.reply(f"💬 Kommentariya qo‘shildi: {comment}", protect_content=True)

# 🔹 Baza haqidagi kommentariyalarni ko‘rish
@dp.message(Command("view_comments"))
async def view_comments(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    cursor.execute("SELECT id, comment, timestamp FROM db_comments ORDER BY timestamp DESC")
    comments = cursor.fetchall()

    if not comments:
        return await message.reply("📜 Hozircha baza haqida kommentariyalar mavjud emas.", protect_content=True)

    response = f"📜 Baza haqidagi kommentariyalar ({len(comments)} ta):\n\n"
    for comment in comments:
        comment_id, text, timestamp = comment
        response += f"🆔 ID: {comment_id}\n💬 Komment: {text}\n⏰ Vaqt: {timestamp}\n\n"

    await message.reply(response, protect_content=True)

# 🔹 Admin lokatsiya qo‘shish jarayonini qayta boshlash
@dp.message(Command("reset_add"))
async def reset_add(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    await state.clear()
    await message.reply("🔄 Lokatsiya qo‘shish jarayoni qayta boshlandi. Birinchi rasmni yuboring.",
                        protect_content=True)
    await state.set_state(AddLocationState.waiting_for_first_photo)

# 🔹 Admin birinchi rasmni yuborishi
@dp.message(lambda message: message.from_user.id == ADMIN_ID and message.photo, AddLocationState.waiting_for_first_photo)
async def process_first_photo(message: Message, state: FSMContext):
    photo1 = message.photo[-1].file_id
    await state.update_data(photo1=photo1)
    await message.reply("📸 Birinchi rasm qabul qilindi. Endi ikkinchi rasmni yuboring.",
                        protect_content=True)
    await state.set_state(AddLocationState.waiting_for_second_photo)

# 🔹 Admin ikkinchi rasmni yuborishi
@dp.message(lambda message: message.from_user.id == ADMIN_ID and message.photo, AddLocationState.waiting_for_second_photo)
async def process_second_photo(message: Message, state: FSMContext):
    photo2 = message.photo[-1].file_id
    await state.update_data(photo2=photo2)
    await message.reply("📸 Ikkita rasm qabul qilindi. Endi qo'shimcha ma'lumotlarni yuboring (agar kerak bo'lmasa, 'yo'q' deb yozing):",
                        protect_content=True)
    await state.set_state(AddLocationState.waiting_for_additional_info)

# 🔹 Admin qo'shimcha ma'lumotlarni yuborishi
@dp.message(AddLocationState.waiting_for_additional_info)
async def process_additional_info(message: Message, state: FSMContext):
    additional_info = message.text.strip()
    if additional_info.lower() == "yo'q":
        additional_info = None
    await state.update_data(additional_info=additional_info)
    await message.reply("📝 Qo'shimcha ma'lumotlar qabul qilindi. Endi /add [kod nom] url yuboring.\n"
                        "Masalan: /add [3700 Aktash] http://maps.google.com/maps?q=39.919719,65.929442",
                        protect_content=True)
    await state.set_state(AddLocationState.waiting_for_command)

# 🔹 Admin lokatsiya qo‘shishi (/add buyrug‘i)
@dp.message(Command("add"))
async def add_location(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    # Holatni tekshirish
    current_state = await state.get_state()
    if current_state != AddLocationState.waiting_for_command.state:
        await message.reply("❌ Oldin ikkita rasm va qo'shimcha ma'lumotlarni yuboring! Birinchi rasmni yuborishdan boshlang.\n"
                            "Agar jarayonni qayta boshlamoqchi bo‘lsangiz, /reset_add buyrug‘ini ishlatishingiz mumkin.",
                            protect_content=True)
        await state.set_state(AddLocationState.waiting_for_first_photo)
        return

    # Formatni tekshirish
    match = re.match(r"/add\s+\[(\d+)\s+(.+?)\]\s+(http://maps.google.com/maps\?q=(-?\d+\.\d+),(-?\d+\.\d+)[^\s]*)", message.text)
    if not match:
        await message.reply("❌ Xato! Format: /add [3700 Aktash] http://maps.google.com/maps?q=39.919719,65.929442",
                            protect_content=True)
        return

    code, name, url, lat, lon = match.groups()
    lat, lon = float(lat), float(lon)
    user_data = await state.get_data()

    photo1 = user_data.get("photo1")
    photo2 = user_data.get("photo2")
    additional_info = user_data.get("additional_info")

    if not photo1 or not photo2:
        await message.reply("❌ Ikkita rasm yuborilmadi! Birinchi rasmni yuborishdan boshlang.\n"
                            "Agar jarayonni qayta boshlamoqchi bo‘lsangiz, /reset_add buyrug‘ini ishlatishingiz mumkin.",
                            protect_content=True)
        await state.set_state(AddLocationState.waiting_for_first_photo)
        return

    cursor.execute("INSERT OR REPLACE INTO locations (code, name, latitude, longitude, photo1, photo2, additional_info) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (code, name, lat, lon, photo1, photo2, additional_info))
    conn.commit()

    await message.reply(f"✅ [{code} {name}] lokatsiya qo‘shildi!\n📍 <a href='{url}'>Xaritada ko‘rish</a>",
                        protect_content=True, disable_web_page_preview=True)
    await state.clear()

# 🔹 Admin lokatsiya o‘chirish
@dp.message(Command("delete"))
async def delete_location(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Sizda ushbu buyruqni bajarish huquqi yo‘q.", protect_content=True)

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        return await message.reply("❌ Xato! Format: /delete 3700", protect_content=True)

    code = parts[1].strip()
    cursor.execute("DELETE FROM locations WHERE code = ?", (code,))
    conn.commit()

    await message.reply(f"🗑 [{code}] kodli joy o‘chirildi.", protect_content=True)

# 🔹 Foydalanuvchi lokatsiya so‘rashi (qo'shimcha ma'lumotlar bilan)
@dp.message()
async def get_location(message: Message):
    # Agar xabar matn bo‘lmasa yoki buyruq bo‘lsa, e'tiborsiz qoldirish
    if not message.text or message.text.startswith("/"):
        return

    user_id = message.from_user.id
    cursor.execute("SELECT approved FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if not result or result[0] == 0:
        return await message.reply("❌ Siz admin ruxsatini olmagansiz. ⏳ Iltimos, admin tasdiqini kuting.",
                                   reply_markup=get_user_keyboard(), protect_content=True)

    code = message.text.strip()
    cursor.execute("SELECT name, latitude, longitude, photo1, photo2, additional_info FROM locations WHERE code = ?", (code,))
    result = cursor.fetchone()

    if result:
        name, lat, lon, photo1, photo2, additional_info = result
        map_url = f"http://maps.google.com/maps?q={lat},{lon}&z=16"
        caption = f"📍 [{code} {name}]\n🌍 <a href='{map_url}'>Google xaritada ochish</a>"
        if additional_info:
            caption += f"\n📝 Qo'shimcha ma'lumot: {additional_info}"

        # Ikkita rasmni guruh sifatida yuborish (protect_content=True qo‘shildi)
        media = [
            types.InputMediaPhoto(media=photo1, caption=caption, parse_mode="HTML"),
            types.InputMediaPhoto(media=photo2)
        ]
        await bot.send_media_group(chat_id=user_id, media=media, protect_content=True)
        await message.reply("Yuqoridagi rasmlar bilan lokatsiya yuborildi.", reply_markup=get_user_keyboard(),
                            protect_content=True)
    else:
        await message.reply("❌ Bunday bazaviy stansiya topilmadi yoki hali bazaga qo‘shilmagan!",
                            reply_markup=get_user_keyboard(), protect_content=True)

# 🔹 Foydalanuvchi rasm yuborsa (admin bo‘lmagan foydalanuvchilar uchun)
@dp.message(lambda message: message.from_user.id != ADMIN_ID and message.photo)
async def handle_user_photo(message: Message):
    await message.reply("❌ Faqat lokatsiya kodi yuborishingiz mumkin (masalan, 3700). Rasm yuborish mumkin emas!",
                        reply_markup=get_user_keyboard(), protect_content=True)

# 🔹 Inline tugmalarga javob
@dp.callback_query()
async def process_callback(callback: types.CallbackQuery):
    if callback.data == "help":
        await callback.message.edit_text("ℹ️ Botdan foydalanish: Lokatsiya kodini yuboring (masalan, 3700). "
                                        "Admin tasdiqini kutayotgan bo‘lsangiz, kuting.",
                                        reply_markup=get_user_keyboard(), protect_content=True)
    elif callback.data == "contact":
        await callback.message.edit_text(f"📞 Aloqa: Admin bilan bog‘lanish uchun {ADMIN_USERNAME} ga yozing.",
                                        reply_markup=get_user_keyboard(), protect_content=True)
    await callback.answer()

# 📌 Botni ishga tushirish
async def main():
    global bot
    while True:  # Qayta urinish uchun tsikl
        try:
            # Botni ishga tushiramiz (faqat proxysiz)
            bot = await initialize_bot()
            logging.info("Polling boshlandi...")
            await dp.start_polling(bot)
            break  # Agar muvaffaqiyatli ulansa, tsikl to'xtaydi
        except Exception as e:
            logging.error(f"Botni ishga tushirishda xato: {str(e)}")
            await asyncio.sleep(5)  # 5 soniya kutib qayta urinish

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())