"""Telegram bot: when an original CAMMED invoice PDF is posted in the group,
reply with the 2-page discounted invoice."""

import io
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from invoice import InvoiceError, NotAnInvoice, generate

load_dotenv()
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

# Optional comma-separated list of chat ids the bot will answer in. Empty = any chat.
ALLOWED_CHATS = {int(c) for c in os.getenv("ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if c}


async def on_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat_id = update.effective_chat.id
    if ALLOWED_CHATS and chat_id not in ALLOWED_CHATS:
        log.info("Ignoring PDF from chat %s (not in ALLOWED_CHAT_IDS)", chat_id)
        return

    doc = msg.document
    tg_file = await doc.get_file()
    data = bytes(await tg_file.download_as_bytearray())

    try:
        filename, out = generate(data)
    except NotAnInvoice:
        log.info("Skipping %s: not an original invoice", doc.file_name)
        return
    except InvoiceError as e:
        log.warning("Could not process %s: %s", doc.file_name, e)
        await msg.reply_text(f"⚠️ Could not generate invoice from {doc.file_name}: {e}")
        return

    log.info("Generated %s from %s in chat %s", filename, doc.file_name, chat_id)
    await msg.reply_document(document=io.BytesIO(out), filename=filename)


def main() -> None:
    token = os.environ["BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.Document.PDF, on_pdf))
    log.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
