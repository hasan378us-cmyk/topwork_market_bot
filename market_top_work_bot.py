import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

ADMIN_ID = 8510313155  # আপনার টেলিগ্রাম অ্যাডমিন আইডি

# কনভারসেশন স্টেপস
WAITING_FOR_UID = 1
WAITING_FOR_COOKIES = 2
WAITING_FOR_BKASH_NAGAD_NUMBER = 10
WAITING_FOR_WITHDRAW_AMOUNT = 12

# --- ডাটাবেস সেটআপ ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.00,
            pending_withdraw REAL DEFAULT 0.00,
            total_income REAL DEFAULT 0.00,
            completed_tasks INTEGER DEFAULT 0,
            review_tasks INTEGER DEFAULT 0,
            refer_count INTEGER DEFAULT 0,
            refer_income REAL DEFAULT 0.00,
            referred_by INTEGER DEFAULT NULL
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("""
            INSERT INTO users (user_id, balance, pending_withdraw, total_income, completed_tasks, review_tasks, refer_count, refer_income)
            VALUES (?, 0.0, 0.0, 0.0, 0, 0, 0, 0.0)
        """, (user_id,))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
    conn.close()
    return {
        "user_id": row[0],
        "balance": row[1],
        "pending_withdraw": row[2],
        "total_income": row[3],
        "completed_tasks": row[4],
        "review_tasks": row[5],
        "refer_count": row[6],
        "refer_income": row[7],
        "referred_by": row[8]
    }

def update_user_field(user_id, field, value):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def add_user_balance(user_id, amount):
    user = get_user(user_id)
    new_bal = user["balance"] + amount
    new_tot = user["total_income"] + amount
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = ?, total_income = ? WHERE user_id = ?", (new_bal, new_tot, user_id))
    conn.commit()
    conn.close()

# --- মূল মেনু ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    keyboard = [
        ["📋 কাজ ▶"],
        ["💰 ব্যালেন্স"],
        ["💵 টাকা উত্তোলন"],
        ["🎁 My Referrals"],
        ["👨‍💻 সাপোর্ট"],
        ["👶 আমি নতুন"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    welcome_message = f"🤖 স্বাগতম, MD: {user_name}!\n☑️ কাজ শুরু করতে নিচের অপশনগুলো ব্যবহার করুন 🔻"
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

# --- স্টার্ট ও রেফারেল হ্যান্ডলার ---
async def start_with_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_data = get_user(user_id)
    
    args = context.args
    if args and args[0].startswith("ref_") and user_data["referred_by"] is None:
        try:
            referrer_id = int(args[0].split("_")[1])
            if referrer_id != user_id:
                update_user_field(user_id, "referred_by", referrer_id)
                ref_user = get_user(referrer_id)
                new_count = ref_user["refer_count"] + 1
                update_user_field(referrer_id, "refer_count", new_count)
                
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text="🎉 অভিনন্দন! আপনার রেফারল লিংকের মাধ্যমে একজন নতুন ইউজার জয়েন করেছে!"
                    )
                except:
                    pass
        except Exception as e:
            print(f"Referral error: {e}")

    await show_main_menu(update, context)

# --- ব্যালেন্স ড্যাশবোর্ড ---
async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_user(user_id)
    
    balance_msg = (
        "💵 **আপনার ব্যালেন্স**\n"
        "──────────────────\n"
        f"💰 ব্যালেন্স: {stats['balance']:.2f} BDT\n"
        f"💰 পেন্ডিং (উইথড্র): {stats['pending_withdraw']:.2f} BDT\n"
        f"💰 Total Income: {stats['total_income']:.2f} BDT\n\n"
        f"✅ সম্পন্ন কাজ: {stats['completed_tasks']} টি\n"
        f"⏳ রিভিউতে আছে: {stats['review_tasks']} টি"
    )
    await update.message.reply_text(balance_msg, parse_mode="Markdown")

