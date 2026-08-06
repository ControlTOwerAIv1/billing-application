import os
import sys
import django

# Set up Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from django.contrib.auth.models import User

def create_admin():
    if not User.objects.filter(username="admin").exists():
        User.objects.create_superuser("admin", "admin@orderbot.local", "admin")
        print("[OK] Superuser created: Username='admin', Password='admin'")
    else:
        print("[INFO] Superuser 'admin' already exists.")

if __name__ == "__main__":
    create_admin()
