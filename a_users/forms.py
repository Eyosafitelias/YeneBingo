from django.forms import ModelForm
from django import forms
from django.contrib.auth.models import User
from .models import Profile
from allauth.account.forms import LoginForm

class ProfileForm(ModelForm):
    class Meta:
        model = Profile
        fields = ['image', 'displayname', 'info', 'balance' ]
        widgets = {
            'image': forms.FileInput(),
            'displayname' : forms.TextInput(attrs={'placeholder': 'Add display name'}),
            'info' : forms.Textarea(attrs={'rows':3, 'placeholder': 'Add information'}),
            'balance': forms.NumberInput(attrs={'readonly': 'readonly', 'disabled': 'disabled'})
        }
        
        
class EmailForm(ModelForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['email']


class UsernameForm(ModelForm):
    class Meta:
        model = User
        fields = ['username']


class CustomLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove the help text from the password field
        self.fields['password'].help_text = None