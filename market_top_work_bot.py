import asyncio
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ===== CONFIG =====
TOKEN = "9126121221:AAHS7Yulv05gfDM8MfW_QjfE8KhcLRLWmEg"
ADMIN_ID = 8510313155
DB = "task_income.db"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ===== DATABASE =====
con = sqlite3.connect(DB)
con.execute("""
CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY,
 balance REAL DEFAULT 0,
 income REAL DEFAULT 0,
 ref_by INTEGER DEFAULT 0
)
""")
con.execute("""
CREATE TABLE IF NOT EXISTS tasks(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 title TEXT,
 link TEXT,
 reward REAL,
 slots INTEGER
)
""")
con.execute("""
CREATE TABLE IF NOT EXISTS submissions(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER,
 task_id INTEGER,
 proof TEXT,
 status TEXT DEFAULT 'pending'
)
""")
con.execute("""
CREATE TABLE IF NOT EXISTS withdrawals(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER,
 method TEXT,
 amount REAL,
 account TEXT,
 status TEXT DEFAULT 'pending'
)
""")
con.commit()


# ===== MENU =====
def menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 কাজ"), KeyboardButton(text="💵 ব্যালেন্স")],
            [KeyboardButton(text="💸 টাকা উত্তোলন"),
             KeyboardButton(text="🎁 My Referrals")],
            [KeyboardButton(text="📞 সাপোর্ট"),
             KeyboardButton(text="👋 আমি নতুন")]
        ],
        resize_keyboard=True
    )


class Form(StatesGroup):
    proof = State()
    method = State()
    amount = State()
    account = State()


# ===== START =====
@dp.message(CommandStart())
async def start(message: Message):
    uid = message.from_user.id
    args = message.text.split()

    con.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))

    if len(args) > 1:
        try:
            ref = int(args[1])
            if ref != uid:
                cur = con.execute(
                    "SELECT ref_by FROM users WHERE id=?", (uid,)
                ).fetchone()
                if cur and not cur[0]:
                    con.execute(
                        "UPDATE users SET ref_by=? WHERE id=?",
                        (ref, uid)
                    )
        except ValueError:
            pass

    con.commit()

    await message.answer(
        "🎉 স্বাগতম আমাদের Task Income Bot-এ!\n\n"
        "📋 কাজ করে আয় করুন।\n"
        "💰 ব্যালেন্স দেখুন।\n"
        "👥 বন্ধুদের রেফার করুন।",
        reply_markup=menu()
    )


# ===== TASK LIST =====
@dp.message(F.text == "📋 কাজ")
async def tasks(message: Message):
    rows = con.execute(
        "SELECT id,title,reward,slots FROM tasks WHERE slots>0"
    ).fetchall()

    if not rows:
        await message.answer("😔 বর্তমানে কোনো কাজ নেই।")
        return

    for tid, title, reward, slots in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="কাজ শুরু করুন",
                callback_data=f"task:{tid}"
            )
        ]])
        await message.answer(
            f"📌 {title}\n💰 পুরস্কার: {reward} টাকা\n"
            f"🎯 বাকি স্লট: {slots}",
            reply_markup=kb
        )


@dp.callback_query(F.data.startswith("task:"))
async def open_task(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    row = con.execute(
        "SELECT title,link,reward,slots FROM tasks WHERE id=?",
        (tid,)
    ).fetchone()

    if not row or row[3] <= 0:
        await call.answer("কাজটি আর নেই!", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ কাজ জমা দিন",
            callback_data=f"submit:{tid}"
        )
    ]])

    await call.message.answer(
        f"📌 {row[0]}\n\n🔗 কাজের লিংক:\n{row[1]}\n\n"
        f"💰 পুরস্কার: {row[2]} টাকা",
        reply_markup=kb
    )
    await call.answer()


# ===== SUBMIT PROOF =====
@dp.callback_query(F.data.startswith("submit:"))
async def submit_task(call: CallbackQuery, state: FSMContext):
    tid = int(call.data.split(":")[1])
    uid = call.from_user.id

    row = con.execute(
        "SELECT slots FROM tasks WHERE id=?", (tid,)
    ).fetchone()

    if not row or row[0] <= 0:
        await call.answer("কাজের স্লট শেষ!", show_alert=True)
        return

    old = con.execute(
        "SELECT id FROM submissions WHERE user_id=? AND task_id=? "
        "AND status IN ('pending','approved')",
        (uid, tid)
    ).fetchone()

    if old:
        await call.answer("আপনি এই কাজ জমা দিয়েছেন!", show_alert=True)
        return

    await state.update_data(task_id=tid)
    await state.set_state(Form.proof)
    await call.message.answer(
        "📸 কাজের স্ক্রিনশট অথবা কাজের প্রমাণ পাঠান।"
    )
    await call.answer()


