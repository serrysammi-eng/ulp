# ╔══════════════════════════════════════════════════════╗
# ║    DERRYSVB — AUTO CHANNEL DOWNLOADER               ║
# ║    Runs separately using your Telegram account      ║
# ║    Silently downloads log files → /logs/ folder     ║
# ╚══════════════════════════════════════════════════════╝

import os
import json
import asyncio
import hashlib
from pathlib import Path
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename

# ── CONFIG ─────────────────────────────────────────────
# ── CONFIG ─────────────────────────────────────────────
API_ID    = 35538142
API_HASH  = "17498b47a691e695150d8600d349249d"
SESSION   = "derrysvb_session"
LOGS_DIR  = Path("logs")
DATA_FILE = Path("data.json")
MAX_MB    = 200

# Add the chat IDs or usernames you want to monitor
# Examples: -1001234567890 or "mychannelusername" or "mygroupname"
WATCH_CHATS = [
    # -1001234567890,   # add your channel/group IDs here
    # "channelname",
]

VALID_EXT = {'.rar', '.zip', '.txt', '.log', '.csv'}
# ───────────────────────────────────────────────────────

LOGS_DIR.mkdir(exist_ok=True)

def load_seen() -> set:
    if DATA_FILE.exists():
        try:
            d = json.loads(DATA_FILE.read_text())
            return set(d.get("seen_files", []))
        except:
            pass
    return set()

def save_seen(seen: set):
    d = {}
    if DATA_FILE.exists():
        try:
            d = json.loads(DATA_FILE.read_text())
        except:
            pass
    lst = list(seen)
    if len(lst) > 10000:
        lst = lst[-5000:]
    d["seen_files"] = lst
    DATA_FILE.write_text(json.dumps(d, indent=2))

def get_filename(doc) -> str:
    for attr in doc.attributes:
        if isinstance(attr, DocumentAttributeFilename):
            return attr.file_name
    return f"file_{doc.id}"

def make_safe_name(original: str) -> str:
    uid = hashlib.md5(original.encode()).hexdigest()[:8]
    return f"{uid}_{original}"


async def download_if_new(client: TelegramClient, msg, seen: set) -> bool:
    if not msg.document:
        return False

    doc      = msg.document
    fname    = get_filename(doc)
    ext      = Path(fname).suffix.lower()
    file_id  = str(doc.id)

    if ext not in VALID_EXT:
        return False

    if file_id in seen:
        return False

    size_mb = doc.size / (1024 * 1024)
    if size_mb > MAX_MB:
        print(f"[SKIP] Too large ({size_mb:.1f}MB): {fname}")
        seen.add(file_id)
        return False

    safe  = make_safe_name(fname)
    dest  = LOGS_DIR / safe

    if dest.exists():
        seen.add(file_id)
        return False

    print(f"[DL] Downloading: {fname} ({size_mb:.1f}MB)")
    try:
        await client.download_media(msg, file=str(dest))
        seen.add(file_id)
        save_seen(seen)
        print(f"[DL] ✅ Saved: {safe}")
        return True
    except Exception as e:
        print(f"[DL ERROR] {fname}: {e}")
        return False


async def main():
    if not API_ID or not API_HASH:
        print("[ERROR] Set API_ID and API_HASH in environment variables")
        print("Get them from: https://my.telegram.org")
        return

    print("[derrysvb] Auto-downloader starting...")
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    print("[derrysvb] Logged in.")

    seen = load_seen()

    # ── Pull existing history first ──────────────────────
    if WATCH_CHATS:
        print("[SCAN] Scanning existing messages in watched chats...")
        for chat in WATCH_CHATS:
            try:
                entity = await client.get_entity(chat)
                print(f"[SCAN] Checking: {getattr(entity, 'title', str(chat))}")
                async for msg in client.iter_messages(entity, filter=None):
                    if msg.document:
                        await download_if_new(client, msg, seen)
                print(f"[SCAN] Done: {getattr(entity, 'title', str(chat))}")
            except Exception as e:
                print(f"[SCAN ERROR] {chat}: {e}")
        print("[SCAN] History scan complete.")

    # ── Listen for new messages ──────────────────────────
    @client.on(events.NewMessage(chats=WATCH_CHATS if WATCH_CHATS else None))
    async def on_new(event):
        if event.document:
            await download_if_new(client, event.message, seen)

    print("[derrysvb] Listening for new files...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
