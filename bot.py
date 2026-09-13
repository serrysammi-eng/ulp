# ╔══════════════════════════════════════════════════════════════════════╗
# ║           DERRYSVB LOG CHECKER BOT — v3.0                          ║
# ║           Telegram: @derrysvb | Bot: @derryulpbot                  ║
# ╚══════════════════════════════════════════════════════════════════════╝

import os, re, json, asyncio, datetime, hashlib, zipfile, time
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
try:
    import rarfile
    RAR_OK = True
except ImportError:
    RAR_OK = False

try:
    from telethon import TelegramClient, events
    from telethon.tl.types import DocumentAttributeFilename
    TELETHON_OK = True
except ImportError:
    TELETHON_OK = False

import aiofiles

# ══════════════════════════════════════════════════════════════════════
# CONFIG — hardcoded
# ══════════════════════════════════════════════════════════════════════
BOT_TOKEN  = "8600054909:AAGkHGnqDxt-g491QxAC5gS0Yk2oivi__Sw"
OWNER_ID   = 8686102690
API_ID     = 35538142
API_HASH   = "17498b47a691e695150d8600d349249d"
SESSION    = "derrysvb_session"

LOGS_DIR   = Path("logs")
TEMP_DIR   = Path("temp")
DATA_FILE  = Path("data.json")

FREE_LIMIT   = 5
MAX_FILE_MB  = 4000    # 4GB cap via Telethon
CHUNK_LINES  = 300_000 # lines per parse chunk

# Auto-download channels (add via /addchat)
AUTO_CHATS: list[int] = [
    -1002512756597,
    -1002624488640,
]

BANNER_TOP = (
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "   🔥  DERRYSVB LOG CHECKER  🔥\n"
    "   📌 Telegram : @derrysvb\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
)
BANNER_BOT = (
    "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "   ✅ Checked by @derrysvb\n"
    "   💎 Premium = Unlimited\n"
    "   📌 Contact : @derrysvb\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
)

for d in [LOGS_DIR, TEMP_DIR]:
    d.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════
# DATA LAYER
# ══════════════════════════════════════════════════════════════════════
def load_data() -> dict:
    if DATA_FILE.exists():
        try: return json.loads(DATA_FILE.read_text())
        except: pass
    return {"usage": {}, "premium": [], "seen_files": [], "stats": {"total_lines": 0, "total_files": 0}}

def save_data(d: dict):
    DATA_FILE.write_text(json.dumps(d, indent=2))

def is_premium(uid: int) -> bool:
    d = load_data()
    return uid == OWNER_ID or str(uid) in d.get("premium", [])

def get_usage(uid: int) -> int:
    d   = load_data()
    key = f"{uid}_{datetime.date.today()}"
    return d.get("usage", {}).get(key, 0)

def increment_usage(uid: int):
    d   = load_data()
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

def is_seen(fid: str) -> bool:
    return fid in load_data().get("seen_files", [])

def mark_seen(fid: str):
    d = load_data()
    d.setdefault("seen_files", []).append(fid)
    if len(d["seen_files"]) > 20000:
        d["seen_files"] = d["seen_files"][-10000:]
    save_data(d)

# ══════════════════════════════════════════════════════════════════════
# PARSER ENGINE
# ══════════════════════════════════════════════════════════════════════
def parse_chunk(chunk: str, target: str | None) -> list[str]:
    results = set()
    t = target.lower() if target else None

    # FORMAT 1 — url:user:pass
    for url, user, pwd in re.findall(
        r'(https?://[^\s:]+):([^\s:\n\r]+):([^\s:\n\r]+)', chunk
    ):
        if t is None or t in url.lower():
            results.add(f"{url}:{user}:{pwd}")

    # FORMAT 2 — url | user | pass
    for url, user, pwd in re.findall(
        r'(https?://[^\s|]+)\s*\|\s*([^\s|\n\r]+)\s*\|\s*([^\s|\n\r]+)', chunk
    ):
        if t is None or t in url.lower():
            results.add(f"{url}:{user}:{pwd}")

    # FORMAT 3 — HOST/URL block
    for url, user, pwd in re.findall(
        r'(?:HOST|URL)[:\s]+([^\n\r]+)[\r\n]+(?:USER(?:NAME)?|LOGIN)[:\s]+([^\n\r]+)[\r\n]+(?:PASS(?:WORD)?)[:\s]+([^\n\r]+)',
        chunk, re.IGNORECASE
    ):
        if t is None or t in url.lower():
            results.add(f"{url.strip()}:{user.strip()}:{pwd.strip()}")

    # FORMAT 4 — email:pass
    for user, pwd in re.findall(
        r'^(?!http)([a-zA-Z0-9_.+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}):([^\s:\n\r]+)$',
        chunk, re.MULTILINE
    ):
        results.add(f"{user}:{pwd}")

    # FORMAT 5 — login:pass (plain, non-email, non-url)
    for user, pwd in re.findall(
        r'^(?!http)([a-zA-Z0-9_.+\-]{3,50}):([^\s:\n\r]{4,80})$',
        chunk, re.MULTILINE
    ):
        if '@' not in user:
            results.add(f"{user}:{pwd}")

    return list(results)


