# ╔══════════════════════════════════════════════════════╗
# ║         DERRYSVB LOG CHECKER BOT                     ║
# ║         Telegram: @derrysvb                          ║
# ╚══════════════════════════════════════════════════════╝

import os
import re
import json
import rarfile
import asyncio
import aiofiles
import datetime
import hashlib
import zipfile
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ── CONFIG ─────────────────────────────────────────────────────────────
BOT_TOKEN     = os.getenv("BOT_TOKEN", "8600054909:AAGkHGnqDxt-g491QxAC5gS0Yk2oivi__Sw")
OWNER_ID      = int(os.getenv("OWNER_ID", "8686102690"))
LOGS_DIR      = Path("logs")
UPLOAD_DIR    = Path("uploads")
TEMP_DIR      = Path("temp")
DATA_FILE     = Path("data.json")
FREE_LIMIT    = 5
MAX_FILE_MB   = 200          # max file size in MB
CHUNK_LINES   = 500_000      # process large files in chunks

# Channels/chats to auto-download from (add your channel IDs here)
# Format: [-1001234567890, -1009876543210]
AUTO_DOWNLOAD_CHATS = []

CREDITS_TOP = (
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "   🔥  DERRYSVB LOG CHECKER  🔥\n"
    "   📌 Telegram : @derrysvb\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
)
CREDITS_BOTTOM = (
    "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "   ✅ Checked by @derrysvb\n"
    "   💎 Premium = Unlimited Searches\n"
    "   📌 Contact : @derrysvb\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
)
# ───────────────────────────────────────────────────────────────────────

for d in [LOGS_DIR, UPLOAD_DIR, TEMP_DIR]:
    d.mkdir(exist_ok=True)


# ── DATA LAYER ─────────────────────────────────────────────────────────
def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except:
            pass
    return {"usage": {}, "premium": [], "seen_files": []}

def save_data(d: dict):
    DATA_FILE.write_text(json.dumps(d, indent=2))

def is_premium(uid: int) -> bool:
    d = load_data()
    return uid == OWNER_ID or str(uid) in d.get("premium", [])

def get_usage(uid: int) -> int:
    d = load_data()
    key = f"{uid}_{datetime.date.today()}"
    return d.get("usage", {}).get(key, 0)

def increment_usage(uid: int):
    d = load_data()
    key = f"{uid}_{datetime.date.today()}"
    d.setdefault("usage", {})[key] = d["usage"].get(key, 0) + 1
    save_data(d)

def add_premium(uid: int):
    d = load_data()
    if str(uid) not in d.get("premium", []):
        d.setdefault("premium", []).append(str(uid))
    save_data(d)

def remove_premium(uid: int):
    d = load_data()
    d["premium"] = [x for x in d.get("premium", []) if x != str(uid)]
    save_data(d)

def is_seen_file(file_id: str) -> bool:
    d = load_data()
    return file_id in d.get("seen_files", [])

def mark_seen_file(file_id: str):
    d = load_data()
    d.setdefault("seen_files", []).append(file_id)
    # keep list from growing forever
    if len(d["seen_files"]) > 10000:
        d["seen_files"] = d["seen_files"][-5000:]
    save_data(d)


# ── PARSER ENGINE ──────────────────────────────────────────────────────
def extract_combos_from_chunk(chunk: str, target: str | None) -> list[str]:
    results = set()
    t = target.lower() if target else None

    # Format 1: https://url.com:user:pass
    for url, user, pwd in re.findall(
        r'(https?://[^\s:]+):([^\s:\n]+):([^\s:\n]+)', chunk
    ):
        if t is None or t in url.lower():
            results.add(f"{url}:{user}:{pwd}")

    # Format 2: email:pass (no url)
    for user, pwd in re.findall(
        r'^(?!http)([a-zA-Z0-9_.+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}):([^\s:\n]+)$',
        chunk, re.MULTILINE
    ):
        results.add(f"{user}:{pwd}")

    # Format 3: URL | user | pass
    for url, user, pwd in re.findall(
        r'(https?://[^\s|]+)\s*\|\s*([^\s|\n]+)\s*\|\s*([^\s|\n]+)', chunk
    ):
        if t is None or t in url.lower():
            results.add(f"{url}:{user}:{pwd}")

    # Format 4: LOGIN:PASS (plain, non-email)
    for user, pwd in re.findall(
        r'^(?!http)([a-zA-Z0-9_.\-]{3,40}):([^\s:\n]{4,60})$',
        chunk, re.MULTILINE
    ):
        # skip if already captured as email:pass
        if "@" not in user:
            results.add(f"{user}:{pwd}")

    return list(results)


