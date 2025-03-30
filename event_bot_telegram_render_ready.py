import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import pytz

# === تنظیمات اصلی ===
TOKEN = '7844573664:AAHKNHPDVCbc7JkMyKlsGzEYQ_V3eZ3s0lc'
CHANNEL_CHAT_ID = -1002641319532
ADMIN_USER_ID = 7140532760
TIMEZONE = 'Asia/Tehran'
SHEET_ID = '12w-aNMUExtkzUPJW2fffcwU8mmfW2asWU67XQEwdVCo'
SHEET_NAME = 'Sheet1'

bot = telebot.TeleBot(TOKEN)
scheduler = BackgroundScheduler(timezone=TIMEZONE)

# دیکشنری‌های سراسری جهت نگهداری اطلاعات ایونت
reservations = {}   # لیست رزروکنندگان برای هر ایونت (کلید: کد ایونت)
capacities = {}     # ظرفیت ایونت‌ها
minimums = {}       # حداقل رزرو مورد نیاز برای هر ایونت
message_ids = {}    # شناسه پیام ارسال شده به کانال برای هر ایونت
event_info = {}     # اطلاعات ایونت شامل زمان، محل، تاریخ، عنوان و کد ایونت

def get_event_markup(event_id, remaining):
    """بر اساس ظرفیت باقی‌مانده، دکمه مناسب را تولید می‌کند."""
    markup = InlineKeyboardMarkup()
    if remaining <= 0:
        markup.add(InlineKeyboardButton("تکمیل ظرفیت", callback_data=f"full_{event_id}"))
    else:
        markup.add(InlineKeyboardButton("رزرو می‌کنم ✅", callback_data=f"reserve_{event_id}"))
    return markup

def update_sheet_status(event_code, status, winner=None):
    """
    بر اساس کد ایونت، ستون‌های "وضعیت" و "برنده" را در شیت به‌روز می‌کند.
    فرض بر این است که شیت شما ستون‌های "کد ایونت"، "وضعیت" و "برنده" را دارد.
    """
    rows = sheet.get_all_records()
    header = sheet.row_values(1)
    code_col = header.index('کد ایونت') + 1 if 'کد ایونت' in header else None
    status_col = header.index('وضعیت') + 1 if 'وضعیت' in header else None
    winner_col = header.index('برنده') + 1 if 'برنده' in header else None

    if code_col is None or status_col is None or winner_col is None:
        return

    for i, row in enumerate(rows, start=2):
        if row.get('کد ایونت') == event_code:
            sheet.update_cell(i, status_col, status)
            if winner:
                sheet.update_cell(i, winner_col, winner)
            break

# === اتصال به Google Sheets ===
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

def send_event():
    data = sheet.get_all_records()
    now = datetime.now(pytz.timezone(TIMEZONE)).date()
    for row in data:
        # ستون‌های شیت: "کد ایونت"، "تاریخ"، "عنوان"، "ساعت"، "مکان"، "ظرفیت"، "حداقل" و "برنده"
        event_date = datetime.strptime(row['تاریخ'], '%Y-%m-%d').date()
        if (event_date - now).days == 1:
            post_event_to_channel(row)

