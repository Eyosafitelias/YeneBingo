from django.urls import path
from . import views

app_name = 'payment'

urlpatterns = [
    path('deposit/', views.deposit_view, name='deposit'),
    path('withdraw/', views.withdrawal_view, name='withdraw'),
    path('callback/', views.payment_callback, name='payment_callback'),
    path('success/', views.payment_success, name='payment_success'),
    path('history/', views.transaction_history, name='transaction_history'),
] 