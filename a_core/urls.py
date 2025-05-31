"""
URL configuration for a_core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import sys
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from a_users.views import profile_view
from a_home.views import *
import os
from django.conf import settings
from django.conf.urls.static import static


admin_url = os.getenv("ADMIN_URL", "admin/")  # default to 'admin/' if missing
if admin_url == "admin/":
    print("\n🚫 WARNING: You must set the ADMIN_URL environment variable to a custom value.")
    print("For example: ADMIN_URL=superuserport/")
    print("The default '/admin/' is disabled for security reasons.\n")
    sys.exit(1)  # Stop server startup to force correction
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from telegram import Update
from telegram.ext import Application
import os
import json
from a_telegram.telegram_bot import setup_bot

application = setup_bot()

@csrf_exempt
def telegram_webhook(request):
    if request.method == "POST":
        update = Update.de_json(json.loads(request.body), application.bot)
        application.update_queue.put_nowait(update)
        return JsonResponse({"status": "ok"})
    return JsonResponse({"status": "not allowed"}, status=405)

from django.urls import path

urlpatterns = [
    path(f'{os.getenv("TELEGRAM_BOT_TOKEN")}', telegram_webhook),
    path(admin_url, admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('a_home.urls')),
    path('profile/', include('a_users.urls')),
    path('bingo/', include('a_ygame.urls')),
    path('payment/', include('a_payments.urls')),
    path('@<username>/', profile_view, name="profile"),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Only used when DEBUG=True, whitenoise can serve files when DEBUG=False
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