# --- My Referrals মেনু ---
async def handle_referral_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = context.bot.username
    ref_data = get_user(user_id)
    
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    ref_msg = (
        "🎁 **My Referrals**\n"
        f"👤 **Total Refer:** {ref_data['refer_count']}\n"
        f"😃 **Total Refer Income:** {ref_data['refer_income']:.2f} BDT\n"
        "🔗 **আপনার রেফার লিংক:**👇\n\n"
        f"`{referral_link}`\n\n"
        "ℹ️ আপনি আপনার প্রতিটি রেফারেলের সম্পূর্ণ করা কাজ থেকে আয়ের ১৫% কমিশন পাবেন।"
    )
    await update.message.reply_text(ref_msg, parse_mode="Markdown")

# --- কাজের ক্যাটাগরি মেনু ---
async def handle_tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_keyboard = [
        ["📷 ইনস্টাগ্রাম কাজ >"],
        ["📧 Gmail কাজ"],
        ["🪙 Coin Work"],
        ["f Facebook কাজ"],
        ["❌ বাতিল"]
    ]
    reply_markup = ReplyKeyboardMarkup(task_keyboard, resize_keyboard=True)
    await update.message.reply_text("🟣 সিলেক্ট করুন:", reply_markup=reply_markup)

async def handle_facebook_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    facebook_keyboard = [
        ["✉️ Anymail/Number"],
        ["❌ বাতিল"]
    ]
    reply_markup = ReplyKeyboardMarkup(facebook_keyboard, resize_keyboard=True)
    await update.message.reply_text("🟣 সিলেক্ট করুন:", reply_markup=reply_markup)

async def handle_anymail_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    anymail_keyboard = [
        ["f 0 fnd cookies | 4.00 ৳"],
        ["🔙 ফিরে যান"]
    ]
    reply_markup = ReplyKeyboardMarkup(anymail_keyboard, resize_keyboard=True)
    await update.message.reply_text("🟣 সিলেক্ট করুন:", reply_markup=reply_markup)

async def handle_specific_facebook_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🟢 First name: `Laura`\n"
        "🟢 Last name: `Silva`\n"
        "🔒 Password: `kamrol@04`\n\n"
        "f উপরের তথ্য দিয়ে অ্যাকাউন্ট খুলে নিচে **Send UID** বাটনে চাপ দিন 🤣"
    )
    fb_action_keyboard = [
        ["Send UID"],
        ["👶 কিভাবে কাজ করব"],
        ["❌ বাতিল"]
    ]
    reply_markup = ReplyKeyboardMarkup(fb_action_keyboard, resize_keyboard=True)
    
    sent_msg = await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
    context.user_data['last_task_msg_id'] = sent_msg.message_id

# --- মাল্টি-স্টেপ ফেসবুক টাস্ক কনভারসেশন (UID -> Cookies) ---
async def ask_for_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancel_keyboard = [["❌ বাতিল"]]
    reply_markup = ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True)
    await update.message.reply_text("☑️ আপনার ফেসবুক অ্যাকাউন্টের ১৪ থেকে ১৬ সংখ্যার UID-টি দিন:", reply_markup=reply_markup)
    return WAITING_FOR_UID

async def receive_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_uid'] = update.message.text
    cancel_keyboard = [["❌ বাতিল"]]
    reply_markup = ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True)
    await update.message.reply_text("এবার আপনার Cookies টি দিন:", reply_markup=reply_markup)
    return WAITING_FOR_COOKIES

