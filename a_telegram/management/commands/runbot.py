from django.core.management.base import BaseCommand
import os
from a_telegram.telegram_bot import setup_bot

class Command(BaseCommand):
    help = 'Runs the Telegram bot'

    def handle(self, *args, **options):
        application = setup_bot()
        
        # Run the application
        self.stdout.write(self.style.SUCCESS('Starting bot...'))
        PORT = int(os.environ.get('PORT', 8000))
        WEBHOOK_DOMAIN = os.environ.get("WEBHOOK_DOMAIN")  # e.g. 'https://your-bot.onrender.com'
        TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{WEBHOOK_DOMAIN}/{TOKEN}"
        )
