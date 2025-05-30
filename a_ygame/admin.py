from django.contrib import admin
from .models import Room, Player, Game

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_name', 'stake', 'is_active', 'created_at')
    search_fields = ('room_name',)
    list_filter = ('is_active',)

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('user', 'room', 'card_number', 'is_active', 'joined_at')
    search_fields = ('user__username', 'room__room_name')
    list_filter = ('is_active',)

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('room', 'is_active', 'winner', 'created_at')
    search_fields = ('room__room_name',)
    list_filter = ('is_active',)