async def receive_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_cookies = update.message.text
    user_uid = context.user_data.get('temp_uid', '')
    user = update.effective_user
    
    user_data = get_user(user.id)
    update_user_field(user.id, "review_tasks", user_data["review_tasks"] + 1)

    # ইউজার কাজ জমা দেওয়ার সাথে সাথে চ্যাট থেকে কাজের ডিটেইলস মেসেজটি রিমুভ করা
    last_msg_id = context.user_data.get('last_task_msg_id')
    if last_msg_id:
        try:
            await context.bot.delete_message(chat_id=user.id, message_id=last_msg_id)
        except:
            pass

    # আপনার চাহিদা অনুযায়ী সঠিক সফল মেসেজটি এখানে সেট করা হলো
    user_success_msg = (
        "এই কাজের রিপোর্ট খুব তাড়াতাড়ি আসবে, তাই সবাই আর দেরি না করে আরও বেশি করে কাজ করুন।"
    )
    await update.message.reply_text(user_success_msg)
    await show_main_menu(update, context)

    admin_msg = (
        "New Facebook Task Submitted!\n\n"
        f"👤 User ID: {user.id}\n"
        f"📝 Name: {user.first_name}\n"
        f"🆔 UID: {user_uid}\n"
        f"🍪 Cookies: {user_cookies}\n"
        f"💵 Rate: ৳4.00\n\n"
        "Status: ⏳ Under Review"
    )
    admin_keyboard = [[InlineKeyboardButton("Reject ❌", callback_data="fb_reject"), InlineKeyboardButton("Approve ✅", callback_data="fb_approve")]]
    
    try:
        sent_msg = await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=InlineKeyboardMarkup(admin_keyboard))
        if 'pending_tasks' not in context.bot_data:
            context.bot_data['pending_tasks'] = {}
        context.bot_data['pending_tasks'][sent_msg.message_id] = {"user_id": user.id, "reward": 4.00}
    except Exception as e:
        print(f"Admin send error: {e}")

    return ConversationHandler.END

# --- টাকা উত্তোলন মেনু ---
async def handle_withdraw_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    withdraw_keyboard = [
        ["💠 USDT (BEP-20) -> সর্বনিম্ন: 0.25(-0.05)"],
        ["📱 মোবাইল রিচার্জ -> সর্বনিম্ন: ২৫৳(-৫)"],
        ["📲 বিকাশ -> সর্বনিম্ন: ১১০৳(-১০)"],
        ["🔴 নগদ -> সর্বনিম্ন: ১০০৳(-১০)"],
        ["🔙 ফিরে যান"]
    ]
    reply_markup = ReplyKeyboardMarkup(withdraw_keyboard, resize_keyboard=True)
    await update.message.reply_text("💰 টাকা তোলার মাধ্যম সিলেক্ট করুন:", reply_markup=reply_markup)

async def ask_for_withdraw_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    method_text = update.message.text
    if "বিকাশ" in method_text:
        context.user_data['withdraw_method'] = "Bkash"
    elif "নগদ" in method_text:
        context.user_data['withdraw_method'] = "Nagad"
    elif "মোবাইল রিচার্জ" in method_text:
        context.user_data['withdraw_method'] = "Mobile Recharge"
    elif "USDT" in method_text:
        context.user_data['withdraw_method'] = "USDT (BEP-20)"

    user_id = update.effective_user.id
    current_bal = get_user(user_id)["balance"]
    
    if current_bal < 0.25:
        await update.message.reply_text(f"❌ আপনার পর্যাপ্ত ব্যালেন্স নেই! বর্তমান ব্যালেন্স: ৳{current_bal:.2f}")
        return ConversationHandler.END

    cancel_keyboard = [["❌ বাতিল"]]
    reply_markup = ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True)
    
    prompt = "💠 আপনার Binance Pay ID অথবা USDT (BEP-20) ডিপোজিট লিংকটি দিন:" if "USDT" in method_text else "📱 আপনার নম্বরটি দিন:"
    await update.message.reply_text(prompt, reply_markup=reply_markup)
    return WAITING_FOR_BKASH_NAGAD_NUMBER

async def receive_withdraw_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['withdraw_account'] = update.message.text
    cancel_keyboard = [["❌ বাতিল"]]
    reply_markup = ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True)
    await update.message.reply_text("💵 আপনি কত টাকা তুলতে চান? পরিমাণটি সংখ্যায় লিখুন:", reply_markup=reply_markup)
    return WAITING_FOR_WITHDRAW_AMOUNT

