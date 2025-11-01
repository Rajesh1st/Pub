

import logging import os import re import json import requests from functools import wraps from dotenv import load_dotenv from telegram import ( Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat, InputMediaPhoto, ) from telegram.ext import ( Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler, )

-------------------------

Setup

-------------------------

load_dotenv()

logging.basicConfig( level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s', handlers=[ logging.FileHandler("thumbnail_bot_ptb.log"), logging.StreamHandler() ] ) logger = logging.getLogger(name)

BOT_TOKEN = os.getenv("BOT_TOKEN") DATA_FILE = 'settings.json'

Conversation states

SETTINGS_MENU, PREFIX_INPUT, SUFFIX_INPUT, LINK_INPUT, MENTION_INPUT = range(5) BUTTON_TEXT, BUTTON_URL = range(5, 7) REPLACE_INPUT, REMOVE_INPUT = range(7, 9) FORMAT_WAIT_SELECTION = range(9, 10) DUMMY = range(10, 11)

Patterns

URL_PATTERN = re.compile( r'https?://(?:[a-zA-Z0-9$-_@.&+!*'(),]|(?:%[0-9a-fA-F]{2}))+', re.IGNORECASE )

VIDEO_EXTENSIONS = ("mkv", "mp4", "avi", "mov", "webm", "m4v", "flv") USERNAME_RE = re.compile(r'@\w+') MKV_RE = re.compile(r'.mkv\S*', flags=re.IGNORECASE)

-------------------------

Persistence helpers

-------------------------

def load_store(): try: with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f) except FileNotFoundError: return {}

def save_store(data): with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)

STORE = load_store()  # structure: {str(user_id): {settings...}, 'dump_channels': {str(user_id): channel_id}} STORE.setdefault('dump_channels', {})

def user_settings(uid: int) -> dict: key = str(uid) if key not in STORE: STORE[key] = { 'caption_style': 'none', 'prefix': '', 'suffix': '', 'mention_text': '', 'link_wrap': None, 'replace_pairs': [],  # [[old, new], ...] 'remove_words': [], 'auto_remove': False, 'button': None,  # {'text': '', 'url': ''} } save_store(STORE) return STORE[key]

def save_user_settings(uid: int, data: dict): STORE[str(uid)] = data save_store(STORE)

-------------------------

Utility functions

-------------------------

def insert_suffix_before_extension(filename: str, suffix_text: str) -> str: if not suffix_text: return filename m = re.search(r'.([A-Za-z0-9]{1,5})$', filename) if m: ext = m.group(1) if ext.lower() in VIDEO_EXTENSIONS: base = filename[:m.start()] return f"{base} {suffix_text}.{ext}" return f"{filename} {suffix_text}"

def escape_html(text: str) -> str: return ( text.replace("&", "&") .replace("<", "<") .replace(">", ">") )

def apply_style_to_text(text: str, style: str) -> str: if not text: return text # We'll output HTML formatting (telegram parse_mode='HTML') if style == "blockquote": return f"<blockquote>{escape_html(text)}</blockquote>" if style == "pre": return f"<pre>{escape_html(text)}</pre>" if style == "bold": return f"<b>{escape_html(text)}</b>" if style == "italic": return f"<i>{escape_html(text)}</i>" if style == "monospace": return f"<code>{escape_html(text)}</code>" if style == "underline": return f"<u>{escape_html(text)}</u>" if style == "strikethrough": return f"<s>{escape_html(text)}</s>" if style == "spoiler": return f"<tg-spoiler>{escape_html(text)}</tg-spoiler>" return escape_html(text)

def apply_replacements(text: str, replace_pairs: list) -> str: for old, new in replace_pairs: if not old: continue pattern = re.compile(re.escape(old), flags=re.IGNORECASE) text = pattern.sub(new, text) return text

def remove_words_from_text(text: str, remove_words: list) -> str: for w in remove_words: if not w: continue pattern = re.compile(re.escape(w), flags=re.IGNORECASE) text = pattern.sub('', text) text = re.sub(r'\s{2,}', ' ', text).strip() return text

def auto_clean_text(text: str) -> str: text = URL_PATTERN.sub('', text) text = USERNAME_RE.sub('', text) text = MKV_RE.sub('', text) text = re.sub(r'\s{2,}', ' ', text).strip() return text

def build_final_caption(original_caption: str, settings: dict) -> str: caption = original_caption or '' caption = apply_replacements(caption, settings.get('replace_pairs', [])) caption = remove_words_from_text(caption, settings.get('remove_words', [])) if settings.get('auto_remove'): caption = auto_clean_text(caption) prefix = settings.get('prefix') or '' suffix = settings.get('suffix') or '' if prefix: caption = prefix + ' ' + caption if caption else prefix if suffix: caption = (caption + ' ' + suffix) if caption else suffix if settings.get('mention_text'): caption += '\n\n' + settings.get('mention_text') return caption.strip()

decorator to ensure store loaded for user

def with_settings(func): @wraps(func) async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs): uid = update.effective_user.id user_settings(uid)  # ensure exist return await func(update, context, *args, **kwargs) return wrapper