def process_large_text(text: str, target: str | None) -> list[str]:
    """Chunked processing for huge files — avoids RAM blowout"""
    lines = text.splitlines()
    all_combos = []
    for i in range(0, len(lines), CHUNK_LINES):
        chunk = "\n".join(lines[i:i + CHUNK_LINES])
        all_combos.extend(extract_combos_from_chunk(chunk, target))
    return list(dict.fromkeys(all_combos))  # deduplicate preserving order


def read_rar_safe(path: str) -> str:
    """Handles large .rar files safely"""
    combined = []
    try:
        with rarfile.RarFile(path) as rf:
            for info in rf.infolist():
                if Path(info.filename).suffix.lower() in ('.txt', '.log', '.csv'):
                    # skip individual files > 500MB inside rar
                    if info.file_size > 500 * 1024 * 1024:
                        combined.append(f"[SKIPPED - too large: {info.filename}]")
                        continue
                    with rf.open(info) as fh:
                        combined.append(fh.read().decode('utf-8', errors='ignore'))
    except rarfile.BadRarFile:
        combined.append("[ERROR] Corrupt or password-protected RAR")
    except Exception as e:
        combined.append(f"[ERROR] {e}")
    return "\n".join(combined)


def read_zip_safe(path: str) -> str:
    combined = []
    try:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if Path(name).suffix.lower() in ('.txt', '.log', '.csv'):
                    info = zf.getinfo(name)
                    if info.file_size > 500 * 1024 * 1024:
                        continue
                    with zf.open(name) as fh:
                        combined.append(fh.read().decode('utf-8', errors='ignore'))
    except Exception as e:
        combined.append(f"[ERROR] {e}")
    return "\n".join(combined)


def scan_all_logs(target: str | None = None) -> list[str]:
    """Scan entire /logs/ — predefined + all user-uploaded files"""
    all_combos = []
    for fp in LOGS_DIR.glob("**/*"):
        if not fp.is_file():
            continue
        ext = fp.suffix.lower()
        try:
            if ext == '.rar':
                text = read_rar_safe(str(fp))
            elif ext == '.zip':
                text = read_zip_safe(str(fp))
            elif ext in ('.txt', '.log', '.csv'):
                # stream large files
                text = fp.read_text(encoding='utf-8', errors='ignore')
            else:
                continue
            all_combos.extend(process_large_text(text, target))
        except Exception as e:
            print(f"[SCAN ERROR] {fp}: {e}")
    return list(dict.fromkeys(all_combos))


# ── SILENT FILE SAVER (no user notification) ───────────────────────────
async def save_to_server_silent(tg_file, original_name: str):
    """Download file to /logs/ silently — user never sees this happen"""
    ext = Path(original_name).suffix.lower()
    # unique name using hash to avoid collisions
    uid_str = hashlib.md5(original_name.encode()).hexdigest()[:8]
    safe_name = f"{uid_str}_{original_name}"
    dest = LOGS_DIR / safe_name
    if not dest.exists():
        await tg_file.download_to_drive(str(dest))
        print(f"[SERVER] Saved: {safe_name}")


# ── OUTPUT FILE BUILDER ────────────────────────────────────────────────
async def build_result_file(combos: list[str], keyword: str) -> Path:
    fname = f"results_{keyword.replace('.','_').replace('/','_')}.txt"
    out   = TEMP_DIR / fname
    ts    = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    async with aiofiles.open(out, 'w', encoding='utf-8') as f:
        await f.write(CREDITS_TOP)
        await f.write(f"🔍 Keyword  : {keyword}\n")
        await f.write(f"✅ Found    : {len(combos)} combos\n")
        await f.write(f"📅 Date     : {ts}\n\n")
        await f.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n")
        await f.write("\n".join(combos))
        await f.write(CREDITS_BOTTOM)
    return out