async def finalize_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ সঠিক সংখ্যায় অ্যামাউন্ট লিখুন:")
        return WAITING_FOR_WITHDRAW_AMOUNT

    user = update.effective_user
    user_id = user.id
    method = context.user_data.get('withdraw_method', 'Bkash')
    account = context.user_data.get('withdraw_account', '')

    user_data = get_user(user_id)
    if amount > user_data["balance"]:
        await update.message.reply_text(f"❌ পর্যাপ্ত ব্যালেন্স নেই! বর্তমান ব্যালেন্স: ৳{user_data['balance']:.2f}")
        return ConversationHandler.END

    new_bal = user_data["balance"] - amount
    new_pend = user_data["pending_withdraw"] + amount
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = ?, pending_withdraw = ? WHERE user_id = ?", (new_bal, new_pend, user_id))
    conn.commit()
    conn.close()

    user_success_msg = f"✅ আপনার টাকা তোলার মাধ্যম সঠিক ভাবে জমা হয়েছে আপনার {account} 2 থেকে 3 ঘন্টার ভিতরে টাকা জমা হবে ধন্যবাদ"
    await update.message.reply_text(user_success_msg)
    await show_main_menu(update, context)

    remaining_balance = get_user(user_id)["balance"]
    admin_withdraw_msg = (
        "🔔 **New Withdrawal Request**\n\n"
        f"👤 **User ID:** `{user_id}`\n"
        f"📱 **Withdrawal Number/Address:** `{account}`\n"
        f"💵 **Amount:** ৳{amount:.2f}\n"
        f"💰 **Remaining Balance:** ৳{remaining_balance:.2f}\n"
        f"📌 **Method:** {method}\n\n"
        "Status: ⏳ Pending"
    )

    admin_keyboard = [[
        InlineKeyboardButton("❌ NO", callback_data=f"withdraw_no_{user_id}_{amount}"),
        InlineKeyboardButton("✅ OK", callback_data=f"withdraw_ok_{user_id}_{amount}_{method}")
    ]]

    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_withdraw_msg, reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode="Markdown")
    except Exception as e:
        print(f"Admin withdraw send error: {e}")

    return ConversationHandler.END

# --- অ্যাডমিন ডিসিশন হ্যান্ডলার ---
async def admin_decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    original_text = query.message.text
    
    if data.startswith("withdraw_"):
        parts = data.split("_")
        action = parts[1]
        user_id = int(parts[2])
        amount = float(parts[3])
        base_text = original_text.split("\n\nStatus:")[0]
        
        user_data = get_user(user_id)

        if action == "ok":
            method = parts[4] if len(parts) > 4 else "মাধ্যম"
            await query.edit_message_text(text=f"{base_text}\n\nStatus: SUCCESS ✅")
            
            new_pend = max(0.0, user_data["pending_withdraw"] - amount)
            update_user_field(user_id, "pending_withdraw", new_pend)
            
            try:
                await context.bot.send_message(chat_id=user_id, text=f"সঠিক ভাবে আপনার ({method}) এ টাকা জমা হয়েছে")
            except:
                pass

        elif action == "no":
            await query.edit_message_text(text=f"{base_text}\n\nStatus: FAILED ❌")
            
            new_bal = user_data["balance"] + amount
            new_pend = max(0.0, user_data["pending_withdraw"] - amount)
            conn = sqlite3.connect("bot_database.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET balance = ?, pending_withdraw = ? WHERE user_id = ?", (new_bal, new_pend, user_id))
            conn.commit()
            conn.close()
            
            try:
                await context.bot.send_message(chat_id=user_id, text="দুঃখিত কোনো একটি সমস্যার কারনে টাকা পাঠানো জাই নাই NO আবার চেষ্টা করুন ধন্যবাদ")
            except:
                pass

    elif data in ["fb_approve", "fb_reject"]:
        message_id = query.message.message_id
        pending_tasks = context.bot_data.get('pending_tasks', {})
        task_info = pending_tasks.get(message_id)
        if task_info:
            target_user_id = task_info["user_id"]
            reward = task_info["reward"]
            base_text = original_text.split("\n\nStatus:")[0]
            user_data = get_user(target_user_id)

            if data == "fb_approve":
                await query.edit_message_text(text=f"{base_text}\n\nStatus: APPROVED ✅")
                add_user_balance(target_user_id, reward)
                update_user_field(target_user_id, "completed_tasks", user_data["completed_tasks"] + 1)
                update_user_field(target_user_id, "review_tasks", max(0, user_data["review_tasks"] - 1))
                
                if user_data["referred_by"]:
                    ref_id = user_data["referred_by"]
                    commission = reward * 0.15
                    add_user_balance(ref_id, commission)
                    ref_user_data = get_user(ref_id)
                    update_user_field(ref_id, "refer_income", ref_user_data["refer_income"] + commission)
                    try:
                        await context.bot.send_message(chat_id=ref_id, text=f"🎁 আপনার রেফারেল থেকে নতুন কমিশন যুক্ত হয়েছে: +৳{commission:.2f}")
                    except:
                        pass

                try:
                    await context.bot.send_message(chat_id=target_user_id, text=f"💎 ফেসবুক কাজ এপ্রুভ হয়েছে: **+{reward:.2f} BDT** আপনার ব্যালেন্সে যোগ হয়েছে! 😄", parse_mode="Markdown")
                except:
                    pass

            elif data == "fb_reject":
                await query.edit_message_text(text=f"{base_text}\n\nStatus: REJECTED ❌")
                update_user_field(target_user_id, "review_tasks", max(0, user_data["review_tasks"] - 1))
                try:
                    await context.bot.send_message(chat_id=target_user_id, text="🔴 ভুল কুকিজ বা তথ্য সঠিক না থাকায় এই কাজ গ্রহণযোগ্য হয়নি।")
                except:
                    pass
            
            if message_id in pending_tasks:
                del pending_tasks[message_id]

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ অপারেশন বাতিল করা হয়েছে।")
    await show_main_menu(update, context)
    return ConversationHandler.END

