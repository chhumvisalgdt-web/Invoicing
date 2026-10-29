# Physiocam invoice bot

When someone posts an original CAMMED LAB invoice PDF in the Telegram group, the bot
replies with the 2-page Physiocam invoice:

- **Page 1:** the original invoice, unchanged.
- **Page 2:** the same invoice with `Original Amount`, `Total for customer`,
  `Discount` (35%) and `Total` rows.

The reply file is named after the customer, e.g. `IM SOVANN PHALLA.pdf`.
Other PDFs (lab reports, already-converted invoices) are ignored silently.

Two invoice formats are read ([pdftext.py](pdftext.py)):

- CAMMED's own files (`invoice_xxxxxx.pdf`, made with mPDF), which contain normal text.
- Invoices printed from the browser with the **Adobe PDF** printer (e.g. `DOEM DOEUN 5713.pdf`).
  Their letters are drawn as shapes, so the bot recognises each shape by its fingerprint
  in [glyphs.json](glyphs.json). That table was made from the Times New Roman and Arial
  fonts with [tools/make_glyph_table.py](tools/make_glyph_table.py) (Windows only; not
  needed on Railway).

## Settings

- `DISCOUNT_RATE` in [invoice.py](invoice.py): currently 35%. Half a cent rounds to the
  even cent, like the existing discount pages (35% of $30.70 is $10.74, of $34.90 is $12.22).
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

1. Make the bot an **admin** of the group (it needs no permissions). Otherwise Telegram
   doesn't show it the files posted in the group.
   (Or in @BotFather: `/setprivacy` → **Disable**, then remove the bot and add it again.)
2. Check it is alive: send `/start` to the bot; it answers "✅ Bot is running".

## Checking the log

In Railway's deploy log:

- At start: `93 fixed-price tests loaded from ...`, `Bot started` and
  `Logged in as @username`. The username must be the bot that is in the group.
- One line for everything the bot receives, e.g.
  `Received file 'invoice_160685.pdf' (application/pdf) in chat -100... (supergroup: ...)`.
  No such line when a file is posted means Telegram isn't delivering the group's
  messages to this bot (not admin, or the token belongs to another bot).
- Then `Generated NAME.pdf ...`, or `Skipping ...: not an original invoice (reason)`,
  or a warning that is also sent to the group.

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

Rebuild `glyphs.json` (only if printed invoices start using another font):

```bash
.venv\Scripts\python -m pip install fonttools
```

```bash
.venv\Scripts\python tools\make_glyph_table.py
```

Fonts: `fonts/DejaVuSerifCondensed-Bold.ttf` is from the official DejaVu release
(free license in `fonts/DEJAVU-LICENSE`), the same typeface the originals use.
