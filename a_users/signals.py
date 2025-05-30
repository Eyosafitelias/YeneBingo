from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from a_users.models import Profile


@receiver(post_save, sender=User)       
def user_postsave(sender, instance, created, **kwargs):
    user = instance
    
    # Add profile if user is created
    if created:
        Profile.objects.create(user=user)
    
    # Handle email address
    try:
        email_address = EmailAddress.objects.get_primary(user)
        if email_address:  # Check if email_address exists
            if email_address.email.lower() != user.email.lower():
                email_address.email = user.email
                email_address.verified = False
                email_address.save()
        else:
            # No primary email exists, try to get any email
            email_address = EmailAddress.objects.filter(user=user).first()
            if email_address:
                email_address.primary = True
                email_address.email = user.email
                email_address.verified = False
                email_address.save()
            else:
                # Create new if none exists
                EmailAddress.objects.create(
                    user=user,
                    email=user.email, 
                    primary=True,
                    verified=False
                )
    except Exception as e:
        print(f"Error handling email for user {user.username}: {str(e)}")
        # Fallback creation if something went wrong
        EmailAddress.objects.create(
            user=user,
            email=user.email, 
            primary=True,
            verified=False
        )
        
@receiver(pre_save, sender=User)
def user_presave(sender, instance, **kwargs):
    if instance.username:
        instance.username = instance.username.lower()
    if instance.email:
        instance.email = instance.email.lower()