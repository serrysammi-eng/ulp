# DERRYSVB LOG CHECKER — SETUP GUIDE
# @derrysvb

---

## STEP 1 — Get Bot Token

1. Open Telegram → search @BotFather
2. Send: /newbot
3. Give it a name: "Derrysvb Log Checker"
4. Give it a username: "derrysvb_checker_bot"
5. Copy the token: 7123456789:AAFxxxxxxxxxxxxxxx

---

## STEP 2 — Get Your Telegram User ID

1. Open @userinfobot on Telegram
2. Send /start
3. Copy your numeric ID (e.g. 987654321)

---

## STEP 3 — Free 24/7 Hosting (Railway)

1. Go to: https://github.com → New repository → Name it "derrysvb-bot"
2. Upload these files:
   - bot.py
   - requirements.txt
   - Procfile
   - (Create empty /logs folder — add a .gitkeep file inside)

3. Go to: https://railway.app
4. Login with GitHub
5. Click "New Project" → "Deploy from GitHub repo"
6. Select your repo

7. Go to "Variables" tab → Add:
   BOT_TOKEN = 7123456789:AAFxxxxxxxxxxxxxxx
   OWNER_ID  = 987654321

8. Click Deploy → Done. Bot is live 24/7 for FREE.

---

## STEP 4 — Auto Channel Downloader (Optional)

This runs on YOUR computer or a separate VPS.
It logs into your Telegram account and downloads files automatically.

### Get API credentials:
1. Go to: https://my.telegram.org
2. Login with your phone number
3. Click "API Development Tools"
4. Create app → Copy API_ID and API_HASH

### Setup auto_downloader.py:
Open the file and add your channel IDs to WATCH_CHATS:
```python
WATCH_CHATS = [
    -1001234567890,   # your channel ID
    -1009876543210,   # another channel
    "channelname",    # or username
]
```

### Run it:
```bash
pip install telethon
API_ID=12345 API_HASH=yourhash python auto_downloader.py
```
First run will ask for your phone number + OTP (one time only).
After that it runs silently forever.

### To get a Channel ID:
Forward any message from that channel to @userinfobot
It will show the channel ID.

---

## STEP 5 — Add Predefined Logs to Server

Upload your .rar / .txt files to Railway:
1. Put files in the /logs/ folder in your GitHub repo
2. Push to GitHub → Railway auto-redeploys
3. Or use Railway's CLI to upload directly

---

## HOW THE BOT WORKS

### User uploads .rar or .txt:
- File is SILENTLY saved to server /logs/ folder
- User only sees "Send a keyword to search"
- Every uploaded file stays on server permanently

### User types keyword:
- Bot scans ALL files in /logs/ (predefined + uploaded)
- Extracts matching combos
- Sends back as .txt file with your credits

### Formats it handles:
- https://site.com:user@email.com:password
- user@email.com:password
- https://site.com | user | password
- username:password

---

## OWNER COMMANDS (only works for your account)

/addpremium 123456789     → Give someone premium
/removepremium 123456789  → Remove premium
/listpremium              → See all premium users

---

## USER COMMANDS

/start    → Welcome screen
/search   → Search by keyword
/stats    → Their usage stats
/dbstats  → Server database info

Or just type any keyword directly to search.

---

## FREE vs PREMIUM

FREE:     5 searches per day (resets midnight)
PREMIUM:  Unlimited searches

---

## FILE SIZE LIMITS

Max file size per upload: 200 MB
Max file size inside RAR: 500 MB per inner file
Large files are processed in chunks — bot won't freeze

---

## CREDITS APPEAR IN EVERY RESULT FILE

Top:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   🔥  DERRYSVB LOG CHECKER  🔥
   📌 Telegram : @derrysvb
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Bottom:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ✅ Checked by @derrysvb
   💎 Premium = Unlimited Searches
   📌 Contact : @derrysvb
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