def post_event_to_channel(row):
    # خواندن کد ایونت از شیت (ستون اول)؛ تبدیل مقدار به رشته
    event_code = str(row['کد ایونت']).strip()
    event_id = event_code  # از کد ایونت به‌عنوان شناسه استفاده می‌شود
    time_format = "%H:%M"
    event_time = datetime.strptime(row['ساعت'], time_format)
    reminder_time = (event_time - timedelta(minutes=15)).strftime(time_format)
    
    if event_id in event_info:
        # ایونت قبلاً ارسال شده؛ اطلاعات به‌روز می‌شود
        capacities[event_id] = int(row['ظرفیت'])
        minimums[event_id] = int(row.get('حداقل', 0))
        event_info[event_id].update({
            "time": row['ساعت'],
            "reminder_time": reminder_time,
            "location": row['مکان'],
            "date": row['تاریخ'],
            "title": row['عنوان']
        })
        current_reservations = reservations.get(event_id, [])
        remaining = capacities[event_id] - len(current_reservations)
        names_text = ""
        if current_reservations:
            names_text = "\n✉ رزروها:\n" + "\n".join([f"{i}. {u['name']}" for i, u in enumerate(current_reservations, start=1)])
        new_text = f"""🎲 <b>{row['عنوان']}</b>
کد ایونت: {event_code}
🕒 {row['تاریخ']} - ساعت {row['ساعت']}
📍 {row['مکان']}
👥 ظرفیت: {row['ظرفیت']} نفر
📉 ظرفیت باقی‌مانده: {remaining} نفر
{names_text}

برای رزرو یا لغو، از دکمه‌های زیر استفاده کن:"""
        markup = get_event_markup(event_id, remaining)
        if event_id in message_ids:
            try:
                bot.edit_message_text(new_text, CHANNEL_CHAT_ID, message_ids[event_id], reply_markup=markup, parse_mode='HTML')
            except Exception as e:
                print(f"خطا در بروزرسانی پیام: {e}")
        else:
            msg = bot.send_message(CHANNEL_CHAT_ID, new_text, reply_markup=markup, parse_mode='HTML')
            message_ids[event_id] = msg.message_id
    else:
        # ایونت جدید؛ ایجاد اطلاعات اولیه
        event_info[event_id] = {
            "time": row['ساعت'],
            "reminder_time": reminder_time,
            "location": row['مکان'],
            "date": row['تاریخ'],
            "title": row['عنوان'],
            "code": event_code
        }
        reservations[event_id] = []  # ثبت اولیه لیست رزروکنندگان (خالی)
        capacities[event_id] = int(row['ظرفیت'])
        minimums[event_id] = int(row.get('حداقل', 0))
        remaining = capacities[event_id]
        new_text = f"""🎲 <b>{row['عنوان']}</b>
کد ایونت: {event_code}
🕒 {row['تاریخ']} - ساعت {row['ساعت']}
📍 {row['مکان']}
👥 ظرفیت: {row['ظرفیت']} نفر
📉 ظرفیت باقی‌مانده: {remaining} نفر

برای رزرو یا لغو، از دکمه‌های زیر استفاده کن:"""
        markup = get_event_markup(event_id, remaining)
        msg = bot.send_message(CHANNEL_CHAT_ID, new_text, reply_markup=markup, parse_mode='HTML')
        message_ids[event_id] = msg.message_id

@bot.callback_query_handler(func=lambda call: call.data.startswith('reserve_') or call.data.startswith('cancel_') or call.data.startswith('full_'))
def handle_reservation(call):
    if call.data.startswith('full_'):
        bot.answer_callback_query(call.id, "ظرفیت این ایونت تکمیل شده است.")
        return

    action, event_id = call.data.split('_', 1)
    user = call.from_user
    entry = f"{user.first_name} (@{user.username or 'بدون_یوزرنیم'})"
    event_title = event_info.get(event_id, {}).get("title", "")
    
    if action == 'reserve':
        if user.id in [u['id'] for u in reservations.get(event_id, [])]:
            bot.answer_callback_query(call.id, "قبلاً رزرو کردی ✅")
        elif len(reservations.get(event_id, [])) >= capacities.get(event_id, 0):
            bot.answer_callback_query(call.id, "ظرفیت این ایونت تکمیل شده ❌")
        else:
            reservations.setdefault(event_id, []).append({'id': user.id, 'name': entry})
            reminder_time = event_info.get(event_id, {}).get("reminder_time", "")
            confirmation_text = f"✅ رزرو شما برای ایونت '{event_title}' با موفقیت ثبت شد.\nلطفاً 15 دقیقه قبل از شروع ایونت (ساعت {reminder_time}) در محل حضور داشته باشید."
            private_markup = InlineKeyboardMarkup()
            private_markup.add(InlineKeyboardButton("لغو رزرو ❌", callback_data=f"cancel_{event_id}"))
            bot.answer_callback_query(call.id, "رزرو با موفقیت انجام شد ✨")
            bot.send_message(user.id, confirmation_text, reply_markup=private_markup)
    elif action == 'cancel':
        user_list = reservations.get(event_id, [])
        if any(u['id'] == user.id for u in user_list):
            reservations[event_id] = [u for u in user_list if u['id'] != user.id]
            bot.answer_callback_query(call.id, "رزرو شما لغو شد ❌")
            bot.send_message(user.id, f"❌ رزرو شما برای ایونت '{event_title}' لغو شد.")
        else:
            bot.answer_callback_query(call.id, "رزروی برای لغو وجود ندارد ❗")
    
    current_reservations = reservations.get(event_id, [])
    names_text = ""
    if current_reservations:
        names_text = "\n✉ رزروها:\n" + "\n".join([f"{i}. {u['name']}" for i, u in enumerate(current_reservations, start=1)])
    remaining = capacities.get(event_id, 0) - len(current_reservations)
    new_text = f"""🎲 <b>{event_title}</b>
📉 ظرفیت باقی‌مانده: {remaining} نفر
{names_text}

برای رزرو یا لغو، از دکمه‌های زیر استفاده کن:"""
    markup = get_event_markup(event_id, remaining)
    try:
        msg_id = message_ids.get(event_id)
        if msg_id:
            bot.edit_message_text(new_text, CHANNEL_CHAT_ID, msg_id, reply_markup=markup, parse_mode='HTML')
    except Exception as e:
        print(f"خطا در بروزرسانی پیام: {e}")

