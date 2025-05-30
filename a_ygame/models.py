from django.db import models
from django.contrib.auth.models import User

from django.utils import timezone

class Room(models.Model):
    room_name = models.CharField(max_length=100, unique=True)
    stake = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    time_left = models.IntegerField(default=30)
    timer_started = models.BooleanField(default=False)
    current_players = models.ManyToManyField(User, through='Player', related_name='rooms')

    def __str__(self):
        return self.room_name

class Player(models.Model):
    game = models.ForeignKey(
        'Game', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='players'
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    card_number = models.IntegerField(null=True, blank=True)
    card_numbers = models.JSONField(default=list)
    marked_numbers = models.JSONField(default=list)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'room')

    def __str__(self):
        return f"{self.user.username} in {self.room.room_name}"

class Game(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    called_numbers = models.JSONField(default=list)
    winner = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    timer_started = models.BooleanField(default=False)
    time_left = models.IntegerField(default=30)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['room', 'is_active'],
                condition=models.Q(is_active=True),
                name='one_active_game_per_room'
            )
        ]

    def save(self, *args, **kwargs):
        # Ensure only one active game per room
        if self.is_active:
            Game.objects.filter(room=self.room, is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Game in {self.room.room_name} at {self.created_at}"

