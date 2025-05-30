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
from a_core.settings import settings
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
# Sanitize names to remove special characters
def sanitize_name(name):
    if not name:
        return ""
    return re.sub(r'[^\w\s-]', '', name).strip()
# Async database functions
@sync_to_async
def generate_unique_email():
    count = TelegramUser.objects.count() + 1
    return f"yenebingo{count}@gmail.com"
@sync_to_async 
def get_user(telegram_id):
    try:
        return TelegramUser.objects.get(telegram_id=telegram_id)
    except ObjectDoesNotExist:
        return None
@sync_to_async
def create_telegram_user(telegram_id, username, first_name, last_name, phone_number):
    """Create both Django User and TelegramUser with comprehensive error handling"""
    try:
        # Sanitize names
        first_name = sanitize_name(first_name)
        last_name = sanitize_name(last_name)
        
        # Generate unique email
        email = f"yenebingo{TelegramUser.objects.count() + 1}@gmail.com"
        
        # Handle missing username
        if not username:
            username = f"user_{telegram_id}"
        
        # Ensure username is unique
        original_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{original_username}_{counter}"
            counter += 1
        
        # Create Django User
        django_user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=str(telegram_id)
        )
        
        # Create TelegramUser
        telegram_user = TelegramUser.objects.create(
            user=django_user,
            telegram_id=telegram_id,
            username=username,
            phone_number=phone_number,
            is_admin=str(telegram_id) == settings.TELEGRAM_ADMIN_ID
        )
        
        return telegram_user
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise Exception(f"Could not create user: {str(e)}")
@sync_to_async
def get_all_users_list():
    return list(TelegramUser.objects.all())
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and handle network issues"""
    error = context.error
    
    if isinstance(error, NetworkError):
        logger.error(f"Network error: {error}")
    elif isinstance(error, Conflict):
        logger.error("Another bot instance is already running")
    else:
        logger.error(f"Unhandled error: {error}")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = user.id
    
    telegram_user = await get_user(telegram_id)
    
    if telegram_user:
        # User exists - show only Mini App button
        webapp_url = f"{settings.WEBAPP_URL}?tgid={telegram_id}"
        keyboard = [
            [InlineKeyboardButton("Launch App", web_app=WebAppInfo(url=webapp_url))]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🎉 Wellcome Back, {sanitize_name(user.first_name)}!\n\n"
            f"🔐 This is Your Username And Password\n Pleas Use theme to login in the mini app\n\n"
            f"Username:{user.username}\n"
            f"Password: {user.id}\n\n"
            f"Click the button below to launch the app:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    if not user.username:
        # No username - instruct user to set one
        await update.message.reply_text(
            "⚠️ You need to set a Telegram username first.\n\n"
            "Please go to Telegram Settings > Edit Profile > Username to set one, "
            "then come back and /start again."
        )
        return VERIFY_USERNAME
    
    keyboard = [[KeyboardButton("Share Contact", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "To complete registration, please share your contact:",
        reply_markup=reply_markup
    )
    return GET_CONTACT
async def verify_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for when user comes back after setting username"""
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
    """Handle received contact with better error reporting"""
    user = update.effective_user
    contact = update.message.contact
    
    # Verify contact belongs to user
    if contact.user_id != user.id:
        await update.message.reply_text("⚠️ Please share your own contact.")
        return GET_CONTACT
    await update.message.reply_text(
        "Thank you! Your contact has been received.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await asyncio.sleep(0.5) # Simulate processing delay
    
    try:
        telegram_user = await create_telegram_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            phone_number=contact.phone_number
        )
        
        webapp_url = f"{settings.WEBAPP_URL}?tgid={user.id}"
        keyboard = [[InlineKeyboardButton("Launch App", web_app=WebAppInfo(url=webapp_url))]]
        
        await update.message.reply_text(
            f"🎉 Registration complete, {sanitize_name(user.first_name)}!\n\n"
            f"🔐 Your login details:\n"
            f"Use this Username And Password to login in the mini app\n\n"
            f"Username: {user.username}\n"
            f"Password: {user.id}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
             )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Registration failed:\n{str(e)}\n\nPlease contact support.at https://t.me/eyosafit",
            reply_markup=ReplyKeyboardRemove()
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
                    text=f"📢 Announcement from admin:\n\n{message}"
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send to {user.telegram_id}: {e}")
        await query.edit_message_text(
            f"✅ Broadcast successful! Sent to {success_count}/{len(users)} users."
        )
    else:
        await query.edit_message_text("Broadcast cancelled.")
    return ConversationHandler.END
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    
    if str(telegram_id) != settings.TELEGRAM_ADMIN_ID:
        await update.message.reply_text("⛔ Admin access required.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📢 Enter your broadcast message:\n"
        "(Type /cancel to abort)",
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
        f"⚠️ Confirm broadcast to all users:\n\n"
        f"{update.message.text}\n\n"
        f"This will be sent to all registered users.",
        reply_markup=reply_markup
    )
    return BROADCAST_CONFIRM
