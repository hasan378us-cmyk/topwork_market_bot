import os
import sqlite3
from datetime import datetime, timezone

from telegram import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# IMPORTANT:
# Set BOT_TOKEN and ADMIN_ID as environment variables.
# Never publish your bot token in code or screenshots.
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "task_income_bot.sqlite3")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL NOT NULL DEFAULT 0,
            total_income REAL NOT NULL DEFAULT 0,
            pending_withdraw REAL NOT NULL DEFAULT 0,
            completed_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            reward REAL NOT NULL CHECK(reward >= 0),
            slots_total INTEGER NOT NULL CHECK(slots_total >= 1),
            slots_open INTEGER NOT NULL CHECK(slots_open >= 0),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS submissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            user_id INTEGER NOT NULL REFERENCES users(user_id),
            status TEXT NOT NULL DEFAULT 'review',
            created_at TEXT NOT NULL,
            UNIQUE(task_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS withdrawals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(user_id),
            method TEXT NOT NULL,
            amount REAL NOT NULL,
            destination TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        """)


def ensure_user(update: Update):
    u = update.effective_user
    if not u:
        return
    with db() as c:
        c.execute(
            """
            INSERT INTO users(user_id, username, first_name)
            VALUES(?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
            """,
            (u.id, u.username or "", u.first_name or ""),
        )


def user_row(user_id):
    with db() as c:
        return c.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()


def home_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📝 কাজ"), KeyboardButton("💵 ব্যালেন্স")],
            [KeyboardButton("💰 টাকা উত্তোলন"), KeyboardButton("🎁 My Referrals")],
            [KeyboardButton("🥸 সাপোর্ট"), KeyboardButton("🥸 আমি নতুন")],
        ],
        resize_keyboard=True,
    )


def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 ফিরে যান", callback_data="menu:home_inline")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    u = update.effective_user
    await update.message.reply_text(
        f"🚀 স্বাগতম, {u.first_name or 'বন্ধু'}!\n\nনিচের মেনু থেকে বেছে নিন।",
        reply_markup=home_keyboard(),
    )


async def show_categories(update, context):
    with db() as c:
        rows = c.execute(
            """
            SELECT category, COUNT(*) AS n
            FROM tasks
            WHERE active=1 AND slots_open>0
            GROUP BY category
            ORDER BY category
            """
        ).fetchall()

    if not rows:
        await update.message.reply_text(
            "❌ এখন কোনো কাজ উপলব্ধ নেই। অ্যাডমিন নতুন কাজ যোগ করলে আবার দেখুন।",
            reply_markup=home_keyboard(),
        )
        return

    buttons = [
        [InlineKeyboardButton(
            f"{r['category']} ({r['n']}টি কাজ)",
            callback_data=f"cat:{r['category']}"
        )]
        for r in rows
    ]
    buttons.append([
        InlineKeyboardButton("🔙 ফিরে যান", callback_data="menu:home_inline")
    ])
    await update.message.reply_text(
        "📝 কাজের বিভাগ বেছে নিন:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def show_category(query, category):
    """Show only one task card at a time within the selected category."""
    with db() as c:
        rows = c.execute(
            """
            SELECT id, title, reward, slots_open
            FROM tasks
            WHERE category=? AND active=1 AND slots_open>0
            ORDER BY id DESC
            """,
            (category,),
        ).fetchall()

    if not rows:
        await query.edit_message_text(
            "❌ এই বিভাগে এখন কোনো কাজ নেই।",
            reply_markup=back_keyboard(),
        )
        return

    r = rows[0]
    buttons = [[
        InlineKeyboardButton(
            "📋 কাজের বিস্তারিত দেখুন",
            callback_data=f"task:{r['id']}"
        )
    ]]

    if len(rows) > 1:
        buttons.append([InlineKeyboardButton(
            "➡️ পরের কাজ",
            callback_data=f"nexttask:{category}:{r['id']}"
        )])

    buttons.append([InlineKeyboardButton(
        "🔙 বিভাগে ফিরে যান",
        callback_data="menu:tasks_back"
    )])

    await query.edit_message_text(
        f"📂 {category} কাজ\n\n"
        f"📋 কাজ: {r['title']}\n"
        f"💰 পারিশ্রমিক: ৳{r['reward']:.2f}\n"
        f"📦 বাকি স্লট: {r['slots_open']}টি\n\n"
        f"মোট উপলব্ধ কাজ: {len(rows)}টি",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def show_next_category_task(query, category, current_id):
    with db() as c:
        rows = c.execute(
            """
            SELECT id, title, reward, slots_open
            FROM tasks
            WHERE category=? AND active=1 AND slots_open>0
            ORDER BY id DESC
            """,
            (category,),
        ).fetchall()

    if not rows:
        await query.edit_message_text(
            "❌ এই বিভাগে এখন কোনো কাজ নেই।",
            reply_markup=back_keyboard(),
        )
        return

    ids = [r["id"] for r in rows]
    try:
        index = ids.index(current_id) + 1
    except ValueError:
        index = 0

    if index >= len(rows):
        await query.edit_message_text(
            "✅ এই বিভাগের সব কাজ দেখেছেন।",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🔄 প্রথম কাজ",
                    callback_data=f"cat:{category}"
                )],
                [InlineKeyboardButton(
                    "🔙 বিভাগে ফিরে যান",
                    callback_data="menu:tasks_back"
                )],
            ]),
        )
        return

    r = rows[index]
    buttons = [[
        InlineKeyboardButton(
            "📋 কাজের বিস্তারিত দেখুন",
            callback_data=f"task:{r['id']}"
        )
    ]]

    if index + 1 < len(rows):
        buttons.append([InlineKeyboardButton(
            "➡️ পরের কাজ",
            callback_data=f"nexttask:{category}:{r['id']}"
        )])

    buttons.append([InlineKeyboardButton(
        "🔙 বিভাগে ফিরে যান",
        callback_data="menu:tasks_back"
    )])

    await query.edit_message_text(
        f"📂 {category} কাজ\n\n"
        f"📋 কাজ: {r['title']}\n"
        f"💰 পারিশ্রমিক: ৳{r['reward']:.2f}\n"
        f"📦 বাকি স্লট: {r['slots_open']}টি\n\n"
        f"কাজের ক্রম: {index + 1}/{len(rows)}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def show_task(query, task_id, user_id):
    with db() as c:
        task = c.execute(
            "SELECT * FROM tasks WHERE id=? AND active=1", (task_id,)
        ).fetchone()
        old = c.execute(
            "SELECT status FROM submissions WHERE task_id=? AND user_id=?",
            (task_id, user_id),
        ).fetchone()

    if not task or task["slots_open"] <= 0:
        await query.edit_message_text(
            "❌ এই কাজের স্লট শেষ হয়েছে।",
            reply_markup=back_keyboard(),
        )
        return

    if old:
        await query.edit_message_text(
            f"ℹ️ এই কাজের অবস্থা: {old['status']}। একই কাজ আবার জমা দিতে পারবেন না।",
            reply_markup=back_keyboard(),
        )
        return

    await query.edit_message_text(
        f"📋 {task['title']}\n\n"
        f"{task['description']}\n\n"
        f"💰 পারিশ্রমিক: ৳{task['reward']:.2f}\n"
        f"📦 বাকি স্লট: {task['slots_open']}টি",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ জমা দিন", callback_data=f"submit:{task_id}")],
            [InlineKeyboardButton("❌ কাজ বাতিল", callback_data=f"cancel:{task_id}")],
            [InlineKeyboardButton(
                "🔙 কাজের তালিকায় ফিরুন",
                callback_data=f"cat:{task['category']}"
            )],
        ]),
    )


async def submit_task(query, task_id, user_id, context):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        task = c.execute(
            "SELECT * FROM tasks WHERE id=? AND active=1", (task_id,)
        ).fetchone()
        old = c.execute(
            "SELECT id FROM submissions WHERE task_id=? AND user_id=?",
            (task_id, user_id),
        ).fetchone()

        if not task or task["slots_open"] <= 0:
            c.rollback()
            await query.edit_message_text(
                "❌ দুঃখিত, এই কাজের স্লট শেষ।",
                reply_markup=back_keyboard(),
            )
            return

        if old:
            c.rollback()
            await query.edit_message_text(
                "ℹ️ এই কাজটি আপনি আগেই জমা দিয়েছেন।",
                reply_markup=back_keyboard(),
            )
            return

        c.execute(
            "UPDATE tasks SET slots_open=slots_open-1 WHERE id=?",
            (task_id,),
        )
        cur = c.execute(
            """
            INSERT INTO submissions(task_id,user_id,status,created_at)
            VALUES(?,?,?,?)
            """,
            (task_id, user_id, "review", now()),
        )
        sub_id = cur.lastrowid
        c.commit()

    u = query.from_user
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"📥 নতুন কাজ জমা হয়েছে\n\n"
            f"🆔 Submission: {sub_id}\n"
            f"👤 নাম: {u.full_name}\n"
            f"🆔 User ID: {user_id}\n"
            f"📋 কাজ: {task['title']}\n"
            f"💰 মূল্য: ৳{task['reward']:.2f}\n"
            f"⏳ অবস্থা: রিভিউ",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ অনুমোদন", callback_data=f"approve:{sub_id}"),
                InlineKeyboardButton("❌ বাতিল", callback_data=f"reject:{sub_id}"),
            ]]),
        )
    except Exception:
        pass

    await query.edit_message_text(
        "✅ আপনার কাজ জমা হয়েছে!\n\n"
        "⏳ কাজটি যাচাই করা হবে। অনুমোদিত হলে ব্যালেন্সে টাকা যোগ হবে।",
        reply_markup=back_keyboard(),
    )


async def cancel_task(query, task_id, user_id):
    await query.edit_message_text(
        "❌ কাজটি বাতিল করেছেন। আপনার ব্যালেন্সে কোনো টাকা যোগ হয়নি।",
        reply_markup=back_keyboard(),
    )


async def balance(update, user_id):
    r = user_row(user_id)
    with db() as c:
        review = c.execute(
            "SELECT COUNT(*) n FROM submissions WHERE user_id=? AND status='review'",
            (user_id,),
        ).fetchone()["n"]

    await update.message.reply_text(
        "💵 আপনার ব্যালেন্স\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 ব্যালেন্স: {r['balance']:.2f} BDT\n"
        f"💸 পেন্ডিং উত্তোলন: {r['pending_withdraw']:.2f} BDT\n"
        f"💰 মোট আয়: {r['total_income']:.2f} BDT\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ সম্পন্ন কাজ: {r['completed_count']}টি\n"
        f"⏳ রিভিউতে আছে: {review}টি",
        reply_markup=home_keyboard(),
    )


async def withdraw_menu(update):
    await update.message.reply_text(
        "📤 টাকা তোলার মাধ্যম নির্বাচন করুন:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 মোবাইল রিচার্জ", callback_data="wd:মোবাইল রিচার্জ")],
            [InlineKeyboardButton("💳 বিকাশ", callback_data="wd:বিকাশ")],
            [InlineKeyboardButton("💳 নগদ", callback_data="wd:নগদ")],
            [InlineKeyboardButton("🔙 ফিরে যান", callback_data="menu:home_inline")],
        ]),
    )


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text
    user_id = update.effective_user.id
    ensure_user(update)

    if text == "📝 কাজ":
        await show_categories(update, context)
    elif text == "💵 ব্যালেন্স":
        await balance(update, user_id)
    elif text == "💰 টাকা উত্তোলন":
        await withdraw_menu(update)
    elif text == "🎁 My Referrals":
        await update.message.reply_text(
            "🎁 রেফারেল ব্যবস্থা পরবর্তী ধাপে যোগ করা যাবে।",
            reply_markup=home_keyboard(),
        )
    elif text == "🥸 সাপোর্ট":
        await update.message.reply_text(
            "🥸 সাপোর্ট: বট অ্যাডমিনের সঙ্গে যোগাযোগ করুন।",
            reply_markup=home_keyboard(),
        )
    elif text == "🥸 আমি নতুন":
        await update.message.reply_text(
            "নতুন ব্যবহারকারী: কাজের নির্দেশনা পড়ুন এবং বৈধ কাজ জমা দিন।",
            reply_markup=home_keyboard(),
        )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ensure_user(update)
    user_id = q.from_user.id
    data = q.data or ""

    if data == "menu:home" or data == "menu:home_inline":
        await q.edit_message_text(
            f"🚀 স্বাগতম, {q.from_user.first_name or 'বন্ধু'}!\n\n"
            "নিচের মেনু থেকে বেছে নিন।",
            reply_markup=back_keyboard(),
        )
    elif data == "menu:tasks_back":
        with db() as c:
            rows = c.execute(
                """
                SELECT category, COUNT(*) AS n FROM tasks
                WHERE active=1 AND slots_open>0
                GROUP BY category ORDER BY category
                """
            ).fetchall()
        if not rows:
            await q.edit_message_text(
                "❌ এখন কোনো কাজ উপলব্ধ নেই।",
                reply_markup=back_keyboard(),
            )
        else:
            buttons = [[InlineKeyboardButton(
                f"{r['category']} ({r['n']}টি কাজ)",
                callback_data=f"cat:{r['category']}"
            )] for r in rows]
            buttons.append([InlineKeyboardButton(
                "🔙 ফিরে যান", callback_data="menu:home_inline"
            )])
            await q.edit_message_text(
                "📝 কাজের বিভাগ বেছে নিন:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
    elif data.startswith("nexttask:"):
        parts = data.split(":", 2)
        if len(parts) == 3:
            await show_next_category_task(q, parts[1], int(parts[2]))
    elif data.startswith("cat:"):
        await show_category(q, data.split(":", 1)[1])
    elif data.startswith("task:"):
        await show_task(q, int(data.split(":", 1)[1]), user_id)
    elif data.startswith("submit:"):
        await submit_task(q, int(data.split(":", 1)[1]), user_id, context)
    elif data.startswith("cancel:"):
        await cancel_task(q, int(data.split(":", 1)[1]), user_id)
    elif data.startswith("approve:") or data.startswith("reject:"):
        if user_id != ADMIN_ID:
            await q.answer("শুধু অ্যাডমিন এটি করতে পারবেন।", show_alert=True)
            return

        sub_id = int(data.split(":", 1)[1])
        approve = data.startswith("approve:")

        with db() as c:
            sub = c.execute(
                """
                SELECT s.*, t.title, t.reward
                FROM submissions s JOIN tasks t ON t.id=s.task_id
                WHERE s.id=?
                """,
                (sub_id,),
            ).fetchone()

            if not sub or sub["status"] != "review":
                await q.edit_message_text("এই জমাটি ইতিমধ্যে প্রক্রিয়া করা হয়েছে।")
                return

            if approve:
                c.execute(
                    "UPDATE submissions SET status='approved' WHERE id=?",
                    (sub_id,),
                )
                c.execute(
                    """
                    UPDATE users
                    SET balance=balance+?,
                        total_income=total_income+?,
                        completed_count=completed_count+1
                    WHERE user_id=?
                    """,
                    (sub["reward"], sub["reward"], sub["user_id"]),
                )
            else:
                c.execute(
                    "UPDATE submissions SET status='rejected' WHERE id=?",
                    (sub_id,),
                )
                c.execute(
                    "UPDATE tasks SET slots_open=slots_open+1 WHERE id=?",
                    (sub["task_id"],),
                )
            c.commit()

        await q.edit_message_text(
            f"{'✅ অনুমোদিত' if approve else '❌ বাতিল'}\n"
            f"কাজ: {sub['title']}\nUser ID: {sub['user_id']}"
        )
        try:
            await context.bot.send_message(
                sub["user_id"],
                (
                    f"✅ আপনার কাজ অনুমোদিত হয়েছে।\n"
                    f"💰 ব্যালেন্সে ৳{sub['reward']:.2f} যোগ হয়েছে।"
                    if approve
                    else "❌ আপনার কাজটি অনুমোদিত হয়নি। কাজের স্লট আবার খালি করা হয়েছে।"
                ),
            )
        except Exception:
            pass
    elif data.startswith("wd:"):
        method = data.split(":", 1)[1]
        await q.edit_message_text(
            f"📤 নির্বাচিত মাধ্যম: {method}\n\n"
            "এই সংস্করণে টাকা উত্তোলনের অনুরোধ জমা দেওয়ার ধাপ এখনো যোগ করা হয়নি।",
            reply_markup=back_keyboard(),
        )


async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ এই কমান্ড শুধু অ্যাডমিন ব্যবহার করতে পারবেন।")
        return

    raw = update.message.text.partition(" ")[2]
    parts = [p.strip() for p in raw.split("|", 4)]
    if len(parts) != 5:
        await update.message.reply_text(
            "ব্যবহার:\n"
            "/addtask ক্যাটাগরি | শিরোনাম | টাকা | সংখ্যা | বিবরণ\n\n"
            "উদাহরণ:\n"
            "/addtask Data Entry | Form checking | 20 | 100 | ফর্মের তথ্য যাচাই করুন।\n\n"
            "শুধু বৈধ কাজ যোগ করুন। অন্যের অ্যাকাউন্টের পাসওয়ার্ড বা লগইন তথ্য সংগ্রহ করবেন না।"
        )
        return

    category, title, reward_s, slots_s, description = parts
    try:
        reward = float(reward_s)
        slots = int(slots_s)
        if reward < 0 or slots < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ টাকা ও কাজের সংখ্যা সঠিকভাবে লিখুন।")
        return

    with db() as c:
        c.execute(
            """
            INSERT INTO tasks(
                category,title,description,reward,slots_total,
                slots_open,active,created_at
            ) VALUES(?,?,?,?,?,?,1,?)
            """,
            (category, title, description, reward, slots, slots, now()),
        )

    await update.message.reply_text(
        f"✅ কাজ যোগ হয়েছে!\n📋 {title}\n"
        f"💰 ৳{reward:.2f}\n📦 মোট স্লট: {slots}"
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"আপনার Telegram User ID: {update.effective_user.id}"
    )


def main():
    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN সেট করা নেই। নতুন BotFather token-টি environment variable হিসেবে সেট করুন."
        )
    if ADMIN_ID <= 0:
        raise SystemExit(
            "ADMIN_ID সেট করা নেই। আপনার Telegram numeric user ID environment variable হিসেবে সেট করুন."
        )

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.run_polling()


if __name__ == "__main__":
    main()
