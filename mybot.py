import logging
import pandas as pd
import sqlite3
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackContext,
)

# ========== 配置区 ==========
DATABASE = 'clients.db'  # SQLite 数据库文件

# ========== 数据库操作函数 ==========
def init_db():
    """初始化数据库，若表不存在则创建"""
    conn = sqlite3.connect(DATABASE)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            username TEXT,
            phone_number TEXT UNIQUE,
            added_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

def number_exists(phone_number: str) -> bool:
    """检查号码是否已存在"""
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM clients WHERE phone_number = ?", (phone_number,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists

def add_number(username: str, phone_number: str, added_time: str):
    """将号码保存到数据库，若重复则自动跳过"""
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO clients (username, phone_number, added_time) VALUES (?, ?, ?)",
            (username, phone_number, added_time)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def export_clients():
    """导出所有客户数据到 Excel（clients.xlsx）"""
    conn = sqlite3.connect(DATABASE)
    df = pd.read_sql_query("SELECT * FROM clients", conn)
    df.to_excel("clients.xlsx", index=False)
    conn.close()

def import_data(file_path: str) -> str:
    """从 Excel 导入客户数据，返回导入结果信息"""
    try:
        df = pd.read_excel(file_path)
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        for _, row in df.iterrows():
            cur.execute(
                "INSERT OR IGNORE INTO clients (username, phone_number, added_time) VALUES (?, ?, ?)",
                (row['username'], row['phone_number'], row['added_time'])
            )
        conn.commit()
        conn.close()
        return "✅ 数据导入成功！\nData import successful!"
    except Exception as e:
        return f"🚨 导入失败: {str(e)}\nImport failed: {str(e)}"

# ========== Bot 命令处理 ==========
# /start 欢迎消息，说明必须以 + 开头
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "欢迎！请发送客户的手机号码，我将检查是否重复。\n"
        "请以“+国家区号+号码”格式发送，仅数字，例如美国 “+11234567890”，英国 “+441234567890”。\n\n"
        "Welcome! Please send the customer's phone number. I will check for duplicates.\n"
        "Use format: +countrycode+number, digits only, e.g., US “+11234567890”, UK “+441234567890”."
    )

# 单个号码处理：要求以 + 开头，后面 7~15 位数字
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    username = update.message.from_user.username or "unknown"
    added_time = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')

    # 校验：必须以 + 开头，且后面 7~15 位纯数字
    if not (text.startswith("+") and text[1:].isdigit() and 7 <= len(text[1:]) <= 15):
        await update.message.reply_text(
            "❌ 无效格式。请输入以“+”开头加国家区号的号码，仅数字，"
            "例如美国 “+11234567890”，英国 “+441234567890”。\n"
            "❌ Invalid format. Must start with '+', followed by 7–15 digits, e.g., +11234567890 or +441234567890."
        )
        return

    if number_exists(text):
        await update.message.reply_text(
            f"⚠️ 该号码已存在。\nThe number already exists.\n📱 {text}"
        )
    else:
        add_number(username, text, added_time)
        await update.message.reply_text(
            f"✅ 号码已保存！\nThe number has been saved.\n📱 {text}"
        )

# 批量添加：同样要求以 + 开头
async def batch_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "⚠️ 用法：\n"
            "/batch <每行一个号码>\n"
            "例如：\n"
            "/batch\n"
            "+11234567890\n"
            "+441234567890"
        )
        return

    numbers = context.args
    username = update.message.from_user.username or "unknown"
    added_time = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')

    added_list, exists_list, invalid_list = [], [], []
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    for num in numbers:
        num = num.strip()
        # 验证 + 开头，后面 7~15 位数字
        if num.startswith("+") and num[1:].isdigit() and 7 <= len(num[1:]) <= 15:
            cur.execute("SELECT 1 FROM clients WHERE phone_number = ?", (num,))
            if cur.fetchone():
                exists_list.append(num)
            else:
                cur.execute(
                    "INSERT INTO clients (username, phone_number, added_time) VALUES (?, ?, ?)",
                    (username, num, added_time)
                )
                added_list.append(num)
        else:
            invalid_list.append(num)

    conn.commit()
    conn.close()

    msg = "📋 批量导入结果 Batch Import Result:\n\n"
    if added_list:
        msg += "✅ 已添加 Added:\n" + "\n".join(added_list) + "\n\n"
    if exists_list:
        msg += "🚨 已存在 (跳过) Already Exists (Skipped):\n" + "\n".join(exists_list) + "\n\n"
    if invalid_list:
        msg += "⚠️ 无效格式 Invalid Format:\n" + "\n".join(invalid_list)
    await update.message.reply_text(msg)


async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/export 导出并发送 Excel 文件"""
    export_clients()
    with open("clients.xlsx", "rb") as f:
        await update.message.reply_document(
            document=f,
            filename="clients.xlsx",
            caption="✅ 数据已导出，见附件。\n✅ Data has been exported. See attached file."
        )

async def import_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/import 接收上传的 Excel 并导入"""
    if update.message.document:
        file = update.message.document
        new_file = await file.get_file()
        content = await new_file.download()
        with open("imported_clients.xlsx", "wb") as f:
            f.write(content)
        res = import_data("imported_clients.xlsx")
        await update.message.reply_text(res)

# ========== 启动 Bot ==========
def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    init_db()

    # TODO: 把 'YOUR_TELEGRAM_BOT_TOKEN' 替换为你的真实 Bot Token
    application = Application.builder().token('7640165528:AAF5y3I-sEZ1ZJRCOR3mjstVuJ84AzMI67w').build()

    # 注册命令和消息处理器
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("batch", batch_input))
    application.add_handler(CommandHandler("export", export))
    application.add_handler(CommandHandler("import", import_file))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
