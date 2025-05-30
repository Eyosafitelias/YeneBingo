from django.core.management.base import BaseCommand
import asyncio
from a_telegram.telegram_bot import setup_bot

class Command(BaseCommand):
    help = 'Runs the Telegram bot'

    def handle(self, *args, **options):
        application = setup_bot()
        
        # Run the application
        self.stdout.write(self.style.SUCCESS('Starting bot...'))
        application.run_polling()