def parse_text(text: str, target: str | None) -> list[str]:
    lines     = text.splitlines()
    all_out   = []
    for i in range(0, len(lines), CHUNK_LINES):
        chunk = "\n".join(lines[i:i + CHUNK_LINES])
        all_out.extend(parse_chunk(chunk, target))
    return list(dict.fromkeys(all_out))


def count_lines_text(text: str) -> int:
    return text.count('\n')


def read_zip(path: str) -> str:
    out = []
    try:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if Path(name).suffix.lower() in ('.txt', '.log', '.csv'):
                    info = zf.getinfo(name)
                    if info.file_size > 2 * 1024 ** 3: continue
                    with zf.open(name) as fh:
                        out.append(fh.read().decode('utf-8', errors='ignore'))
    except Exception as e:
        out.append(f"[ZIP ERROR] {e}")
    return "\n".join(out)


def read_rar(path: str) -> str:
    if not RAR_OK:
        return "[RAR] rarfile not installed"
    out = []
    try:
        with rarfile.RarFile(path) as rf:
            for info in rf.infolist():
                if Path(info.filename).suffix.lower() in ('.txt', '.log', '.csv'):
                    if info.file_size > 2 * 1024 ** 3:
                        out.append(f"[SKIPPED large: {info.filename}]")
                        continue
                    with rf.open(info) as fh:
                        out.append(fh.read().decode('utf-8', errors='ignore'))
    except Exception as e:
        out.append(f"[RAR ERROR] {e}")
    return "\n".join(out)


def scan_all_logs(target: str | None = None) -> list[str]:
    all_combos = []
    for fp in sorted(LOGS_DIR.glob("**/*")):
        if not fp.is_file(): continue
        ext = fp.suffix.lower()
        try:
            if ext == '.rar':   text = read_rar(str(fp))
            elif ext == '.zip': text = read_zip(str(fp))
            elif ext in ('.txt', '.log', '.csv'):
                text = fp.read_text(encoding='utf-8', errors='ignore')
            else: continue
            all_combos.extend(parse_text(text, target))
        except Exception as e:
            print(f"[SCAN ERR] {fp}: {e}")
    return list(dict.fromkeys(all_combos))


def get_db_stats() -> dict:
    total_files = total_bytes = total_lines = 0
    for fp in LOGS_DIR.glob("**/*"):
        if not fp.is_file(): continue
        ext = fp.suffix.lower()
        if ext not in ('.rar', '.zip', '.txt', '.log', '.csv'): continue
        total_files += 1
        sz = fp.stat().st_size
        total_bytes += sz
        if ext in ('.txt', '.log', '.csv'):
            try:
                # count lines without loading full file
                with open(fp, 'rb') as f:
                    total_lines += sum(1 for _ in f)
            except: pass
    return {"files": total_files, "bytes": total_bytes, "lines": total_lines}


# ══════════════════════════════════════════════════════════════════════
# TELETHON LARGE FILE DOWNLOAD
# ══════════════════════════════════════════════════════════════════════
_tl_client: TelegramClient | None = None

async def get_tl_client() -> TelegramClient | None:
    global _tl_client
    if not TELETHON_OK or not API_ID or not API_HASH:
        return None
    if _tl_client is None or not _tl_client.is_connected():
        _tl_client = TelegramClient(SESSION, API_ID, API_HASH)
        await _tl_client.start(bot_token=BOT_TOKEN)
    return _tl_client


