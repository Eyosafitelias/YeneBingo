from django.urls import path
from . import views

app_name = 'game'

urlpatterns = [
    path('', views.rooms, name='rooms'),
    path('join-room/<str:room_name>/', views.join_room, name='join_room'),
    path('card-selection/<str:room_name>/', views.card_selection, name='card_selection'),
    path('preview-card/<int:card_number>/', views.preview_card, name='preview_card'),
    path('join-game/<str:room_name>/', views.join_game, name='join_game'),
    path('game/<str:room_name>/', views.game_view, name='game'),
]