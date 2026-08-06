from django.urls import path
from apps.api.api import api

urlpatterns = [
    path("", api.urls),
]
