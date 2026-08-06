import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from django.contrib.auth.models import User

def add_user():
    email_username = "superadmin@gmail.com"
    # Create or update superuser for superadmin@gmail.com
    user, created = User.objects.get_or_create(username=email_username, defaults={"email": email_username, "is_staff": True, "is_superuser": True})
    user.set_password("admin")
    user.is_staff = True
    user.is_superuser = True
    user.save()
    print(f"[OK] Created/updated superuser '{email_username}' with password 'admin'")

    # Also make sure 'admin' username password is 'admin'
    admin_user, _ = User.objects.get_or_create(username="admin", defaults={"email": "admin@orderbot.local", "is_staff": True, "is_superuser": True})
    admin_user.set_password("admin")
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.save()

if __name__ == "__main__":
    add_user()