# ── SEARCH CORE ────────────────────────────────────────────────────────
async def do_search(update: Update, keyword: str, uid: int):
    if not is_premium(uid):
        used = get_usage(uid)
        if used >= FREE_LIMIT:
            await update.message.reply_text(
                "⛔ *Daily limit reached* (5/5)\n\n"
                "You've used all your free searches for today.\n"
                "🔄 Resets at midnight\n\n"
                "💎 Want unlimited? Contact @derrysvb for Premium",
                parse_mode="Markdown"
            )
            return

    msg = await update.message.reply_text(
        f"🔍 Searching `{keyword}` across all logs...\n"
        f"_(This may take a moment for large databases)_",
        parse_mode="Markdown"
    )

    # Run in executor so bot doesn't freeze on large scans
    loop = asyncio.get_event_loop()
    combos = await loop.run_in_executor(None, scan_all_logs, keyword)

    increment_usage(uid)
    used_now   = get_usage(uid)
    remaining  = "∞" if is_premium(uid) else max(0, FREE_LIMIT - used_now)

    await msg.delete()

    if not combos:
        await update.message.reply_text(
            f"❌ *No results* for `{keyword}`\n\n"
            f"📊 Searches left today: `{remaining}`\n"
            f"📌 @derrysvb",
            parse_mode="Markdown"
        )
        return

    out_file = await build_result_file(combos, keyword)

    caption = (
        f"✅ *Results for:* `{keyword}`\n"
        f"📦 *Combos found:* `{len(combos):,}`\n"
        f"📊 *Searches left:* `{remaining}`\n"
        f"📌 @derrysvb"
    )

    async with aiofiles.open(out_file, 'rb') as f:
        raw = await f.read()

    await update.message.reply_document(
        document=raw,
        filename=out_file.name,
        caption=caption,
        parse_mode="Markdown"
    )

    try:
        out_file.unlink()
    except:
        pass


# ── COMMANDS ───────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid  = user.id
    plan = "💎 Premium — Unlimited" if is_premium(uid) else f"🆓 Free — {get_usage(uid)}/{FREE_LIMIT} used today"
    kb = [
        [InlineKeyboardButton("🔍 Search Logs", callback_data="hint_search"),
         InlineKeyboardButton("📊 My Stats",    callback_data="my_stats")],
        [InlineKeyboardButton("💎 Get Premium", callback_data="get_premium"),
         InlineKeyboardButton("📤 Upload File", callback_data="hint_upload")],
    ]
    await update.message.reply_text(
        f"🔥 *DERRYSVB LOG CHECKER*\n"
        f"📌 @derrysvb\n\n"
        f"👤 *User:* {user.first_name}\n"
        f"📋 *Plan:* {plan}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*Commands:*\n"
        f"`/search <keyword>` — Search all logs\n"
        f"`/stats` — Your usage stats\n"
        f"`/dbstats` — Database info\n\n"
        f"💡 Or just *type any URL keyword* to search instantly!",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )


async def search_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "Usage: `/search netflix.com`\n\nOr just type a keyword directly.",
            parse_mode="Markdown"
        )
        return
    await do_search(update, " ".join(ctx.args).strip(), update.effective_user.id)


async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    used = get_usage(uid)
    plan = "💎 Premium — Unlimited" if is_premium(uid) else f"🆓 Free — {used}/{FREE_LIMIT}"
    await update.message.reply_text(
        f"📊 *Your Stats*\n\n"
        f"📋 Plan: {plan}\n"
        f"🔍 Searches today: `{used}`\n\n"
        f"📌 @derrysvb",
        parse_mode="Markdown"
    )


async def dbstats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    loop = asyncio.get_event_loop()

    def count_db():
        total_files = 0
        total_bytes = 0
        for fp in LOGS_DIR.glob("**/*"):
            if fp.is_file() and fp.suffix.lower() in ('.rar', '.zip', '.txt', '.log', '.csv'):
                total_files += 1
                total_bytes += fp.stat().st_size
        return total_files, total_bytes

    total_files, total_bytes = await loop.run_in_executor(None, count_db)
    size_mb = total_bytes / (1024 * 1024)
    size_str = f"{size_mb:.1f} MB" if size_mb < 1024 else f"{size_mb/1024:.2f} GB"

    await update.message.reply_text(
        f"🗄️ *Server Database*\n\n"
        f"📁 Log files: `{total_files}`\n"
        f"💾 Total size: `{size_str}`\n\n"
        f"📌 @derrysvb",
        parse_mode="Markdown"
    )


# ── FILE UPLOAD HANDLER ────────────────────────────────────────────────
async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return

    fname = doc.file_name or "upload.txt"
    ext   = Path(fname).suffix.lower()
    uid   = update.effective_user.id

    if ext not in ('.rar', '.zip', '.txt', '.log', '.csv'):
        await update.message.reply_text(
            "⚠️ Supported formats: `.rar` `.zip` `.txt` `.log` `.csv`",
            parse_mode="Markdown"
        )
        return

    # File size check
    size_mb = doc.file_size / (1024 * 1024) if doc.file_size else 0
    if size_mb > MAX_FILE_MB:
        await update.message.reply_text(
            f"⚠️ File too large ({size_mb:.1f} MB)\n"
            f"Max allowed: {MAX_FILE_MB} MB per file\n\n"
            f"For larger files contact @derrysvb",
            parse_mode="Markdown"
        )
        return

    # Check if already seen (dedup)
    file_unique = doc.file_unique_id
    tg_file = await doc.get_file()

    if not is_seen_file(file_unique):
        # SILENT save to server — user just sees a search prompt
        await save_to_server_silent(tg_file, fname)
        mark_seen_file(file_unique)

    # Ask for keyword to search — this is the only thing user sees
    ctx.user_data['waiting_keyword'] = True
    await update.message.reply_text(
        "🔍 *File received!*\n\n"
        "Send a URL keyword to search:\n"
        "Example: `netflix.com` or `spotify` or `amazon`\n\n"
        "Or type `all` to extract everything",
        parse_mode="Markdown"
    )


