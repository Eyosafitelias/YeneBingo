from django.db import models
from django.contrib.auth.models import User


# Create your models here.
class TelegramUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    telegram_id  = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=255, null=True, blank=True)
    first_name = models.CharField(max_length=255, null=True, blank=True)    
    last_name = models.CharField(max_length=255, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    registration_date = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)  # New field

    def __str__(self):
        return self.username or str(self.telegram_id)