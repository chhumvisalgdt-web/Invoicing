"""Telegram bot: when an original CAMMED invoice PDF is posted in the group,
reply with the 2-page discounted invoice."""

import io
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, TypeHandler, filters

from invoice import InvoiceError, NotAnInvoice, fixed_items, fixed_items_source, generate

load_dotenv()
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

# Optional comma-separated list of chat ids the bot will answer in. Empty = any chat.
ALLOWED_CHATS = {int(c) for c in os.getenv("ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if c}

# Some apps send PDFs as a generic file type, so also accept them by file name.
PDF_FILES = (filters.Document.PDF | filters.Document.FileExtension("pdf")) & ~filters.UpdateType.EDITED


async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """One log line for everything the bot receives (never the message text),
    so the log shows whether Telegram delivers the group's messages at all."""
    chat, msg = update.effective_chat, update.effective_message
    where = f"chat {chat.id} ({chat.type}{': ' + chat.title if chat.title else ''})" if chat else "no chat"
    if msg and msg.document:
        what = f"file {msg.document.file_name!r} ({msg.document.mime_type})"
    elif msg:
        what = "message"
    else:
        what = "update"
    log.info("Received %s in %s", what, where)


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "✅ Bot is running. Send an original CAMMED invoice PDF and I'll reply with the discounted invoice."
    )


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
    except NotAnInvoice as e:
        log.info("Skipping %s: not an original invoice (%s)", doc.file_name, e)
        return
    except InvoiceError as e:
        log.warning("Could not process %s: %s", doc.file_name, e)
        await msg.reply_text(f"⚠️ Could not generate invoice from {doc.file_name}: {e}")
        return

    log.info("Generated %s from %s in chat %s", filename, doc.file_name, chat_id)
    await msg.reply_document(document=io.BytesIO(out), filename=filename)


async def on_startup(app: Application) -> None:
    log.info("Logged in as @%s (id %s)", app.bot.username, app.bot.id)


def build_app(token: str) -> Application:
    app = Application.builder().token(token).post_init(on_startup).build()
    app.add_handler(TypeHandler(Update, log_update), group=-1)
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(MessageHandler(PDF_FILES, on_pdf))
    return app


def main() -> None:
    token = os.environ["BOT_TOKEN"]
    log.info("%d fixed-price tests loaded from %s", len(fixed_items()), fixed_items_source())
    app = build_app(token)
    log.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