-------------------------

Settings UI

-------------------------

def build_settings_page(user_data: dict, page: int = 1): caption_style = user_data.get("caption_style", "none") prefix = user_data.get("prefix", "") suffix = user_data.get("suffix", "") mention_text = user_data.get("mention_text", "") link_wrap = user_data.get("link_wrap", None)

if page == 1:
    text = f"""

⚙️ <b>Settings — Page 1 / 3</b>

<b>Current style:</b> <code>{caption_style}</code> <b>Prefix:</b> <code>{prefix or '-'}</code> <b>Suffix:</b> <code>{suffix or '-'}</code> <b>Link wrap:</b> <code>{link_wrap or '-'}</code> <b>Mention text:</b> <code>{mention_text or '-'}</code>

<b>Choose a basic caption style:</b> """ keyboard = [ [InlineKeyboardButton("𝐁𝐨𝐥𝐝", callback_data="style:bold"), InlineKeyboardButton("𝘐𝘵𝘢𝘭𝘪𝘤", callback_data="style:italic")], [InlineKeyboardButton("𝙼𝚘𝚗𝚘𝚜𝚙𝚊𝚌𝚎", callback_data="style:monospace"), InlineKeyboardButton("Underline", callback_data="style:underline")], [InlineKeyboardButton("Strikethrough", callback_data="style:strikethrough"), InlineKeyboardButton("Spoiler", callback_data="style:spoiler")], [InlineKeyboardButton("Next ➡️", callback_data="nav:page2"), InlineKeyboardButton("🗑 Clear Style", callback_data="style:none")], [InlineKeyboardButton("✅ Done", callback_data="style:done")] ] return text, InlineKeyboardMarkup(keyboard)

elif page == 2:
    text = """

⚙️ <b>Settings — Page 2 / 3</b>

<b>Extra formats:</b> """ keyboard = [ [InlineKeyboardButton("❝ Blockquote", callback_data="style:blockquote"), InlineKeyboardButton("⤷ Pre (code block)", callback_data="style:pre")], [InlineKeyboardButton("⬅️ Back", callback_data="nav:page1"), InlineKeyboardButton("Next ➡️", callback_data="nav:page3")], [InlineKeyboardButton("✅ Done", callback_data="style:done")] ] return text, InlineKeyboardMarkup(keyboard)

else:
    text = f"""

⚙️ <b>Settings — Page 3 / 3</b>

<b>Prefix:</b> <code>{prefix or '-'}</code> <b>Suffix:</b> <code>{suffix or '-'}</code> <b>Link wrap:</b> <code>{link_wrap or '-'}</code> <b>Mention text:</b> <code>{mention_text or '-'}</code> """ keyboard = [ [InlineKeyboardButton("Set Prefix", callback_data="set:prefix"), InlineKeyboardButton("Set Suffix", callback_data="set:suffix")], [InlineKeyboardButton("Set Link Wrap", callback_data="set:link"), InlineKeyboardButton("Set Mention", callback_data="set:mention")], [InlineKeyboardButton("🗑 Clear Prefix", callback_data="clear:prefix"), InlineKeyboardButton("🗑 Clear Suffix", callback_data="clear:suffix")], [InlineKeyboardButton("🗑 Clear Link", callback_data="clear:link"), InlineKeyboardButton("🗑 Clear Mention", callback_data="clear:mention")], [InlineKeyboardButton("🧹 Clear All Settings", callback_data="confirm:clear_all")], [InlineKeyboardButton("🪄 Preview Caption", callback_data="action:preview")], [InlineKeyboardButton("⬅️ Back", callback_data="nav:page2"), InlineKeyboardButton("✅ Done", callback_data="style:done")] ] return text, InlineKeyboardMarkup(keyboard)

