from django.core.management.base import BaseCommand
from backend.run_telegram_bot import main as run_bot_main

class Command(BaseCommand):
    help = "Start the live OrderBot Telegram Bot listener"

    def handle(self, *args, **options):
        run_bot_main()
