from django.core.management.base import BaseCommand
from backend.run_chat import main as run_chat_main

class Command(BaseCommand):
    help = "Start the interactive OrderBot AI CLI chat console"

    def handle(self, *args, **options):
        run_chat_main()
