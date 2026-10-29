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
- **Fixed-price tests** get **no discount**. The bot takes the list from:
  1. the Railway variable `FIXED_PRICE_ITEMS`, if it is set: one test name per line
     (names separated by `;` also work). [fixed_prices_railway.txt](fixed_prices_railway.txt)
     has the current list ready to paste.
  2. otherwise the `Test` column of [fixed_prices.xlsx](fixed_prices.xlsx).

  Names match ignoring upper/lower case, extra spaces and a trailing `*`.
  When the bot starts, its log says how many fixed-price tests it loaded and from where,
  e.g. `93 fixed-price tests loaded from FIXED_PRICE_ITEMS variable`.
  For every invoice it logs which items were treated as fixed-price.

## Telegram setup (once)

1. In @BotFather send `/setprivacy`, pick the bot and choose **Disable**.
   Without this the bot can't see files posted in a group.
   (Making the bot a group admin also works.)
2. Remove the bot from the group and add it again so the change takes effect.

## Deploy on Railway

1. Upload this folder's files to a **private** GitHub repository. Never upload a `.env`
   file or the bot token.
2. In Railway: **New Project → Deploy from GitHub repo** and pick the repo.
   `railway.json` sets the start command (`python bot.py`).
3. In the service's **Variables** tab add:
   - `BOT_TOKEN`: the token from @BotFather.
   - `FIXED_PRICE_ITEMS` (optional): paste the contents of `fixed_prices_railway.txt`.
   - `ALLOWED_CHAT_IDS` (optional): the group's id (starts with `-100`) so the bot only
     answers there.

   Then click **Deploy** to apply the variables.
4. Keep the service at **1 replica**, and make sure nothing else is running with the
   same token: two copies polling the same bot fight each other (`409 Conflict`).

To change the fixed-price list later: edit `FIXED_PRICE_ITEMS` in Railway (add or remove a
line) and click **Deploy**. No GitHub change needed.

## Run locally

```bash
py -m venv .venv
```

```bash
.venv\Scripts\python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, fill in `BOT_TOKEN` (and optionally the other variables), then:

```bash
.venv\Scripts\python bot.py
```

Convert files without Telegram:

```bash
.venv\Scripts\python invoice.py out "C:\path\to\invoice_160776.pdf"
```

Fonts: `fonts/DejaVuSerifCondensed-Bold.ttf` is from the official DejaVu release
(free license in `fonts/DEJAVU-LICENSE`), the same typeface the originals use.