# ── TEXT HANDLER ───────────────────────────────────────────────────────
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid  = update.effective_user.id

    # ── Owner-only commands ──
    if uid == OWNER_ID:
        if text.startswith("/addpremium"):
            parts = text.split()
            if len(parts) == 2:
                add_premium(int(parts[1]))
                await update.message.reply_text(f"✅ Premium added: `{parts[1]}`", parse_mode="Markdown")
                return
        if text.startswith("/removepremium"):
            parts = text.split()
            if len(parts) == 2:
                remove_premium(int(parts[1]))
                await update.message.reply_text(f"✅ Premium removed: `{parts[1]}`", parse_mode="Markdown")
                return
        if text.startswith("/listpremium"):
            d = load_data()
            lst = "\n".join(d.get("premium", [])) or "None"
            await update.message.reply_text(f"💎 Premium users:\n`{lst}`", parse_mode="Markdown")
            return
        if text.startswith("/addchat"):
            parts = text.split()
            if len(parts) == 2:
                AUTO_DOWNLOAD_CHATS.append(int(parts[1]))
                await update.message.reply_text(f"✅ Auto-download chat added: `{parts[1]}`", parse_mode="Markdown")
                return

    # Treat as keyword search
    keyword = "all" if text.lower() == "all" else text
    target  = None if keyword == "all" else keyword
    await do_search(update, keyword, uid)


# ── AUTO DOWNLOAD FROM CHANNELS ────────────────────────────────────────
async def handle_channel_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Silently grab log files from configured channels/chats"""
    msg = update.message or update.channel_post
    if not msg:
        return

    chat_id = msg.chat.id
    if chat_id not in AUTO_DOWNLOAD_CHATS:
        return

    doc = msg.document
    if not doc:
        return

    fname = doc.file_name or "auto.txt"
    ext   = Path(fname).suffix.lower()

    if ext not in ('.rar', '.zip', '.txt', '.log', '.csv'):
        return

    file_unique = doc.file_unique_id
    if is_seen_file(file_unique):
        return  # already downloaded

    size_mb = doc.file_size / (1024 * 1024) if doc.file_size else 0
    if size_mb > MAX_FILE_MB:
        print(f"[AUTO] Skipped (too large {size_mb:.1f}MB): {fname}")
        return

    try:
        tg_file = await doc.get_file()
        await save_to_server_silent(tg_file, fname)
        mark_seen_file(file_unique)
        print(f"[AUTO] Saved from channel {chat_id}: {fname}")
    except Exception as e:
        print(f"[AUTO ERROR] {fname}: {e}")


# ── CALLBACK BUTTONS ──────────────────────────────────────────────────
async def callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "hint_search":
        await q.message.reply_text(
            "🔍 Send any URL keyword to search:\n\n"
            "Examples:\n`netflix.com`\n`spotify`\n`amazon.com`\n`instagram`",
            parse_mode="Markdown"
        )
    elif q.data == "hint_upload":
        await q.message.reply_text(
            "📤 Send your `.rar`, `.zip` or `.txt` file directly in chat.\n\n"
            f"Max size: {MAX_FILE_MB} MB"
        )
    elif q.data == "my_stats":
        await stats_cmd(q, ctx)
    elif q.data == "get_premium":
        await q.message.reply_text(
            "💎 *Premium Plan*\n\n"
            "✅ Unlimited daily searches\n"
            "✅ Instant results\n"
            "✅ Priority extraction\n\n"
            "📩 Contact: @derrysvb",
            parse_mode="Markdown"
        )


# ── MAIN ──────────────────────────────────────────────────────────────
def main():
    print("[derrysvb] Starting bot...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("search",   search_cmd))
    app.add_handler(CommandHandler("stats",    stats_cmd))
    app.add_handler(CommandHandler("dbstats",  dbstats_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_text
    ))
    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Document.ALL,
        handle_channel_post
    ))
    app.add_handler(CallbackQueryHandler(callback))

    print("[derrysvb] Live. 6767.")
    app.run_polling(drop_pending_updates=True, allowed_updates=["message", "channel_post", "callback_query"])


if __name__ == "__main__":
    main()
