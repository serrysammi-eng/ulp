# DERRYSVB LOG CHECKER v3.0
**Bot: @derryulpbot | Admin: @derrysvb**

## Deploy on Hugging Face Spaces (Free, 24/7)

1. huggingface.co → New Space → Docker → Private
2. Upload all files from this folder
3. Space Settings → Persistent Storage → Enable → Mount: /app/logs
4. Space Settings → Variables and Secrets — NOT needed (hardcoded)
5. Bot auto-starts, background downloader runs silently

## Admin Commands (Owner only)
| Command | Action |
|---------|--------|
| `/dbstats` | Full DB stats (files, lines, size) |
| `/addpremium 123456` | Give premium |
| `/removepremium 123456` | Remove premium |
| `/listpremium` | List premium users |
| `/addchat -100123` | Add auto-download channel |
| `/listchats` | List watched channels |
| `/removechat -100123` | Remove channel |

## Supported Formats
- `url:login:pass`
- `login:pass`
- `email:pass`
- HOST/URL block format
- URL | user | pass format

## File Support
- .txt .log .csv — up to 20MB via Bot API
- .zip .rar — up to 20MB via Bot API
- ANY size — via Telethon (auto)