def main():
    init_db()
    app = ApplicationBuilder().token("9126121221:AAEn9n9KO1ZY05RfynRvadEJkyBROCaZiIU").build()

    fb_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("Send UID"), ask_for_uid)],
        states={
            WAITING_FOR_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_uid)],
            WAITING_FOR_COOKIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_cookies)]
        },
        fallbacks=[MessageHandler(filters.Text("❌ বাতিল"), handle_cancel)]
    )

    withdraw_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text("💠 USDT (BEP-20) -> সর্বনিম্ন: 0.25(-0.05)"), ask_for_withdraw_account),
            MessageHandler(filters.Text("📱 মোবাইল রিচার্জ -> সর্বনিম্ন: ২৫৳(-৫)"), ask_for_withdraw_account),
            MessageHandler(filters.Text("📲 বিকাশ -> সর্বনিম্ন: ১১০৳(-১০)"), ask_for_withdraw_account),
            MessageHandler(filters.Text("🔴 নগদ -> সর্বনিম্ন: ১০০৳(-১০)"), ask_for_withdraw_account)
        ],
        states={
            WAITING_FOR_BKASH_NAGAD_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_withdraw_account)],
            WAITING_FOR_WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, finalize_withdrawal)]
        },
        fallbacks=[MessageHandler(filters.Text("❌ বাতিল"), handle_cancel)]
    )

    app.add_handler(CommandHandler("start", start_with_referral))
    app.add_handler(fb_conv)
    app.add_handler(withdraw_conv)
    
    app.add_handler(MessageHandler(filters.Text("📋 কাজ ▶"), handle_tasks_menu))
    app.add_handler(MessageHandler(filters.Text("💰 ব্যালেন্স"), check_balance))
    app.add_handler(MessageHandler(filters.Text("🎁 My Referrals"), handle_referral_menu))
    app.add_handler(MessageHandler(filters.Text("🔙 ফিরে যান"), handle_tasks_menu))
    app.add_handler(MessageHandler(filters.Text("f Facebook কাজ"), handle_facebook_tasks))
    app.add_handler(MessageHandler(filters.Text("✉️ Anymail/Number"), handle_anymail_tasks))
    app.add_handler(MessageHandler(filters.Text("f 0 fnd cookies | 4.00 ৳"), handle_specific_facebook_details))
    app.add_handler(MessageHandler(filters.Text("💵 টাকা উত্তোলন"), handle_withdraw_menu))
    app.add_handler(MessageHandler(filters.Text("❌ বাতিল"), handle_cancel))
    
    app.add_handler(CallbackQueryHandler(admin_decision_callback))

    print("বট সফলভাবে চালু হয়েছে এবং ডাটাবেস কানেক্ট হয়েছে...")
    app.run_polling()

if __name__ == "__main__":
    main()