async def download_large(chat_id: int, msg_id: int, fname: str) -> Path | None:
    client = await get_tl_client()
    if not client: return None
    try:
        msg = await client.get_messages(chat_id, ids=msg_id)
        if not msg or not msg.document: return None
        safe = f"{hashlib.md5(f'{msg_id}{fname}'.encode()).hexdigest()[:8]}_{fname}"
        dest = LOGS_DIR / safe
        if dest.exists(): return dest
        print(f"[TL] Downloading large: {fname}")
        await client.download_media(msg, file=str(dest))
        print(f"[TL] Done: {safe}")
        return dest
    except Exception as e:
        print(f"[TL ERR] {e}")
        return None


async def download_small(tg_file, fname: str) -> Path | None:
    try:
        safe = f"{hashlib.md5(fname.encode()).hexdigest()[:8]}_{fname}"
        dest = LOGS_DIR / safe
        if not dest.exists():
            await tg_file.download_to_drive(str(dest))
            print(f"[DL] {safe}")
        return dest
    except Exception as e:
        print(f"[DL ERR] {e}")
        return None


# ══════════════════════════════════════════════════════════════════════
# BACKGROUND AUTO-DOWNLOADER (Telethon listener)
# ══════════════════════════════════════════════════════════════════════
VALID_EXT = {'.rar', '.zip', '.txt', '.log', '.csv'}

def tl_get_fname(doc) -> str:
    if not TELETHON_OK: return "file.txt"
    for attr in doc.attributes:
        if isinstance(attr, DocumentAttributeFilename):
            return attr.file_name
    return f"file_{doc.id}.txt"


async def auto_dl_msg(client, msg):
    if not msg.document: return
    doc     = msg.document
    fname   = tl_get_fname(doc)
    ext     = Path(fname).suffix.lower()
    file_id = str(doc.id)
    if ext not in VALID_EXT or is_seen(file_id): return
    size_mb = doc.size / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        print(f"[AUTO SKIP] {size_mb:.0f}MB > {MAX_FILE_MB}MB: {fname}")
        mark_seen(file_id)
        return
    safe = f"{hashlib.md5(f'{file_id}{fname}'.encode()).hexdigest()[:8]}_{fname}"
    dest = LOGS_DIR / safe
    if dest.exists():
        mark_seen(file_id)
        return
    print(f"[AUTO] {fname} ({size_mb:.1f}MB)")
    try:
        await client.download_media(msg, file=str(dest))
        mark_seen(file_id)
        print(f"[AUTO] ✅ {safe}")
    except Exception as e:
        print(f"[AUTO ERR] {fname}: {e}")