async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == 'yes':
        message = context.user_data['broadcast_message']
        users = await get_all_users_list()  # Now properly async
        
        success_count = 0
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"📢 Announcement from admin:\n\n{message}"
                )
                success_count += 1
            except Exception as e:
                print(f"Failed to send to {user.telegram_id}: {e}")
                
        await update.message.reply_text(
            f"✅ Broadcast successful! Sent to {success_count}/{len(users)} users."
        )
    else:
        await update.message.reply_text("Broadcast cancelled.")
    
    return ConversationHandler.END
def setup_bot():
    # Configure application with robust settings
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).connect_timeout(30).pool_timeout(30).build()
    
    # Add error handler
    
    # Conversation handlers
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            VERIFY_USERNAME: [CommandHandler('start', verify_username)],
            GET_CONTACT: [MessageHandler(filters.CONTACT, contact_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    conv_handler_bradcast = ConversationHandler(
        entry_points=[CommandHandler('broadcast', broadcast_command)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)],
            BROADCAST_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            VERIFY_USERNAME: [CommandHandler('start', verify_username)],
            GET_CONTACT: [MessageHandler(filters.CONTACT, contact_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    application.add_handler(CallbackQueryHandler(broadcast_callback))
    application.add_handler(conv_handler_bradcast)
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    return application
'''
###################################################
# Conversation states
BROADCAST_MESSAGE = 1
BROADCAST_CONFIRM = 2
VERIFY_USERNAME, GET_CONTACT = range(2)
from a_core import settings

TOKEN = settings.TELEGRAM_BOT_TOKEN
WEBAPP_URL = settings.WEBAPP_URL

# Async database functions

@sync_to_async
def generate_unique_email():
    count = TelegramUser.objects.count() + 1
    return f"yenebingo{count}@gmail.com"

@sync_to_async
def get_user(telegram_id):
    try:
        return TelegramUser.objects.get(telegram_id=telegram_id)
    except ObjectDoesNotExist:
        return None

@sync_to_async
def create_telegram_user(telegram_id, username, first_name, last_name, phone_number):
    """Create both Django User and TelegramUser with comprehensive error handling"""
    try:
        # Generate unique email
        email = f"yenebingo{TelegramUser.objects.count() + 1}@gmail.com"
        # Handle missing username
        if not username:
            username = f"user_{telegram_id}"
        
        # Ensure username is unique
        original_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{original_username}_{counter}"
            counter += 1
        
        # Create Django User
        django_user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name or "",
            last_name=last_name or "",
            password=str(telegram_id)
        )
        # Create TelegramUser
        telegram_user = TelegramUser.objects.create(
            user=django_user,
            telegram_id=telegram_id,
            username=username,
            phone_number=phone_number,
            is_admin=str(telegram_id) == settings.TELEGRAM_ADMIN_ID
            )
        
        return telegram_user
    except Exception as e:
        print(f"Detailed error: {str(e)}")
        raise Exception(f"Could not create user: {str(e)}")
        
    



@sync_to_async
def get_all_users_list():
    return list(TelegramUser.objects.all())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = user.id
    
    telegram_user = await get_user(telegram_id)
    
    if telegram_user:
        # User exists - show only Mini App button
        webapp_url = f"{settings.WEBAPP_URL}?tgid={telegram_id}"
        keyboard = [
            [InlineKeyboardButton("Launch App", web_app=WebAppInfo(url=webapp_url))]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Welcome back, {user.first_name}!",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    if not user.username:
        # No username - instruct user to set one
        await update.message.reply_text(
            "⚠️ You need to set a Telegram username first.\n\n"
            "Please go to Telegram Settings > Edit Profile > Username to set one, "
            "then come back and /start again."
        )
        return VERIFY_USERNAME
    keyboard = [[KeyboardButton("Share Contact", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "To complete registration, please share your contact:",
        reply_markup=reply_markup
    )
    return GET_CONTACT
async def verify_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for when user comes back after setting username"""
    user = update.effective_user
    
    if not user.username:
        await update.message.reply_text(
            "❌ You still don't have a username set.\n\n"
            "Please set a username in Telegram Settings and try /start again."
        )
        return VERIFY_USERNAME
    
    # Now that they have username, request contact
    keyboard = [[KeyboardButton("Share Contact", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "Thank you! Now please share your contact to complete registration:",
        reply_markup=reply_markup
    )
    return GET_CONTACT

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle received contact with better error reporting"""
    user = update.effective_user
    contact = update.message.contact
    
    # Verify contact belongs to user
    if contact.user_id != user.id:
        await update.message.reply_text("⚠️ Please share your own contact.")
        return GET_CONTACT
    
    try:
        # Ensure we have required fields
        username = user.username or f"user_{user.id}"
        first_name = user.first_name or ""
        last_name = user.last_name or ""
        
        telegram_user = await create_telegram_user(
            telegram_id=user.id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            phone_number=contact.phone_number
        )
        
        # Success response
        webapp_url = f"{settings.WEBAPP_URL}?tgid={user.id}"
        keyboard = [[InlineKeyboardButton("Launch App", web_app=WebAppInfo(url=webapp_url))]]
        
        await update.message.reply_text(
            f"🎉 Registration complete!\n\n"
            f"Username: {username}\n"
            f"Password: {user.id}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Registration failed:\n{str(e)}\n\nPlease contact support at.\n https://t.me/eyosafit",
            reply_markup=ReplyKeyboardRemove()
        )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel registration process"""
    await update.message.reply_text(
        "Its Cancelled. You can start over",
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
                    text=f"📢 Announcement from admin:\n\n{message}"
                )
                success_count += 1
            except Exception as e:
                print(f"Failed to send to {user.telegram_id}: {e}")
        await query.edit_message_text(
            f"✅ Broadcast successful! Sent to {success_count}/{len(users)} users."
        )
    else:
        await query.edit_message_text("Broadcast cancelled.")

    return ConversationHandler.END

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    
    # Check if user is admin
    if str(telegram_id) != settings.TELEGRAM_ADMIN_ID:
        await update.message.reply_text(
            "⛔ You are not the admin of this bot. You can't use this command."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📢 Please type your message to broadcast to all users:"
    )
    return BROADCAST_MESSAGE

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_message'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("✅ Yes", callback_data="broadcast_yes")],
        [InlineKeyboardButton("❌ No", callback_data="broadcast_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Are you sure you want to broadcast this message to all users?\n\n"
        f"{update.message.text}\n\n"
        f"Type 'yes' to confirm or 'no' to cancel.",
        reply_markup=reply_markup
    )
    return BROADCAST_CONFIRM

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == 'yes':
        message = context.user_data['broadcast_message']
        users = await get_all_users_list()  # Now properly async
        
        success_count = 0
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"📢 Announcement from admin:\n\n{message}"
                )
                success_count += 1
            except Exception as e:
                print(f"Failed to send to {user.telegram_id}: {e}")
        
        await update.message.reply_text(
            f"✅ Broadcast successful! Sent to {success_count}/{len(users)} users."
        )
    else:
        await update.message.reply_text("Broadcast cancelled.")
    
    return ConversationHandler.END

def setup_bot():
    application = Application.builder().token(TOKEN).build()
    
    # Conversation handler for broadcast
    conv_handler_bradcast = ConversationHandler(
        entry_points=[CommandHandler('broadcast', broadcast_command)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)],
            BROADCAST_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            VERIFY_USERNAME: [CommandHandler('start', verify_username)],
            GET_CONTACT: [MessageHandler(filters.CONTACT, contact_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    # Handlers
    #application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    application.add_handler(CallbackQueryHandler(broadcast_callback))
    application.add_handler(conv_handler_bradcast)
    application.add_handler(conv_handler)
    
    return application
'''