from django.urls import path
from a_home.views import *

urlpatterns = [
    path('', home_view, name="home"),
    path('win_pattern/', win_view, name="win_pattern"),
]
