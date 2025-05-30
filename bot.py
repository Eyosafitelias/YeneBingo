from telegram import (
    Update,
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    WebAppInfo,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler,CallbackQueryHandler
)
from a_core import settings
from a_telegram.models import TelegramUser
import os
from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist

# Conversation states
BROADCAST_MESSAGE = 1
BROADCAST_CONFIRM = 2

TOKEN = settings.TELEGRAM_BOT_TOKEN #'8049357114:AAFvZ_BQJSv59nfgLWLH9-45nW99zNGPI_A'
WEBAPP_URL = settings.WEBAPP_URL #"https://dx8g0c4k-9000.inc1.devtunnels.ms/"

# Async database functions
@sync_to_async
def get_user(user_id):
    try:
        return TelegramUser.objects.get(user_id=user_id)
    except ObjectDoesNotExist:
        return None

@sync_to_async
def create_user(user_data):
    return TelegramUser.objects.create(**user_data)

@sync_to_async
def get_all_users_list():
    return list(TelegramUser.objects.all())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    telegram_user = await get_user(user_id)
    
    if telegram_user:
        # User exists - show only Mini App button
        keyboard = [
            [InlineKeyboardButton("Launch Mini App", web_app=WebAppInfo(url=WEBAPP_URL))]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Welcome back! Click below to launch the Mini App.",
            reply_markup=reply_markup
        )
    else:
        # New user - show Share Contact button
        keyboard = [
            [KeyboardButton("Share Contact", request_contact=True)]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Welcome! Please share your contact to proceed.",
            reply_markup=reply_markup
        )

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user = update.effective_user
    
    # Save user data
    await create_user({
        'user_id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone_number': contact.phone_number,
        'is_admin': str(user.id) == settings.TELEGRAM_ADMIN_ID
    })
    
    # ✅ Remove the keyboard
    await update.message.reply_text(
        "Thank you! You can now launch the Mini App.",
        reply_markup=ReplyKeyboardRemove()
    )

    # Send new message with Mini App button
    keyboard = [
        [InlineKeyboardButton("Launch Mini App", web_app=WebAppInfo(url=WEBAPP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=user.id,
        text="Click below to launch the Mini App.",
        reply_markup=reply_markup
    )

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
                    chat_id=user.user_id,
                    text=f"📢 Announcement from admin:\n\n{message}"
                )
                success_count += 1
            except Exception as e:
                print(f"Failed to send to {user.user_id}: {e}")
        await query.edit_message_text(
            f"✅ Broadcast successful! Sent to {success_count}/{len(users)} users."
        )
    else:
        await query.edit_message_text("Broadcast cancelled.")

    return ConversationHandler.END

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if user is admin
    if str(user_id) != settings.TELEGRAM_ADMIN_ID:
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
                    chat_id=user.user_id,
                    text=f"📢 Announcement from admin:\n\n{message}"
                )
                success_count += 1
            except Exception as e:
                print(f"Failed to send to {user.user_id}: {e}")
        
        await update.message.reply_text(
            f"✅ Broadcast successful! Sent to {success_count}/{len(users)} users."
        )
    else:
        await update.message.reply_text("Broadcast cancelled.")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Broadcast cancelled.")
    return ConversationHandler.END

def setup_bot():
    application = Application.builder().token(TOKEN).build()
    
    # Conversation handler for broadcast
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('broadcast', broadcast_command)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)],
            BROADCAST_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    application.add_handler(CallbackQueryHandler(broadcast_callback))
    application.add_handler(conv_handler)
    
    return application