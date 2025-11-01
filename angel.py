import logging
import os
import re
import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)

# -------------------------
# Setup
# -------------------------
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("thumbnail_bot_ptb.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

SETTINGS_MENU, PREFIX_INPUT, SUFFIX_INPUT, LINK_INPUT, MENTION_INPUT = range(5)

URL_PATTERN = re.compile(
    r'https?://(?:[a-zA-Z0-9$-_@.&+!*\'(),]|(?:%[0-9a-fA-F]{2}))+'
    r'\.(?:jpg|jpeg|png|webp|bmp)(?:\?.*)?$',
    re.IGNORECASE
)

VIDEO_EXTENSIONS = ("mkv", "mp4", "avi", "mov", "webm", "m4v", "flv")


# -------------------------
# Helper functions
# -------------------------
def insert_suffix_before_extension(filename: str, suffix_text: str) -> str:
    if not suffix_text:
        return filename
    m = re.search(r'\.([A-Za-z0-9]{1,5})$', filename)
    if m:
        ext = m.group(1)
        if ext.lower() in VIDEO_EXTENSIONS:
            base = filename[:m.start()]
            return f"{base} {suffix_text}.{ext}"
    return f"{filename} {suffix_text}"


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def apply_styles_to_text(text: str, styles: list[str]) -> str:
    """Apply multiple HTML styles in order to a given text."""
    if not text or not styles:
        return escape_html(text)
    styled = escape_html(text)
    for style in styles:
        if style == "blockquote":
            styled = f"<blockquote>{styled}</blockquote>"
        elif style == "pre":
            styled = f"<pre>{styled}</pre>"
        elif style == "bold":
            styled = f"<b>{styled}</b>"
        elif style == "italic":
            styled = f"<i>{styled}</i>"
        elif style == "monospace":
            styled = f"<code>{styled}</code>"
        elif style == "underline":
            styled = f"<u>{styled}</u>"
        elif style == "strikethrough":
            styled = f"<s>{styled}</s>"
        elif style == "spoiler":
            styled = f"<tg-spoiler>{styled}</tg-spoiler>"
    return styled   

# -------------------------
# Build Settings Pages
# -------------------------
def build_settings_page(user_data: dict, page: int = 1) -> (str, InlineKeyboardMarkup):
    caption_styles = user_data.get("caption_styles", [])
    style_display = ", ".join(caption_styles) if caption_styles else "none"
    prefix = user_data.get("prefix", "")
    suffix = user_data.get("suffix", "")
    mention_text = user_data.get("mention_text", "")
    link_wrap = user_data.get("link_wrap", None)

    if page == 1:
        text = f"""
⚙️ <b>Settings — Page 1 / 3</b>

<b>Current style:</b> <code>{style_display}</code>
<b>Prefix:</b> <code>{prefix or '-'}</code>
<b>Suffix:</b> <code>{suffix or '-'}</code>
<b>Link wrap:</b> <code>{link_wrap or '-'}</code>
<b>Mention text:</b> <code>{mention_text or '-'}</code>

<b>Choose a basic caption style:</b>
"""
        keyboard = [
            [InlineKeyboardButton("𝐁𝐨𝐥𝐝", callback_data="style:bold"),
             InlineKeyboardButton("𝘐𝘵𝘢𝘭𝘪𝘤", callback_data="style:italic")],
            [InlineKeyboardButton("𝙼𝚘𝚗𝚘𝚜𝚙𝚊𝚌𝚎", callback_data="style:monospace"),
             InlineKeyboardButton("Underline", callback_data="style:underline")],
            [InlineKeyboardButton("Strikethrough", callback_data="style:strikethrough"),
             InlineKeyboardButton("Spoiler", callback_data="style:spoiler")],
            [InlineKeyboardButton("Next ➡️", callback_data="nav:page2"),
             InlineKeyboardButton("🗑 Clear Style", callback_data="style:none")],
            [InlineKeyboardButton("✅ Done", callback_data="style:done")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    elif page == 2:
        text = """
⚙️ <b>Settings — Page 2 / 3</b>

<b>Extra formats:</b>
"""
        keyboard = [
            [InlineKeyboardButton("❝ Blockquote", callback_data="style:blockquote"),
             InlineKeyboardButton("⤷ Pre (code block)", callback_data="style:pre")],
            [InlineKeyboardButton("⬅️ Back", callback_data="nav:page1"),
             InlineKeyboardButton("Next ➡️", callback_data="nav:page3")],
            [InlineKeyboardButton("✅ Done", callback_data="style:done")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    else:
        text = f"""
⚙️ <b>Settings — Page 3 / 3</b>

<b>Prefix:</b> <code>{prefix or '-'}</code>
<b>Suffix:</b> <code>{suffix or '-'}</code>
<b>Link wrap:</b> <code>{link_wrap or '-'}</code>
<b>Mention text:</b> <code>{mention_text or '-'}</code>
"""
        keyboard = [
            [InlineKeyboardButton("Set Prefix", callback_data="set:prefix"),
             InlineKeyboardButton("Set Suffix", callback_data="set:suffix")],
            [InlineKeyboardButton("Set Link Wrap", callback_data="set:link"),
             InlineKeyboardButton("Set Mention", callback_data="set:mention")],
            [InlineKeyboardButton("🗑 Clear Prefix", callback_data="clear:prefix"),
             InlineKeyboardButton("🗑 Clear Suffix", callback_data="clear:suffix")],
            [InlineKeyboardButton("🗑 Clear Link", callback_data="clear:link"),
             InlineKeyboardButton("🗑 Clear Mention", callback_data="clear:mention")],
            [InlineKeyboardButton("🧹 Clear All Settings", callback_data="confirm:clear_all")],
            [InlineKeyboardButton("🪄 Preview Caption", callback_data="action:preview")],
            [InlineKeyboardButton("⬅️ Back", callback_data="nav:page2"),
             InlineKeyboardButton("✅ Done", callback_data="style:done")]
        ]
        return text, InlineKeyboardMarkup(keyboard)


# -------------------------
# Commands
# -------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🤖 <b>Thumbnail Cover Changer Bot</b>

I can change video thumbnails/covers and style captions.

<b>Commands:</b>
/start - Show help
/settings - Configure caption styles, prefix/suffix/link
/thumb - View saved thumbnail
/clear - Clear thumbnail
/clear_prefix - Remove saved prefix
/clear_suffix - Remove saved suffix
/clear_link - Remove link wrapping
/clear_mention - Remove mention text
/clear_everything - 🧹 Clear all saved settings at once
"""
    await update.message.reply_text(text, parse_mode='HTML')


async def clear_prefix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("prefix", None)
    await update.message.reply_text("✅ Prefix cleared!")


async def clear_suffix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("suffix", None)
    await update.message.reply_text("✅ Suffix cleared!")


async def clear_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("link_wrap", None)
    await update.message.reply_text("✅ Link wrap cleared!")


async def clear_mention_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("mention_text", None)
    await update.message.reply_text("✅ Mention text cleared!")


async def clear_everything_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Clear All", callback_data="clear:all_cmd"),
         InlineKeyboardButton("❌ No, Cancel", callback_data="cancel:clear_all_cmd")]
    ]
    await update.message.reply_text(
        "⚠️ Are you sure you want to clear ALL your saved settings?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


# -------------------------
# Settings Handler
# -------------------------
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    ud.setdefault('caption_style', 'none')
    ud.setdefault('prefix', '')
    ud.setdefault('suffix', '')
    ud.setdefault('mention_text', '')
    ud.setdefault('link_wrap', None)

    text, markup = build_settings_page(ud, page=1)
    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU


async def settings_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user_data = context.user_data

    # Navigation
    if data.startswith("nav:"):
        page = int(data[-1])
        text, markup = build_settings_page(user_data, page=page)
        await query.edit_message_text(text, reply_markup=markup, parse_mode='HTML')
        return SETTINGS_MENU

    # Style
    if data.startswith("style:"):
    style = data.split(":", 1)[1]
    if style == "done":
        await query.edit_message_text("✅ <b>Settings saved!</b>", parse_mode='HTML')
        return ConversationHandler.END

    # multi-style toggle logic
    caption_styles = user_data.get("caption_styles", [])
    if style in caption_styles:
        caption_styles.remove(style)
        msg = f"❌ Removed style <code>{style}</code>"
    else:
        caption_styles.append(style)
        msg = f"✅ Added style <code>{style}</code>"

    user_data["caption_styles"] = caption_styles
    text, markup = build_settings_page(user_data, page=1)
    await query.edit_message_text(f"{msg}\n\n{text}", reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU
    
    # Set inputs
    if data.startswith("set:"):
        which = data.split(":", 1)[1]
        prompts = {
            "prefix": "✏️ Send your new Prefix text.",
            "suffix": "✏️ Send your new Suffix text.",
            "link": "🔗 Send the URL to wrap your captions.",
            "mention": "💬 Send your custom Mention text (like 'Join my channel - @fjiffyuv')."
        }
        await query.edit_message_text(prompts[which])
        return {"prefix": PREFIX_INPUT, "suffix": SUFFIX_INPUT, "link": LINK_INPUT, "mention": MENTION_INPUT}[which]

    # Clear prefix
    if data == "clear:prefix":
        user_data.pop("prefix", None)
        text, markup = build_settings_page(user_data, page=3)
        await query.edit_message_text("✅ Prefix cleared!\n\n" + text, reply_markup=markup, parse_mode='HTML')
        return SETTINGS_MENU

    # Clear suffix
    if data == "clear:suffix":
        user_data.pop("suffix", None)
        text, markup = build_settings_page(user_data, page=3)
        await query.edit_message_text("✅ Suffix cleared!\n\n" + text, reply_markup=markup, parse_mode='HTML')
        return SETTINGS_MENU

    # Clear link
    if data == "clear:link":
        user_data.pop("link_wrap", None)
        text, markup = build_settings_page(user_data, page=3)
        await query.edit_message_text("✅ Link wrap cleared!\n\n" + text, reply_markup=markup, parse_mode='HTML')
        return SETTINGS_MENU

    # Clear mention
    if data == "clear:mention":
        user_data.pop("mention_text", None)
        text, markup = build_settings_page(user_data, page=3)
        await query.edit_message_text("✅ Mention text cleared!\n\n" + text, reply_markup=markup, parse_mode='HTML')
        return SETTINGS_MENU

    # Confirm before clear all from button
    if data == "confirm:clear_all":
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Clear All", callback_data="clear:all"),
             InlineKeyboardButton("❌ No, Cancel", callback_data="cancel:clear_all")]
        ]
        await query.edit_message_text("⚠️ Are you sure you want to clear all saved settings?",
                                      reply_markup=InlineKeyboardMarkup(keyboard),
                                      parse_mode='HTML')
        return SETTINGS_MENU

    # Clear all confirmed (button version)
    if data == "clear:all":
        for key in ["prefix", "suffix", "mention_text", "link_wrap", "caption_style"]:
            user_data.pop(key, None)
        text, markup = build_settings_page(user_data, page=3)
        await query.edit_message_text("🧹 All settings cleared!\n\n" + text,
                                      reply_markup=markup, parse_mode='HTML')
        return SETTINGS_MENU

    # Cancel clear all (button version)
    if data == "cancel:clear_all":
        text, markup = build_settings_page(user_data, page=3)
        await query.edit_message_text("❌ Clear all cancelled.\n\n" + text,
                                      reply_markup=markup, parse_mode='HTML')
        return SETTINGS_MENU

    # Clear all confirmed (command version)
    if data == "clear:all_cmd":
        for key in ["prefix", "suffix", "mention_text", "link_wrap", "caption_style"]:
            user_data.pop(key, None)
        await query.edit_message_text("🧹 All settings cleared successfully!",
                                      parse_mode='HTML')
        return SETTINGS_MENU

    # Cancel clear all (command version)
    if data == "cancel:clear_all_cmd":
        await query.edit_message_text("❌ Clear all cancelled.", parse_mode='HTML')
        return SETTINGS_MENU

    # Preview
    if data.startswith("action:preview"):
        sample = "The Summer Hikaru Died S01 Ep 07 - 12 [Hindi-English-Japanese] 1080p HEVC 10bit WEB-DL ESub ~ Aᴍɪᴛ ~ [TW4ALL].mkv"
        prefix = user_data.get('prefix', '')
        suffix = user_data.get('suffix', '')
        styles = user_data.get('caption_styles', [])
        mention_text = user_data.get('mention_text', '')
        link_wrap = user_data.get('link_wrap')

        composed = f"{prefix} {sample}".strip()
        composed = insert_suffix_before_extension(composed, suffix)
        if mention_text:
            composed += f"\n\n{mention_text}"
        styled = apply_style_to_text(composed, styles)
        if link_wrap:
            styled = f'<a href="{escape_html(link_wrap)}">{styled}</a>'

        await query.message.reply_text(f"🪄 <b>Preview:</b>\n{styled}", parse_mode='HTML')
        return SETTINGS_MENU

    return SETTINGS_MENU


# -------------------------
# Input Handlers
# -------------------------
async def prefix_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['prefix'] = update.message.text.strip()
    await update.message.reply_text("✅ Prefix updated.")
    text, markup = build_settings_page(context.user_data, page=3)
    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU


async def suffix_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['suffix'] = update.message.text.strip()
    await update.message.reply_text("✅ Suffix updated.")
    text, markup = build_settings_page(context.user_data, page=3)
    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU


async def link_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['link_wrap'] = update.message.text.strip()
    await update.message.reply_text("✅ Link wrap URL saved!")
    text, markup = build_settings_page(context.user_data, page=3)
    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU


async def mention_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mention_text'] = update.message.text.strip()
    await update.message.reply_text("✅ Mention text saved!")
    text, markup = build_settings_page(context.user_data, page=3)
    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU


async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Settings menu closed.")
    return ConversationHandler.END


# -------------------------
# Thumbnail / Video Handlers
# -------------------------
async def view_thumb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thumb_file_id = context.user_data.get("thumb_file_id")
    if thumb_file_id:
        await update.message.reply_photo(thumb_file_id, caption="📷 Your current thumbnail", parse_mode='HTML')
    else:
        await update.message.reply_text("📷 No thumbnail saved.")


async def clear_thumb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("thumb_file_id", None)
    await update.message.reply_text("✅ Thumbnail cleared.")


async def save_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["thumb_file_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("✅ Thumbnail saved!")


async def handle_url_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if URL_PATTERN.match(url):
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            msg = await update.message.reply_photo(photo=res.content, caption="🖼️ Image fetched.")
            context.user_data["thumb_file_id"] = msg.photo[-1].file_id
            await update.message.reply_text("✅ Thumbnail saved from URL!")
        except Exception:
            await update.message.reply_text("❌ Failed to download image.")


async def send_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thumb = context.user_data.get("thumb_file_id")
    if not thumb:
        await update.message.reply_text("⚠️ Please send a thumbnail first.")
        return

    video_file_id = update.message.video.file_id if update.message.video else update.message.document.file_id
    ud = context.user_data
    prefix, suffix = ud.get('prefix', ''), ud.get('suffix', '')
    caption_style = ud.get('caption_style', 'none')
    mention_text = ud.get('mention_text', '')
    link_wrap = ud.get('link_wrap', None)

    caption = update.message.caption or ""
    composed = f"{prefix} {caption}".strip()
    composed = insert_suffix_before_extension(composed, suffix)
    if mention_text:
        composed += f"\n\n{mention_text}"

    final_caption = apply_style_to_text(composed, caption_style)
    if link_wrap:
        final_caption = f'<a href="{escape_html(link_wrap)}">{final_caption}</a>'

    await context.bot.send_video(
        chat_id=update.message.chat_id,
        video=video_file_id,
        caption=final_caption,
        cover=thumb,
        parse_mode='HTML'
    )


# -------------------------
# Main
# -------------------------
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN missing.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    settings_conv = ConversationHandler(
        entry_points=[CommandHandler("settings", settings_command)],
        states={
            SETTINGS_MENU: [CallbackQueryHandler(settings_button_handler)],
            PREFIX_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, prefix_input_handler)],
            SUFFIX_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, suffix_input_handler)],
            LINK_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, link_input_handler)],
            MENTION_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, mention_input_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel_settings)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("thumb", view_thumb_command))
    app.add_handler(CommandHandler("clear", clear_thumb_command))
    app.add_handler(settings_conv)
    app.add_handler(CommandHandler("clear_prefix", clear_prefix_command))
    app.add_handler(CommandHandler("clear_suffix", clear_suffix_command))
    app.add_handler(CommandHandler("clear_link", clear_link_command))
    app.add_handler(CommandHandler("clear_mention", clear_mention_command))
    app.add_handler(CommandHandler("clear_everything", clear_everything_command))

    app.add_handler(MessageHandler(filters.PHOTO, save_thumb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_thumb))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, send_video))

    logger.info("🚀 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
