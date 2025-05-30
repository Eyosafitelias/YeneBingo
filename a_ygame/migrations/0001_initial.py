# Generated by Django 5.2 on 2025-05-22 07:51

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Game',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_active', models.BooleanField(default=True)),
                ('called_numbers', models.JSONField(default=list)),
                ('timer_started', models.BooleanField(default=False)),
                ('time_left', models.IntegerField(default=30)),
                ('winner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Player',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('card_number', models.IntegerField(blank=True, null=True)),
                ('card_numbers', models.JSONField(default=list)),
                ('marked_numbers', models.JSONField(default=list)),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('is_active', models.BooleanField(default=True)),
                ('game', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='players', to='a_ygame.game')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Room',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_name', models.CharField(max_length=100, unique=True)),
                ('stake', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('time_left', models.IntegerField(default=30)),
                ('timer_started', models.BooleanField(default=False)),
                ('current_players', models.ManyToManyField(related_name='rooms', through='a_ygame.Player', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='player',
            name='room',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='a_ygame.room'),
        ),
        migrations.AddField(
            model_name='game',
            name='room',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='a_ygame.room'),
        ),
        migrations.AlterUniqueTogether(
            name='player',
            unique_together={('user', 'room')},
        ),
        migrations.AddConstraint(
            model_name='game',
            constraint=models.UniqueConstraint(condition=models.Q(('is_active', True)), fields=('room', 'is_active'), name='one_active_game_per_room'),
        ),
    ]