async def start_auto_downloader():
    """Background Telethon listener for configured channels"""
    if not TELETHON_OK or not API_ID or not API_HASH:
        print("[AUTO] Telethon not available — skipping background downloader")
        return
    if not AUTO_CHATS:
        print("[AUTO] No chats configured")
        return
    try:
        client = TelegramClient(f"{SESSION}_auto", API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        print(f"[AUTO] Connected. Scanning {len(AUTO_CHATS)} chats history...")

        for chat_id in AUTO_CHATS:
            try:
                entity = await client.get_entity(chat_id)
                title  = getattr(entity, 'title', str(chat_id))
                print(f"[AUTO SCAN] {title}")
                async for msg in client.iter_messages(entity):
                    if msg.document:
                        await auto_dl_msg(client, msg)
                print(f"[AUTO SCAN] Done: {title}")
            except Exception as e:
                print(f"[AUTO SCAN ERR] {chat_id}: {e}")

        @client.on(events.NewMessage(chats=AUTO_CHATS))
        async def on_new(event):
            await auto_dl_msg(client, event.message)

        print("[AUTO] Listening for new files...")
        await client.run_until_disconnected()
    except Exception as e:
        print(f"[AUTO FATAL] {e}")


# ══════════════════════════════════════════════════════════════════════
# RESULT FILE BUILDER
# ══════════════════════════════════════════════════════════════════════
async def build_result(combos: list[str], keyword: str) -> Path:
    fname = f"results_{re.sub(r'[^a-zA-Z0-9]', '_', keyword)}.txt"
    out   = TEMP_DIR / fname
    ts    = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    async with aiofiles.open(out, 'w', encoding='utf-8') as f:
        await f.write(BANNER_TOP)
        await f.write(f"🔍 Keyword : {keyword}\n")
        await f.write(f"✅ Found   : {len(combos):,} combos\n")
        await f.write(f"📅 Date    : {ts}\n\n")
        await f.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n")
        await f.write("\n".join(combos))
        await f.write(BANNER_BOT)
    return out


# ══════════════════════════════════════════════════════════════════════
# SEARCH
# ══════════════════════════════════════════════════════════════════════
async def do_search(update: Update, keyword: str, uid: int):
    if not is_premium(uid):
        used = get_usage(uid)
        if used >= FREE_LIMIT:
            await update.message.reply_text(
                "⛔ *Daily limit reached* (5/5)\n\n"
                "🔄 Resets at midnight\n"
                "💎 Contact @derrysvb for Premium",
                parse_mode="Markdown"
            )
            return

    proc = await update.message.reply_text(
        f"🔍 Searching `{keyword}` across all logs...\n_(large database, please wait)_",
        parse_mode="Markdown"
    )

    loop   = asyncio.get_event_loop()
    target = None if keyword.lower() == "all" else keyword
    combos = await loop.run_in_executor(None, scan_all_logs, target)

    increment_usage(uid)
    remaining = "∞" if is_premium(uid) else max(0, FREE_LIMIT - get_usage(uid))

    await proc.delete()

    if not combos:
        await update.message.reply_text(
            f"❌ *No results* for `{keyword}`\n\n"
            f"📊 Searches left: `{remaining}`\n📌 @derrysvb",
            parse_mode="Markdown"
        )
        return

    out_file = await build_result(combos, keyword)
    caption  = (
        f"✅ *Results: `{keyword}`*\n"
        f"📦 Found: `{len(combos):,}` combos\n"
        f"📊 Left: `{remaining}`\n"
        f"📌 @derrysvb"
    )
    async with aiofiles.open(out_file, 'rb') as f:
        raw = await f.read()
    await update.message.reply_document(
        document=raw, filename=out_file.name,
        caption=caption, parse_mode="Markdown"
    )
    try: out_file.unlink()
    except: pass


# ══════════════════════════════════════════════════════════════════════
# COMMANDS
# ══════════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    plan = "💎 Premium — Unlimited" if is_premium(uid) else f"🆓 Free — {get_usage(uid)}/{FREE_LIMIT} today"

    kb = [
        [InlineKeyboardButton("🔍 Search Logs",  callback_data="hint_search"),
         InlineKeyboardButton("📊 My Stats",     callback_data="my_stats")],
        [InlineKeyboardButton("🗄️ DB Status",    callback_data="db_status"),
         InlineKeyboardButton("💎 Get Premium",  callback_data="get_premium")],
        [InlineKeyboardButton("📤 How to Upload", callback_data="hint_upload"),
         InlineKeyboardButton("ℹ️ About",         callback_data="about")],
    ]
    await update.message.reply_text(
        f"🔥 *DERRYSVB LOG CHECKER*\n"
        f"📌 @derrysvb\n\n"
        f"👤 *User:* {update.effective_user.first_name}\n"
        f"📋 *Plan:* {plan}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*Commands:*\n"
        f"`/search <keyword>` — Search all logs\n"
        f"`/dbstats` — Full database info\n"
        f"`/stats` — Your usage stats\n\n"
        f"💡 Or just *type any keyword* to search instantly!\n"
        f"💡 Send a *.txt .zip .rar* file to add to DB",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )


async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: `/search netflix.com`", parse_mode="Markdown")
        return
    await do_search(update, " ".join(ctx.args).strip(), update.effective_user.id)


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    used = get_usage(uid)
    plan = "💎 Premium — Unlimited" if is_premium(uid) else f"🆓 Free — {used}/{FREE_LIMIT}"
    await update.message.reply_text(
        f"📊 *Your Stats*\n\n"
        f"📋 Plan: {plan}\n"
        f"🔍 Searches today: `{used}`\n"
        f"📌 @derrysvb",
        parse_mode="Markdown"
    )


async def cmd_dbstats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Owner only.")
        return
    proc = await update.message.reply_text("⏳ Counting database...")
    loop = asyncio.get_event_loop()
    st   = await loop.run_in_executor(None, get_db_stats)
    sz   = st['bytes']
    size_str = f"{sz/(1024**3):.2f} GB" if sz > 1024**3 else f"{sz/(1024**2):.1f} MB"
    lines_str = f"{st['lines']:,}"
    await proc.delete()
    await update.message.reply_text(
        f"🗄️ *Server Database — Full Stats*\n\n"
        f"📁 Log files: `{st['files']}`\n"
        f"📄 Total lines (txt/log): `{lines_str}`\n"
        f"💾 Total size: `{size_str}`\n"
        f"📡 Auto-chats watching: `{len(AUTO_CHATS)}`\n\n"
        f"📌 @derrysvb",
        parse_mode="Markdown"
    )


# ══════════════════════════════════════════════════════════════════════
# FILE UPLOAD HANDLER
# ══════════════════════════════════════════════════════════════════════
async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc   = update.message.document
    fname = doc.file_name or "upload.txt"
    ext   = Path(fname).suffix.lower()
    uid   = update.effective_user.id

    if ext not in ('.rar', '.zip', '.txt', '.log', '.csv'):
        if uid == OWNER_ID:
            await update.message.reply_text(f"⚠️ Unsupported: `{ext}`\nSend .rar .zip .txt .log .csv")
        return

    size_mb = (doc.file_size or 0) / (1024 * 1024)

    # ── LARGE FILE (>20MB) — use Telethon ──────────────────────────
    if size_mb > 20:
        proc = await update.message.reply_text(
            f"📥 Large file: `{fname}` ({size_mb:.0f}MB)\n"
            "⏳ Downloading via Telethon... (may take a few minutes)",
            parse_mode="Markdown"
        )
        path = await download_large(update.message.chat_id, update.message.message_id, fname)

        if not path:
            await proc.edit_text(
                f"❌ Download failed: `{fname}`\n"
                "Check that API_ID and API_HASH are correct.",
                parse_mode="Markdown"
            )
            return

        mark_seen(doc.file_unique_id)
        sz      = path.stat().st_size
        sz_str  = f"{sz/(1024**3):.2f}GB" if sz > 1024**3 else f"{sz/(1024**2):.0f}MB"

        if uid == OWNER_ID:
            await proc.edit_text(
                f"✅ *Saved to server*\n"
                f"📁 `{fname}`\n"
                f"💾 Size: `{sz_str}`\n\n"
                "Now send a keyword to search, or type `all`",
                parse_mode="Markdown"
            )
        else:
            await proc.delete()

        ctx.user_data['waiting_keyword'] = True
        return

    # ── SMALL FILE (<=20MB) — Bot API ──────────────────────────────
    if not is_seen(doc.file_unique_id):
        tg_file = await doc.get_file()
        path    = await download_small(tg_file, fname)
        if path:
            mark_seen(doc.file_unique_id)

    if uid == OWNER_ID:
        await update.message.reply_text(
            f"✅ *Saved to server*: `{fname}` ({size_mb:.1f}MB)\n\n"
            "Send a keyword to search, or type `all`",
            parse_mode="Markdown"
        )

    ctx.user_data['waiting_keyword'] = True


# ══════════════════════════════════════════════════════════════════════
# TEXT HANDLER
# ══════════════════════════════════════════════════════════════════════
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid  = update.effective_user.id

    # Owner-only admin commands
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
                await update.message.reply_text(f"✅ Removed: `{parts[1]}`", parse_mode="Markdown")
                return
        if text.startswith("/listpremium"):
            d   = load_data()
            lst = "\n".join(d.get("premium", [])) or "None"
            await update.message.reply_text(f"💎 Premium users:\n`{lst}`", parse_mode="Markdown")
            return
        if text.startswith("/addchat"):
            parts = text.split()
            if len(parts) == 2:
                cid = int(parts[1])
                if cid not in AUTO_CHATS:
                    AUTO_CHATS.append(cid)
                await update.message.reply_text(f"✅ Auto-chat added: `{cid}`", parse_mode="Markdown")
                return
        if text.startswith("/listchats"):
            lst = "\n".join(str(c) for c in AUTO_CHATS) or "None"
            await update.message.reply_text(f"📡 Watching:\n`{lst}`", parse_mode="Markdown")
            return
        if text.startswith("/removechat"):
            parts = text.split()
            if len(parts) == 2:
                cid = int(parts[1])
                if cid in AUTO_CHATS: AUTO_CHATS.remove(cid)
                await update.message.reply_text(f"✅ Removed: `{cid}`", parse_mode="Markdown")
                return

    await do_search(update, text, uid)


# ══════════════════════════════════════════════════════════════════════
# CHANNEL POST AUTO-SAVE
# ══════════════════════════════════════════════════════════════════════
async def handle_channel_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg: return
    if msg.chat.id not in AUTO_CHATS: return
    doc = msg.document
    if not doc: return
    fname = doc.file_name or "auto.txt"
    ext   = Path(fname).suffix.lower()
    if ext not in VALID_EXT: return
    if is_seen(doc.file_unique_id): return
    size_mb = (doc.file_size or 0) / (1024 * 1024)
    try:
        if size_mb > 20:
            path = await download_large(msg.chat.id, msg.message_id, fname)
        else:
            tg_file = await doc.get_file()
            path    = await download_small(tg_file, fname)
        if path:
            mark_seen(doc.file_unique_id)
            print(f"[AUTO BOT] Saved: {fname} from {msg.chat.id}")
    except Exception as e:
        print(f"[AUTO BOT ERR] {fname}: {e}")


# ══════════════════════════════════════════════════════════════════════
# CALLBACK BUTTONS
# ══════════════════════════════════════════════════════════════════════
async def callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if q.data == "hint_search":
        await q.message.reply_text(
            "🔍 *How to Search*\n\n"
            "Just type any keyword:\n"
            "`netflix.com`\n`spotify`\n`amazon`\n`gmail.com`\n\n"
            "Or use: `/search netflix.com`\n"
            "For everything: type `all`",
            parse_mode="Markdown"
        )

    elif q.data == "hint_upload":
        await q.message.reply_text(
            "📤 *How to Add Logs*\n\n"
            "Send a file directly in chat:\n"
            "• `.txt` `.log` `.csv` — up to 20MB via bot\n"
            "• `.zip` `.rar` — up to 20MB via bot\n"
            "• Files >20MB — auto downloaded via Telethon\n\n"
            "Logs are saved silently to the server.\n"
            "Users never see this happen.",
            parse_mode="Markdown"
        )

    elif q.data == "my_stats":
        used = get_usage(uid)
        plan = "💎 Premium" if is_premium(uid) else f"🆓 {used}/{FREE_LIMIT} today"
        await q.message.reply_text(
            f"📊 *Your Stats*\n\nPlan: {plan}\nToday: `{used}` searches\n📌 @derrysvb",
            parse_mode="Markdown"
        )

    elif q.data == "db_status":
        if uid != OWNER_ID:
            await q.message.reply_text("⛔ Owner only.")
            return
        loop = asyncio.get_event_loop()
        st   = await loop.run_in_executor(None, get_db_stats)
        sz   = st['bytes']
        size_str = f"{sz/(1024**3):.2f} GB" if sz > 1024**3 else f"{sz/(1024**2):.1f} MB"
        await q.message.reply_text(
            f"🗄️ *Database Status*\n\n"
            f"📁 Files: `{st['files']}`\n"
            f"📄 Lines: `{st['lines']:,}`\n"
            f"💾 Size: `{size_str}`\n"
            f"📡 Watching: `{len(AUTO_CHATS)}` chats\n\n"
            f"📌 @derrysvb",
            parse_mode="Markdown"
        )

    elif q.data == "get_premium":
        await q.message.reply_text(
            "💎 *Premium Plan*\n\n"
            "✅ Unlimited daily searches\n"
            "✅ Instant results\n"
            "✅ Priority extraction\n\n"
            "📩 Contact: @derrysvb",
            parse_mode="Markdown"
        )

    elif q.data == "about":
        await q.message.reply_text(
            "ℹ️ *About DERRYSVB LOG CHECKER*\n\n"
            "🔍 Searches ULP combos from massive log databases\n"
            "📦 Supports: `url:login:pass` `login:pass` `email:pass`\n"
            "📁 Handles: `.txt` `.log` `.csv` `.zip` `.rar`\n"
            "⚡ Large files up to 4GB via Telethon\n"
            "🔄 Background auto-download from channels\n\n"
            "📌 @derrysvb",
            parse_mode="Markdown"
        )


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
async def post_init(app):
    """Start background auto-downloader after bot starts"""
    asyncio.create_task(start_auto_downloader())

def main():
    print("[derrysvb] Starting bot... 6767")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("search",  cmd_search))
    app.add_handler(CommandHandler("stats",   cmd_stats))
    app.add_handler(CommandHandler("dbstats", cmd_dbstats))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(
        (filters.ChatType.CHANNEL | filters.ChatType.SUPERGROUP) & filters.Document.ALL,
        handle_channel_post
    ))
    app.add_handler(CallbackQueryHandler(callback))

    print("[derrysvb] Live. Polling. 6767.")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "channel_post", "callback_query"]
    )

if __name__ == "__main__":
    main()