-------------------------

Commands

-------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE): text = """ 🤖 <b>Thumbnail Cover Changer Bot</b>

I can change video thumbnails/covers and style captions.

<b>Commands:</b> /start - Show help /settings - Configure caption styles, prefix/suffix/link /thumb - View saved thumbnail /clear - Clear thumbnail /clear_prefix - Remove saved prefix /clear_suffix - Remove saved suffix /clear_link - Remove link wrapping /clear_mention - Remove mention text /clear_everything - 🧹 Clear all saved settings at once /set_button - Configure button to add under videos /replace_words - Set replace pairs: old - new, old - new /remove_words - Set words to remove: hd, 2025, Hindi /toggle_auto_remove - Toggle automatic removal of links/usernames/.mkv patterns /set_dump - Set dump channel by forwarding a message from your channel /format - Reply to a message and run /format to open formatting toggles (Bold/Italic) /change_thumbnail - Reply to a media and run to replace thumbnail (simulation) """ await update.message.reply_text(text, parse_mode='HTML')

@with_settings async def clear_prefix_command(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id s = user_settings(uid) s['prefix'] = '' save_user_settings(uid, s) await update.message.reply_text("✅ Prefix cleared!")

@with_settings async def clear_suffix_command(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id s = user_settings(uid) s['suffix'] = '' save_user_settings(uid, s) await update.message.reply_text("✅ Suffix cleared!")

@with_settings async def clear_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id s = user_settings(uid) s['link_wrap'] = None save_user_settings(uid, s) await update.message.reply_text("✅ Link wrap cleared!")

@with_settings async def clear_mention_command(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id s = user_settings(uid) s['mention_text'] = '' save_user_settings(uid, s) await update.message.reply_text("✅ Mention text cleared!")

async def clear_everything_command(update: Update, context: ContextTypes.DEFAULT_TYPE): keyboard = [ [InlineKeyboardButton("✅ Yes, Clear All", callback_data="clear:all_cmd"), InlineKeyboardButton("❌ No, Cancel", callback_data="cancel:clear_all_cmd")] ] await update.message.reply_text( "⚠️ Are you sure you want to clear ALL your saved settings?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML' )

-------------------------

Settings Conversation

-------------------------

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id s = user_settings(uid) text, markup = build_settings_page(s, page=1) await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML') return SETTINGS_MENU

async def settings_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() data = query.data or "" uid = query.from_user.id s = user_settings(uid)

# Navigation
if data.startswith("nav:"):
    page = int(data.split(':', 1)[1].replace('page', ''))
    text, markup = build_settings_page(s, page=page)
    await query.edit_message_text(text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU

# Style
if data.startswith("style:"):
    style = data.split(":", 1)[1]
    if style == "done":
        await query.edit_message_text("✅ <b>Settings saved!</b>", parse_mode='HTML')
        save_user_settings(uid, s)
        return ConversationHandler.END
    if style == 'none':
        s['caption_style'] = 'none'
    else:
        s['caption_style'] = style
    save_user_settings(uid, s)
    text, markup = build_settings_page(s, page=1)
    await query.edit_message_text(f"✅ Style set to <code>{style}</code>\n\n{text}",
                                  reply_markup=markup, parse_mode='HTML')
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
    if which == 'prefix':
        return PREFIX_INPUT
    if which == 'suffix':
        return SUFFIX_INPUT
    if which == 'link':
        return LINK_INPUT
    if which == 'mention':
        return MENTION_INPUT

# Clear prefix
if data == "clear:prefix":
    s['prefix'] = ''
    save_user_settings(uid, s)
    text, markup = build_settings_page(s, page=3)
    await query.edit_message_text("✅ Prefix cleared!\n\n" + text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU

# Clear suffix
if data == "clear:suffix":
    s['suffix'] = ''
    save_user_settings(uid, s)
    text, markup = build_settings_page(s, page=3)
    await query.edit_message_text("✅ Suffix cleared!\n\n" + text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU

# Clear link
if data == "clear:link":
    s['link_wrap'] = None
    save_user_settings(uid, s)
    text, markup = build_settings_page(s, page=3)
    await query.edit_message_text("✅ Link wrap cleared!\n\n" + text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU

# Clear mention
if data == "clear:mention":
    s['mention_text'] = ''
    save_user_settings(uid, s)
    text, markup = build_settings_page(s, page=3)
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
    for key in ["prefix", "suffix", "mention_text", "link_wrap", "caption_style", 'replace_pairs', 'remove_words', 'auto_remove', 'button']:
        s.pop(key, None)
    save_user_settings(uid, s)
    text, markup = build_settings_page(s, page=3)
    await query.edit_message_text("🧹 All settings cleared!\n\n" + text,
                                  reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU

# Cancel clear all (button version)
if data == "cancel:clear_all":
    text, markup = build_settings_page(s, page=3)
    await query.edit_message_text("❌ Clear all cancelled.\n\n" + text,
                                  reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU

# Clear all confirmed (command version)
if data == "clear:all_cmd":
    for key in ["prefix", "suffix", "mention_text", "link_wrap", "caption_style", 'replace_pairs', 'remove_words', 'auto_remove', 'button']:
        s.pop(key, None)
    save_user_settings(uid, s)
    await query.edit_message_text("🧹 All settings cleared successfully!", parse_mode='HTML')
    return SETTINGS_MENU

# Cancel clear all (command version)
if data == "cancel:clear_all_cmd":
    await query.edit_message_text("❌ Clear all cancelled.", parse_mode='HTML')
    return SETTINGS_MENU

# Preview
if data.startswith("action:preview"):
    sample = "🔥 The Summer Hikaru Died S01 Ep 07 - 12 [Hindi-English-Japanese] 1080p HEVC 10bit WEB-DL ESub ~ Aᴍɪᴛ ~ [TW4ALL].mkv"
    prefix = s.get('prefix', '')
    suffix = s.get('suffix', '')
    style = s.get('caption_style', 'none')
    mention_text = s.get('mention_text', '')
    link_wrap = s.get('link_wrap')

    composed = f"{prefix} {sample}".strip()
    composed = insert_suffix_before_extension(composed, suffix)
    if mention_text:
        composed += f"\n\n{mention_text}"
    styled = apply_style_to_text(composed, style)
    if link_wrap:
        styled = f'<a href="{escape_html(link_wrap)}">{styled}</a>'

    await query.message.reply_text(f"🪄 <b>Preview:</b>\n{styled}", parse_mode='HTML')
    return SETTINGS_MENU

return SETTINGS_MENU

-------------------------

Input Handlers

-------------------------

async def prefix_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id s = user_settings(uid) s['prefix'] = update.message.text.strip() save_user_settings(uid, s) await update.message.reply_text("✅ Prefix updated.") text, markup = build_settings_page(s, page=3) await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML') return SETTINGS_MENU

async def suffix_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id s = user_settings(uid) s['suffix'] = update.message.text.strip() save_user_settings(uid, s) await update.message.reply_text("✅ Suffix updated.") text, markup = build_settings_page(s, page=3) await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML') return SETTINGS_MENU

async def link_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id s = user_settings(uid) s['link_wrap'] = update.message.text.strip() save_user_settings(uid, s) await update.message.reply_text("✅ Link wrap URL saved!") text, markup = build_settings_page(s, page=3) await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML') return SETTINGS_MENU

async def mention_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id s = user_settings(uid) s['mention_text'] = update.message.text.strip() save_user_settings(uid, s) await update.message.reply_text("✅ Mention text saved!") text, markup = build_settings_page(s, page=3) await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML') return SETTINGS_MENU

async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("❌ Settings menu closed.") return ConversationHandler.END

-------------------------

Replace / Remove / Toggle commands

-------------------------

@with_settings async def replace_words_command(update: Update, context: ContextTypes.DEFAULT_TYPE): # Example: /replace_words old - new, foo - bar uid = update.effective_user.id text = ' '.join(context.args) if context.args else '' if not text: await update.message.reply_text("Send pairs like: old - new, old - new") return pairs = [] parts = [p.strip() for p in text.split(',') if p.strip()] for p in parts: if '-' in p: left, _, right = p.partition('-') pairs.append([left.strip(), right.strip()]) s = user_settings(uid) s['replace_pairs'] = pairs save_user_settings(uid, s) await update.message.reply_text(f"✅ Replace pairs saved: {pairs}")

@with_settings async def remove_words_command(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id text = ' '.join(context.args) if context.args else '' if not text: await update.message.reply_text("Send comma-separated words to remove: hd, 2025, Hindi") return arr = [p.strip() for p in ','.join(context.args).split(',') if p.strip()] s = user_settings(uid) s['remove_words'] = arr save_user_settings(uid, s) await update.message.reply_text(f"✅ Remove words saved: {arr}")

@with_settings async def toggle_auto_remove(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id s = user_settings(uid) s['auto_remove'] = not s.get('auto_remove', False) save_user_settings(uid, s) await update.message.reply_text(f"✅ Auto remove set to: {s['auto_remove']}")

-------------------------

Button & Dump channel flows

-------------------------

@with_settings async def set_button_command(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("Send BUTTON TEXT (what will appear on the button)") return BUTTON_TEXT

async def button_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): context.user_data['_button_text'] = update.message.text.strip() await update.message.reply_text("Now send BUTTON URL (eg. https://example.com)") return BUTTON_URL

async def button_url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id text = context.user_data.pop('_button_text', 'Visit') url = update.message.text.strip() s = user_settings(uid) s['button'] = {'text': text, 'url': url} save_user_settings(uid, s) await update.message.reply_text(f"✅ Button saved: {s['button']}") return ConversationHandler.END

async def set_dump_command(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text( "To set dump channel: 1) Add this bot to your channel as admin.\n2) After adding, forward any message from that channel to me. I will detect and store the channel id." )

async def handle_forwarded_from_channel(update: Update, context: ContextTypes.DEFAULT_TYPE): # When user forwards a message from channel, store mapping fchat = update.message.forward_from_chat if not fchat or fchat.type != 'channel': return uid = update.effective_user.id STORE['dump_channels'][str(uid)] = fchat.id save_store(STORE) await update.message.reply_text(f"✅ Dump channel set to: {fchat.title} (id: {fchat.id})")

-------------------------

Format flow (multi-select bold+italic)

-------------------------

@with_settings async def format_command(update: Update, context: ContextTypes.DEFAULT_TYPE): # User must reply to a text message if not update.message.reply_to_message or not update.message.reply_to_message.text: await update.message.reply_text('Please reply to the text message you want to format using /format') return target = update.message.reply_to_message uid = update.effective_user.id # store temporary state in context.user_data context.user_data.setdefault('format_state', {}) context.user_data['format_state'][str(target.message_id)] = {'bold': False, 'italic': False, 'target_chat_id': target.chat_id} markup = InlineKeyboardMarkup([ [InlineKeyboardButton('Bold', callback_data=f'fmt|{uid}|{target.message_id}|bold'), InlineKeyboardButton('Italic', callback_data=f'fmt|{uid}|{target.message_id}|italic')], [InlineKeyboardButton('Apply', callback_data=f'fmt|{uid}|{target.message_id}|apply'), InlineKeyboardButton('Cancel', callback_data=f'fmt|{uid}|{target.message_id}|cancel')] ]) await update.message.reply_text('Formatting toggles: Tap to toggle. Press Apply when done.', reply_markup=markup)

async def callback_format(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() parts = query.data.split('|') if len(parts) != 4: await query.edit_message_text('Invalid format control') return _, uid_s, target_id_s, action = parts uid = int(uid_s) target_id = int(target_id_s) if query.from_user.id != uid: await query.answer('This control is not for you') return state_map = context.user_data.get('format_state', {}) state = state_map.get(str(target_id)) if not state: await query.edit_message_text('Formatting session expired or cancelled') return if action in ('bold', 'italic'): state[action] = not state.get(action, False) await query.answer(f'{action} set to {state[action]}') return if action == 'cancel': state_map.pop(str(target_id), None) await query.edit_message_text('Formatting cancelled') return if action == 'apply': await query.answer('Send the text to format, or send ALL to format whole message') # we will wait for user message next and handle in format_selection_handler context.user_data['_format_target_id'] = target_id return

async def format_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): if '_format_target_id' not in context.user_data: return target_id = context.user_data.pop('_format_target_id') state = context.user_data.get('format_state', {}).pop(str(target_id), None) if not state: await update.message.reply_text('Formatting session expired or cancelled') return target_chat_id = state.get('target_chat_id', update.message.chat_id) # try to fetch original message try: orig_msg = await context.bot.get_chat(target_chat_id) # PTB does not provide get_message; we assume the message exists in the same chat where user replied earlier # Simpler approach: user had replied to message in same chat; we can use message history if necessary — but we'll assume same chat orig = update.message.reply_to_message  # best-effort: the message we replied when starting /format if not orig or not orig.text: await update.message.reply_text('Could not fetch original message to apply formatting') return except Exception: orig = update.message.reply_to_message selection = update.message.text.strip() new_text = orig.text def wrap_text(t): txt = escape_html(t) if state.get('bold'): txt = f"<b>{txt}</b>" if state.get('italic'): txt = f"<i>{txt}</i>" return txt if selection.upper() == 'ALL': new_text = wrap_text(orig.text) else: formatted = wrap_text(selection) # replace all occurrences (case-sensitive) for clarity new_text = escape_html(orig.text).replace(escape_html(selection), formatted) # send preview await update.message.reply_text(f'Preview of formatted text (HTML):\n{new_text}', parse_mode='HTML')

-------------------------

Thumbnail / Video Handlers

-------------------------

async def view_thumb_command(update: Update, context: ContextTypes.DEFAULT_TYPE): thumb_file_id = context.user_data.get("thumb_file_id") if thumb_file_id: await update.message.reply_photo(thumb_file_id, caption="📷 Your current thumbnail", parse_mode='HTML') else: await update.message.reply_text("📷 No thumbnail saved.")

async def clear_thumb_command(update: Update, context: ContextTypes.DEFAULT_TYPE): context.user_data.pop("thumb_file_id", None) await update.message.reply_text("✅ Thumbnail cleared.")

async def save_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE): # Save photo sent as thumbnail if not update.message.photo: return context.user_data["thumb_file_id"] = update.message.photo[-1].file_id await update.message.reply_text("✅ Thumbnail saved!")

async def handle_url_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE): url = update.message.text.strip() if URL_PATTERN.match(url): try: res = requests.get(url, timeout=10) res.raise_for_status() msg = await update.message.reply_photo(photo=res.content, caption="🖼️ Image fetched.") context.user_data["thumb_file_id"] = msg.photo[-1].file_id await update.message.reply_text("✅ Thumbnail saved from URL!") except Exception: await update.message.reply_text("❌ Failed to download image.")

async def send_video(update: Update, context: ContextTypes.DEFAULT_TYPE): # Handles incoming video or document video if not (update.message.video or (update.message.document and update.message.document.mime_type and 'video' in (update.message.document.mime_type))): await update.message.reply_text('Send a video file or a document (video).') return

thumb = context.user_data.get("thumb_file_id")
if not thumb:
    await update.message.reply_text("⚠️ Please send a thumbnail first.")
    return

# get file id
video_file_id = update.message.video.file_id if update.message.video else update.message.document.file_id
uid = update.effective_user.id
s = user_settings(uid)

caption = update.message.caption or ""
composed = f"{s.get('prefix','')} {caption}".strip()
composed = insert_suffix_before_extension(composed, s.get('suffix',''))
final_caption = build_final_caption(composed, s)
styled_caption = apply_style_to_text(final_caption, s.get('caption_style','none'))
if s.get('link_wrap'):
    styled_caption = f'<a href="{escape_html(s.get("link_wrap"))}">{styled_caption}</a>'

# Button
markup = None
if s.get('button'):
    b = s['button']
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(b['text'], url=b['url'])]])

# Send video with cover (note: PTB's send_video doesn't accept "cover" param) — libraries vary. We'll attempt with send_video and thumb as thumbnail via thumb parameter if supported.
try:
    await context.bot.send_video(
        chat_id=update.message.chat_id,
        video=video_file_id,
        caption=styled_caption or None,
        parse_mode='HTML',
        thumb=thumb,
        reply_markup=markup
    )
except TypeError:
    # fallback if thumb param not supported in this PTB version
    await context.bot.send_video(
        chat_id=update.message.chat_id,
        video=video_file_id,
        caption=styled_caption or None,
        parse_mode='HTML',
        reply_markup=markup
    )

# If dump channel set for this user, forward original and send processed caption there
dump_map = STORE.get('dump_channels', {})
dump_id = dump_map.get(str(uid))
if dump_id:
    try:
        # forward original
        await context.bot.forward_message(chat_id=dump_id, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
        # send a note with processed caption and button
        await context.bot.send_message(chat_id=dump_id, text=f'Processed caption for forwarded media:\n{styled_caption}', parse_mode='HTML', reply_markup=markup)
    except Exception as e:
        logger.exception('Failed to send to dump channel: %s', e)

-------------------------

Change thumbnail flow

-------------------------

@with_settings async def change_thumbnail_command(update: Update, context: ContextTypes.DEFAULT_TYPE): if not update.message.reply_to_message or not (update.message.reply_to_message.video or update.message.reply_to_message.document): await update.message.reply_text('Reply to the media message for which you want to change the thumbnail, then run /change_thumbnail') return context.user_data['_change_target'] = { 'chat_id': update.message.reply_to_message.chat_id, 'message_id': update.message.reply_to_message.message_id, } await update.message.reply_text('Now send the NEW THUMBNAIL image as a photo reply to this chat.')

async def handle_new_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE): if not update.message.photo: return if '_change_target' not in context.user_data: return target = context.user_data.pop('_change_target') # Save as user's thumbnail and simulate sending processed result to dump channel context.user_data['thumb_file_id'] = update.message.photo[-1].file_id await update.message.reply_text('✅ New thumbnail saved and applied (simulation).')

uid = update.effective_user.id
dump_map = STORE.get('dump_channels', {})
dump_id = dump_map.get(str(uid))
s = user_settings(uid)
# Build caption for the target (if we can find it) — best-effort: not fetching original; just notify
final_caption = '(thumbnail updated)'
if dump_id:
    try:
        await context.bot.send_photo(chat_id=dump_id, photo=update.message.photo[-1].file_id, caption=f'New thumbnail for media (caption applied):\n{final_caption}')
        await update.message.reply_text('New thumbnail sent to dump channel.')
    except Exception as e:
        logger.exception('Failed to send thumbnail to dump channel: %s', e)
        await update.message.reply_text('Failed to send thumbnail to dump channel.')

-------------------------

Handlers wiring and main

-------------------------

def main(): if not BOT_TOKEN: logger.error("BOT_TOKEN missing.") return

app = Application.builder().token(BOT_TOKEN).build()

# Settings conversation
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

# Button set conv
button_conv = ConversationHandler(
    entry_points=[CommandHandler('set_button', set_button_command)],
    states={
        BUTTON_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, button_text_handler)],
        BUTTON_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, button_url_handler)],
    },
    fallbacks=[CommandHandler('cancel', cancel_settings)],
    allow_reentry=True,
)

app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("thumb", view_thumb_command))
app.add_handler(CommandHandler("clear", clear_thumb_command))
app.add_handler(settings_conv)
app.add_handler(button_conv)
app.add_handler(CommandHandler("clear_prefix", clear_prefix_command))
app.add_handler(CommandHandler("clear_suffix", clear_suffix_command))
app.add_handler(CommandHandler("clear_link", clear_link_command))
app.add_handler(CommandHandler("clear_mention", clear_mention_command))
app.add_handler(CommandHandler("clear_everything", clear_everything_command))

app.add_handler(CommandHandler('replace_words', replace_words_command))
app.add_handler(CommandHandler('remove_words', remove_words_command))
app.add_handler(CommandHandler('toggle_auto_remove', toggle_auto_remove))
app.add_handler(CommandHandler('set_dump', set_dump_command))
app.add_handler(CommandHandler('format', format_command))
app.add_handler(CallbackQueryHandler(callback_format, pattern=r'^fmt\|'))
app.add_handler(CommandHandler('change_thumbnail', change_thumbnail_command))

# Forwarded message handler for dump channel setting
app.add_handler(MessageHandler(filters.ALL & filters.FORWARDED, handle_forwarded_from_channel))

# Media and thumbnail handlers
app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, save_thumb))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_thumb))
# video/document handler
app.add_handler(MessageHandler((filters.VIDEO | (filters.Document.EXTENSION | filters.Document.MIME_TYPE)), send_video))

# Format selection text after pressing apply — we rely on user sending message
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, format_selection_handler))

# New thumbnail after /change_thumbnail
app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_new_thumbnail))

logger.info("🚀 Bot is running...")
app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if name == "main": try: main() except KeyboardInterrupt: logger.info("Bot stopped by user") except Exception as e: logger.error(f"Failed to start bot: {e}")

