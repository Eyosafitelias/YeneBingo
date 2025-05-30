import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "a_core.settings")
django.setup()

import asyncio
import re
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    WebAppInfo,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler,
    CallbackQueryHandler
)
from telegram.error import NetworkError, Conflict
from django.conf import settings
from django.contrib.auth.models import User
from a_telegram.models import TelegramUser
from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist
# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
VERIFY_USERNAME, GET_CONTACT = range(2)
BROADCAST_MESSAGE, BROADCAST_CONFIRM = range(2, 4)
# Message texts
WELCOME_MESSAGE = (
    "👋 *Welcome to the Bingo Telegram Bot!*\n\n"
    "In this bot, you can play Bingo and stand a chance to win *real money* 🤑\n\n"
    "🎮 Click the button below to open the Mini App and start playing!"
)


HELP_MESSAGE = (
    "🤖 Available Commands:\n\n"
    "/start - Start the bot\n"
    "/help - Show this help message\n"
    "/info - Get information about the bot\n"
    "/contact - Get contact information\n"
    "/about - Learn more about the bot\n"
    "/broadcast - (Admin only) Send message to all users"
)

def sanitize_name(name):
    if not name:
        return ""
    return re.sub(r'[^\w\s-]', '', name).strip()

@sync_to_async 
def get_user(telegram_id):
    try:
        return TelegramUser.objects.get(telegram_id=telegram_id)
    except ObjectDoesNotExist:
        return None

@sync_to_async
def create_telegram_user(telegram_id, username, first_name, last_name, phone_number):
    try:
        first_name = sanitize_name(first_name)
        last_name = sanitize_name(last_name)
        email = f"user{TelegramUser.objects.count() + 1}@example.com"
        
        if not username:
            username = f"user_{telegram_id}"
        
        original_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{original_username}_{counter}"
            counter += 1
        
        django_user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=str(telegram_id))
        
        telegram_user = TelegramUser.objects.create(
            user=django_user,
            telegram_id=telegram_id,
            username=username,
            phone_number=phone_number,
            is_admin=str(telegram_id) == getattr(settings, 'TELEGRAM_ADMIN_ID', '')
        )
        
        return telegram_user
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise Exception(f"Could not create user: {str(e)}")

@sync_to_async
def get_all_users_list():
    return list(TelegramUser.objects.all())

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = user.id
    
    telegram_user = await get_user(telegram_id)
    
    if telegram_user:
        webapp_url = f"{settings.WEBAPP_URL}?tgid={telegram_id}"
        keyboard = [
            [InlineKeyboardButton("Open Mini App", web_app={"url": webapp_url})]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Welcome back, {sanitize_name(user.first_name)}!\n\n"
            f"Username: {user.username}\n"
            f"Password: {user.id}\n\n"
            "Click below to open the Mini App:",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    
    if not user.username:
        await update.message.reply_text(
            "⚠️ You need to set a Telegram username first.\n\n"
            "Please set a username in Telegram Settings and try /start again."
        )
        return VERIFY_USERNAME
    
    keyboard = [[KeyboardButton("Share Contact", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "To complete registration, please share your contact:",
        reply_markup=reply_markup
    )
    return GET_CONTACT

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MESSAGE)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Bot Information*\n\n"
        "🎉 Welcome to *Bingo Game Bot*!\n\n"
        "🧩 This bot lets you play real-time multiplayer Bingo with your friends right inside Telegram.\n\n"
        "👥 *Features:*\n"
        "• Create or join game rooms\n"
        "• Automatically generate Bingo cards\n"
        "• Real-time updates and win detection\n"
        "• Easy and fun interface\n\n"
        "🛠️ Built using *Django*, *Django Channels*, and *Telegram Bot API*.\n\n"
        "📢 Invite your friends and start a game!\n\n"
        "_Type /start to begin or /help for commands._",
        parse_mode="Markdown"
    )


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📞 *Contact Information*\n\n"
        "Need help or want to report a bug?\n"
        "Reach out to the developer:\n\n"
        "👤 Eyosafit\n"
        "🌐 Arba Minch University\n"
        "📧 Email: eyosafit@example.com\n"
        "💬 Telegram: @your_username_here\n\n"
        "_We're here to assist you!_",
        parse_mode="Markdown"
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 *About This Bot*\n\n"
        "🎮 *Bingo Game Bot* is an interactive multiplayer Telegram game created by *Eyosafit*, "
        "a Software Engineering student at *Arba Minch University*.\n\n"
        "🧠 The project demonstrates advanced Telegram bot development using:\n"
        "• Python\n"
        "• Django & Django Channels\n"
        "• Real-time communication\n\n"
        "🎯 Built for fun and learning, this bot lets you create and join Bingo rooms, "
        "play with friends, and compete in real time — all within Telegram!\n\n"
        "_Enjoy the game and feel free to share your feedback._",
        parse_mode="Markdown"
    )

