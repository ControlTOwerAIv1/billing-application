from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect, render

def miniapp_view(request):
    return render(request, "index.html")

urlpatterns = [
    path("", lambda request: redirect("admin/", permanent=False)),
    path("miniapp/", miniapp_view, name="miniapp"),
    path("admin/", admin.site.urls),
    path("api/", include("apps.api.urls")),
]