@bot.message_handler(commands=['set_winner'])
def set_winner(message):
    """
    دستور /set_winner جهت ثبت برنده یک ایونت توسط ادمین.
    فرمت مورد انتظار:
    /set_winner event_code نام_برنده
    با این دستور، در ردیف مربوط به آن ایونت، ستون‌های "برنده" به‌روز می‌شوند.
    """
    if message.from_user.id != ADMIN_USER_ID:
        return
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "فرمت دستور صحیح نیست. استفاده: /set_winner event_code نام_برنده")
        return
    event_code = parts[1]
    winner = " ".join(parts[2:])
    if event_code not in event_info:
        bot.reply_to(message, f"کد ایونت {event_code} یافت نشد.")
        return
    update_sheet_status(event_code, "برگذار شده", winner)
    bot.reply_to(message, f"برنده برای ایونت با کد {event_code} به نام {winner} ثبت شد.")

@bot.message_handler(commands=['send_today'])
def manual_send_today(message):
    if message.from_user.id != ADMIN_USER_ID:
        return
    data = sheet.get_all_records()
    now = datetime.now(pytz.timezone(TIMEZONE)).date()
    for row in data:
        event_date = datetime.strptime(row['تاریخ'], '%Y-%m-%d').date()
        if event_date == now:
            post_event_to_channel(row)
    bot.reply_to(message, "✅ ایونت‌های امروز مجدد ارسال شدند.")

@bot.message_handler(commands=['send_day'])
def manual_send_specific_day(message):
    if message.from_user.id != ADMIN_USER_ID:
        return
    try:
        parts = message.text.strip().split()
        if len(parts) != 2:
            raise ValueError
        target_date = datetime.strptime(parts[1], "%Y-%m-%d").date()
        data = sheet.get_all_records()
        found = False
        for row in data:
            event_date = datetime.strptime(row['تاریخ'], '%Y-%m-%d').date()
            if event_date == target_date:
                post_event_to_channel(row)
                found = True
        if found:
            bot.reply_to(message, f"✅ ایونت‌های تاریخ {parts[1]} ارسال شدند.")
        else:
            bot.reply_to(message, f"❗ ایونتی برای تاریخ {parts[1]} یافت نشد.")
    except:
        bot.reply_to(message, "❗ فرمت تاریخ صحیح نیست. لطفاً به صورت YYYY-MM-DD وارد کن.")

@bot.message_handler(commands=['help'])
def show_help(message):
    if message.from_user.id != ADMIN_USER_ID:
        return
    text = """📌 دستورات مدیریتی:
/send_today - ارسال مجدد ایونت‌های امروز
/send_day YYYY-MM-DD - ارسال دستی ایونت‌های یک تاریخ خاص
/set_winner event_code نام_برنده - ثبت برنده یک ایونت (ثبت نام برنده در شیت)
/help - نمایش این راهنما"""
    bot.reply_to(message, text)

scheduler.start()
bot.polling(none_stop=True)


def run_bot():
    scheduler.start()
    bot.polling(none_stop=True)
