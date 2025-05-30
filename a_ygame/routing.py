import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "a_core.settings")
django.setup()

from django.urls import re_path
from a_ygame.consumers import CardSelectionConsumer, GameConsumer

websocket_urlpatterns = [
    re_path(r'ws/bingo/card-selection/(?P<room_name>\w+)/$', CardSelectionConsumer.as_asgi()),
    re_path(r'ws/bingo/game/(?P<room_name>\w+)/$', GameConsumer.as_asgi()),
]