@dp.message(Form.proof)
async def save_proof(message: Message, state: FSMContext):
    data = await state.get_data()
    tid = data["task_id"]
    uid = message.from_user.id

    row = con.execute(
        "SELECT reward,slots,title FROM tasks WHERE id=?", (tid,)
    ).fetchone()

    if not row or row[1] <= 0:
        await message.answer("দুঃখিত, কাজের স্লট শেষ।")
        await state.clear()
        return

    con.execute("UPDATE tasks SET slots=slots-1 WHERE id=?", (tid,))
    cur = con.execute(
        "INSERT INTO submissions(user_id,task_id,proof) "
        "VALUES(?,?,?)",
        (uid, tid, message.text or "[ছবি/মিডিয়া জমা]")
    )
    sid = cur.lastrowid
    con.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Approve",
            callback_data=f"approve:{sid}"
        ),
        InlineKeyboardButton(
            text="❌ Reject",
            callback_data=f"reject:{sid}"
        )
    ]])

    await bot.send_message(
        ADMIN_ID,
        f"📝 নতুন কাজ জমা!\n"
        f"ইউজার: {uid}\nকাজ: {row[2]}\n"
        f"প্রমাণ: {message.text or 'ছবি/মিডিয়া'}",
        reply_markup=kb
    )

    if message.photo:
        await bot.send_photo(
            ADMIN_ID, message.photo[-1].file_id,
            caption=f"প্রমাণের ছবি | User: {uid}"
        )

    await message.answer(
        "✅ আপনার কাজ জমা হয়েছে। অ্যাডমিন যাচাই করবেন।",
        reply_markup=menu()
    )
    await state.clear()


# ===== ADMIN APPROVE / REJECT =====
@dp.callback_query(F.data.startswith(("approve:", "reject:")))
async def review(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("অনুমতি নেই!", show_alert=True)
        return

    action, sid = call.data.split(":")
    row = con.execute(
        "SELECT user_id,task_id,status FROM submissions WHERE id=?",
        (int(sid),)
    ).fetchone()

    if not row or row[2] != "pending":
        await call.answer("আগেই যাচাই করা হয়েছে!", show_alert=True)
        return

    uid, tid, status = row

    if action == "approve":
        task = con.execute(
            "SELECT reward FROM tasks WHERE id=?", (tid,)
        ).fetchone()
        reward = task[0] if task else 0

        con.execute(
            "UPDATE users SET balance=balance+?,income=income+? WHERE id=?",
            (reward, reward, uid)
        )
        con.execute(
            "UPDATE submissions SET status='approved' WHERE id=?",
            (int(sid),)
        )
        con.commit()

        await bot.send_message(
            uid, f"🎉 আপনার কাজ অনুমোদিত!\n💰 {reward} টাকা যোগ হয়েছে।"
        )
        await call.message.edit_text("✅ কাজ Approve করা হয়েছে।")

    else:
        con.execute(
            "UPDATE submissions SET status='rejected' WHERE id=?",
            (int(sid),)
        )
        con.execute(
            "UPDATE tasks SET slots=slots+1 WHERE id=?", (tid,)
        )
        con.commit()

        await bot.send_message(uid, "❌ আপনার কাজটি বাতিল হয়েছে।")
        await call.message.edit_text("❌ কাজ Reject করা হয়েছে।")

    await call.answer()


# ===== BALANCE =====
@dp.message(F.text == "💵 ব্যালেন্স")
async def balance(message: Message):
    row = con.execute(
        "SELECT balance,income FROM users WHERE id=?",
        (message.from_user.id,)
    ).fetchone()

    if row:
        await message.answer(
            f"💰 বর্তমান ব্যালেন্স: {row[0]:.2f} BDT\n"
            f"📈 মোট আয়: {row[1]:.2f} BDT"
        )


# ===== REFERRAL =====
@dp.message(F.text == "🎁 My Referrals")
async def referrals(message: Message):
    uid = message.from_user.id
    count = con.execute(
        "SELECT COUNT(*) FROM users WHERE ref_by=?", (uid,)
    ).fetchone()[0]

    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={uid}"

    await message.answer(
        f"🎁 আপনার রেফার লিংক:\n{link}\n\n"
        f"👥 মোট রেফার: {count}\n"
        "বন্ধুদের এই লিংক পাঠান।"
    )


# ===== WITHDRAW =====
@dp.message(F.text == "💸 টাকা উত্তোলন")
async def withdraw(message: Message, state: FSMContext):
    await state.set_state(Form.method)
    await message.answer(
        "কোন মাধ্যমে টাকা নিতে চান?\n"
        "বিকাশ / নগদ / USDT লিখুন।"
    )


@dp.message(Form.method)
async def method(message: Message, state: FSMContext):
    value = message.text.strip()
    if value not in ["বিকাশ", "নগদ", "USDT"]:
        await message.answer("বিকাশ, নগদ অথবা USDT লিখুন।")
        return

    await state.update_data(method=value)
    await state.set_state(Form.amount)
    await message.answer("কত টাকা উত্তোলন করতে চান? পরিমাণ লিখুন।")


@dp.message(Form.amount)
async def amount(message: Message, state: FSMContext):
    try:
        value = float(message.text)
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("সঠিক পরিমাণ লিখুন।")
        return

    uid = message.from_user.id
    row = con.execute(
        "SELECT balance FROM users WHERE id=?", (uid,)
    ).fetchone()

    if not row or value > row[0]:
        await message.answer("❌ আপনার পর্যাপ্ত ব্যালেন্স নেই।")
        await state.clear()
        return

    await state.update_data(amount=value)
    await state.set_state(Form.account)
    await message.answer("আপনার পেমেন্ট নম্বর বা USDT ঠিকানা দিন।")


@dp.message(Form.account)
async def account(message: Message, state: FSMContext):
    data = await state.get_data()
    uid = message.from_user.id
    value = data["amount"]

    row = con.execute(
        "SELECT balance FROM users WHERE id=?", (uid,)
    ).fetchone()

    if not row or value > row[0]:
        await message.answer("ব্যালেন্স যথেষ্ট নয়।")
        await state.clear()
        return

    con.execute(
        "UPDATE users SET balance=balance-? WHERE id=?",
        (value, uid)
    )
    cur = con.execute(
        "INSERT INTO withdrawals(user_id,method,amount,account) "
        "VALUES(?,?,?,?)",
        (uid, data["method"], value, message.text)
    )
    wid = cur.lastrowid
    con.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Paid",
            callback_data=f"paid:{wid}"
        ),
        InlineKeyboardButton(
            text="❌ Cancel",
            callback_data=f"cancelwd:{wid}"
        )
    ]])

    await bot.send_message(
        ADMIN_ID,
        f"💸 নতুন উত্তোলন অনুরোধ\n"
        f"User: {uid}\nপরিমাণ: {value}\n"
        f"মাধ্যম: {data['method']}\nঠিকানা: {message.text}",
        reply_markup=kb
    )

    await message.answer(
        "✅ উত্তোলনের আবেদন জমা হয়েছে।",
        reply_markup=menu()
    )
    await state.clear()