async def verify_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not user.username:
        await update.message.reply_text(
            "❌ You still don't have a username set.\n\n"
            "Please set a username in Telegram Settings and try /start again."
        )
        return VERIFY_USERNAME
    
    keyboard = [[KeyboardButton("Share Contact", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "Thank you! Now please share your contact to complete registration:",
        reply_markup=reply_markup
    )
    return GET_CONTACT

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact
    
    if contact.user_id != user.id:
        await update.message.reply_text("⚠️ Please share your own contact.")
        return GET_CONTACT
    
    await update.message.reply_text(
        "Thank you! Your contact has been received.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    try:
        telegram_user = await create_telegram_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            phone_number=contact.phone_number
        )
        
        webapp_url = f"{settings.WEBAPP_URL}?tgid={user.id}"
        keyboard = [[InlineKeyboardButton("Launch App", web_app={"url": webapp_url})]]
        
        # Fixed message without Markdown formatting issues
        registration_message = (
            f"🎉 Registration complete, {self.sanitize_name(user.first_name)}!\n\n"
            f"🔐 Your login details:\n\n"
            f"Username: {user.username}\n"
            f"Password: {user.id}\n\n"
            "If you need help, contact support: https://t.me/eyosafit"
        )
        
        await update.message.reply_text(
            registration_message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='MarkdownV2'  # Disable Markdown parsing
        )
    except Exception as e:
        error_message = (
            "❌ Registration failed:\n"
            f"{str(e)}\n\n"
            "Please contact support: https://t.me/eyosafit"
        )
        await update.message.reply_text(
            error_message,
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=None  # Disable Markdown parsing
        )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Operation cancelled.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    decision = query.data
    message = context.user_data.get('broadcast_message')
    
    if decision == "broadcast_yes":
        users = await get_all_users_list()
        success_count = 0
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"📢 Announcement:\n\n{message}"
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send to {user.telegram_id}: {e}")
        await query.edit_message_text(
            f"✅ Broadcast sent to {success_count}/{len(users)} users."
        )
    else:
        await query.edit_message_text("Broadcast cancelled.")
    return ConversationHandler.END

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    
    if str(telegram_id) != getattr(settings, 'TELEGRAM_ADMIN_ID', ''):
        await update.message.reply_text("⛔ Admin access required.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📢 Enter your broadcast message:",
        reply_markup=ReplyKeyboardRemove()
    )
    return BROADCAST_MESSAGE

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_message'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("✅ Confirm", callback_data="broadcast_yes")],
        [InlineKeyboardButton("❌ Cancel", callback_data="broadcast_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"⚠️ Confirm broadcast to all users:\n\n{update.message.text}",
        reply_markup=reply_markup
    )
    return BROADCAST_CONFIRM

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and handle network issues"""
    error = context.error
    
    if isinstance(error, NetworkError):
        logger.error(f"Network error: {error}")
    elif isinstance(error, Conflict):
        logger.error("Another bot instance is already running")
    else:
        logger.error(f"Unhandled error: {error}")
def setup_bot():
    # Configure application with robust settings
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).connect_timeout(30).pool_timeout(30).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("contact", contact))
    application.add_handler(CommandHandler("about", about))

    # Add conversation handlers
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            VERIFY_USERNAME: [CommandHandler('start', verify_username)],
            GET_CONTACT: [MessageHandler(filters.CONTACT, contact_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    broadcast_handler = ConversationHandler(
        entry_points=[CommandHandler('broadcast', broadcast_command)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)],
            BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_callback)]
        },
        fallbacks=[CommandHandler('cancel',cancel)]
    )

    application.add_handler(reg_handler)
    application.add_handler(broadcast_handler)
    application.add_error_handler(error_handler)
    
    return application
