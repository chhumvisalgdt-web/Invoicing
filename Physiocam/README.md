# Physiocam invoice bot

When someone posts an original CAMMED LAB invoice PDF (`invoice_xxxxxx.pdf`) in the
Telegram group, the bot replies with the 2-page Physiocam invoice:

- **Page 1:** the original invoice, unchanged.
- **Page 2:** the same invoice with `Original Amount`, `Total for customer`,
  `Discount` (35%) and `Total` rows.

The reply file is named after the customer, e.g. `IM SOVANN PHALLA.pdf`.
Other PDFs (lab reports, already-converted invoices) are ignored silently.

## Settings

- `DISCOUNT_RATE` in [invoice.py](invoice.py): currently 35%.
- [fixed_prices.xlsx](fixed_prices.xlsx): tests that get **no discount**. The bot reads the
  `Test` column of the first sheet; names match ignoring upper/lower case, extra spaces and a
  trailing `*`. To change the list, edit or replace this file and redeploy.

## Telegram setup (once)

1. In @BotFather send `/setprivacy`, pick the bot and choose **Disable**.
   Without this the bot can't see files posted in a group.
   (Making the bot a group admin also works.)
2. Remove the bot from the group and add it again so the change takes effect.

## Deploy on Railway

1. Push this folder to a GitHub repository (the `.gitignore` keeps `.venv`, `.env` and `out/` out).
2. In Railway: **New Project → Deploy from GitHub repo** and pick the repo.
   `railway.json` sets the start command (`python bot.py`).
3. In the service's **Variables** tab add:
   - `BOT_TOKEN`: the token from @BotFather.
   - `ALLOWED_CHAT_IDS` (optional): the group's id (starts with `-100`) so the bot only
     answers there.
4. Keep the service at **1 replica**, and make sure nothing else is running with the
   same token: two copies polling the same bot fight each other (`409 Conflict`).

## Run locally

```bash
py -m venv .venv
```

```bash
.venv\Scripts\python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, fill in `BOT_TOKEN`, then:

```bash
.venv\Scripts\python bot.py
```

Convert files without Telegram:

```bash
.venv\Scripts\python invoice.py out "C:\path\to\invoice_160776.pdf"
```

Fonts: `fonts/DejaVuSerifCondensed-Bold.ttf` is from the official DejaVu release
(free license in `fonts/DEJAVU-LICENSE`), the same typeface the originals use.