@dp.callback_query(F.data.startswith(("paid:", "cancelwd:")))
async def withdraw_review(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("অনুমতি নেই!", show_alert=True)
        return

    action, wid = call.data.split(":")
    row = con.execute(
        "SELECT user_id,amount,status FROM withdrawals WHERE id=?",
        (int(wid),)
    ).fetchone()

    if not row or row[2] != "pending":
        await call.answer("আগেই প্রক্রিয়া হয়েছে!", show_alert=True)
        return

    uid, amount, status = row

    if action == "paid":
        con.execute(
            "UPDATE withdrawals SET status='paid' WHERE id=?",
            (int(wid),)
        )
        await bot.send_message(uid, "✅ আপনার উত্তোলন সম্পন্ন হয়েছে।")
        await call.message.edit_text("✅ উত্তোলন Paid হয়েছে।")
    else:
        con.execute(
            "UPDATE users SET balance=balance+? WHERE id=?",
            (amount, uid)
        )
        con.execute(
            "UPDATE withdrawals SET status='cancelled' WHERE id=?",
            (int(wid),)
        )
        await bot.send_message(
            uid, "❌ উত্তোলন বাতিল হয়েছে। টাকা ফেরত দেওয়া হয়েছে।"
        )
        await call.message.edit_text("❌ আবেদন বাতিল, ব্যালেন্স ফেরত।")

    con.commit()
    await call.answer()


# ===== ADMIN ADD TASK =====
@dp.message(Command("addtask"))
async def addtask(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        title, link, reward, slots = message.text.split(maxsplit=1)[1].split("|")
        con.execute(
            "INSERT INTO tasks(title,link,reward,slots) VALUES(?,?,?,?)",
            (title.strip(), link.strip(), float(reward), int(slots))
        )
        con.commit()
        await message.answer("✅ নতুন কাজ যোগ হয়েছে!")
    except Exception:
        await message.answer(
            "ব্যবহার:\n/addtask কাজের নাম|লিংক|টাকা|স্লট"
        )


@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    tasks = con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    await message.answer(
        f"📊 বট রিপোর্ট\n👥 ইউজার: {users}\n📋 কাজ: {tasks}"
    )


# ===== OTHER MENU =====
@dp.message(F.text == "📞 সাপোর্ট")
async def support(message: Message):
    await message.answer("📞 সাপোর্টের জন্য অ্যাডমিনের সাথে যোগাযোগ করুন।")


@dp.message(F.text == "👋 আমি নতুন")
async def guide(message: Message):
    await message.answer(
        "স্বাগতম!\n📋 কাজ বাটনে চাপ দিয়ে কাজ শুরু করুন।\n"
        "কাজের প্রমাণ জমা দিলে অ্যাডমিন যাচাই করবেন।"
    )


@dp.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("কাজ বাতিল হয়েছে।", reply_markup=menu())


# ===== RUN BOT =====
async def main():
    print("Bot is running...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
