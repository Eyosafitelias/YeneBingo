import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "a_core.settings")
django.setup()

import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
import requests
from .models import Transaction
import uuid
from dotenv import load_dotenv
from chapa import Chapa
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
import logging
from decimal import Decimal ,InvalidOperation
logger = logging.getLogger(__name__)


load_dotenv()

chapa = Chapa(settings.CHAPA_SECRET_KEY)


@login_required
def deposit_view(request):
    logger.info(f"Callback received: {request.method} {request.GET}")
    if request.method == 'POST':
        amount = request.POST.get('amount')
        try:
            amount = float(amount)
            if amount < 50:
                messages.error(request, 'Deposit amount must be at least 50 ETB.')
                return redirect('payment:deposit')
                
            reference = str(uuid.uuid4())
            transaction = Transaction.objects.create(
                user=request.user,
                amount=amount,
                transaction_type='deposit',
                reference=reference
            )

            response = chapa.initialize(
                amount=float(amount),
                currency='ETB',
                email=request.user.email,
                first_name=request.user.first_name or request.user.username,
                last_name=request.user.last_name or '',
                tx_ref=reference,
                callback_url=f"{request.build_absolute_uri(reverse('payment:payment_callback'))}?tx_ref={reference}",
                return_url=request.build_absolute_uri(reverse('payment:payment_success')),
            )
            if response.get('status') == 'success':
                return redirect(response['data']['checkout_url'])
            else:
                transaction.status = 'failed'
                transaction.save()
                messages.error(request, 'Failed to initialize payment. Please try again.')
                
        except (ValueError, TypeError):
            messages.error(request, 'Please enter a valid amount.')
    
    return render(request, 'payment/deposit.html')

@login_required
def withdrawal_view(request):
    try:
        if request.method == 'POST':
            try:
                amount = Decimal(request.POST.get('amount'))
            except (ValueError, InvalidOperation):
                messages.error(request, 'Invalid amount')
                return redirect('payment:withdraw')
                
            bank_code = str(request.POST.get('bank_code'))
            account_number = str(request.POST.get('account_number'))
            account_name = str(request.POST.get('account_name'))

            # Validations
            if amount < Decimal('50'):
                messages.error(request, 'Withdrawal amount must be at least 50 ETB.')
                return redirect('payment:withdraw')

            if not all([bank_code, account_number, account_name]):
                messages.error(request, 'All fields are required.')
                return redirect('payment:withdraw')

            if request.user.profile.balance < amount:
                messages.error(request, 'Insufficient balance for this withdrawal.')
                return redirect('payment:withdraw')

            reference = str(uuid.uuid4())
            transaction = Transaction.objects.create(
                user=request.user,
                amount=amount,
                transaction_type='withdrawal',
                reference=reference,
                status='pending'
            )

            try:
                # Prepare the transfer payload
                payload = {
                    "account_name": account_name,
                    "account_number": account_number,
                    "amount": str(amount),  # Convert to string for API
                    "currency": "ETB",
                    "reference": reference,
                    "bank_code": bank_code
                }

                headers = {
                    'Authorization': f'Bearer {settings.CHAPA_SECRET_KEY}',
                    'Content-Type': 'application/json'
                }

                # Make the POST request to Chapa API
                response = requests.post(
                    "https://api.chapa.co/v1/transfers",
                    json=payload,
                    headers=headers
                )

                # Parse the response
                try:
                    data = response.json()
                except json.JSONDecodeError:
                    logger.error("Invalid JSON response from Chapa API")
                    raise Exception("Invalid response from payment provider")

                if response.status_code == 200 and data.get('status') == 'success':
                    transaction.status = 'completed'
                    # Both values are now Decimal
                    request.user.profile.balance -= amount
                    request.user.profile.save()
                    messages.success(request, 'Withdrawal submitted for processing!')
                    return redirect('payment:transaction_history')
                else:
                    transaction.status = 'failed'
                    error_message = data.get('message', 'Unknown error')
                    logger.error(f"Withdrawal failed: {error_message}")
                    messages.error(request, f"Withdrawal failed: {error_message}")

            except requests.exceptions.RequestException as api_error:
                transaction.status = 'failed'
                logger.error(f"Chapa API request failed: {str(api_error)}")
                messages.error(request, "Payment service error. Please try later.")

    except Exception as e:
        logger.error(f"Withdrawal error: {str(e)}")
        messages.error(request, 'An error occurred')

    return render(request, 'payment/withdrawal.html')

@csrf_exempt
def payment_callback(request):
    # Handle both GET and POST methods
    if request.method not in ['GET', 'POST']:
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

    # Check for both parameter names
    reference = request.GET.get('tx_ref') or request.GET.get('trx_ref')
    status = request.GET.get('status')
    
    if not reference:
        return JsonResponse({'status': 'error', 'message': 'Missing reference'}, status=400)

    try:
        transaction = Transaction.objects.get(reference=reference)
        
        # Only process if not already completed
        if transaction.status != 'completed':
            if status == 'success':
                transaction.status = 'completed'
                
                if transaction.transaction_type == 'deposit':
                    profile = transaction.user.profile
                    profile.balance += transaction.amount
                    profile.save()
            else:
                transaction.status = 'failed'
            
            transaction.save()

        # Handle JSONP if callback parameter exists
        callback = request.GET.get('callback')
        response_data = {
            'status': 'success',
            'message': 'Payment processed',
            'transaction_id': str(transaction.id),
            'amount': str(transaction.amount)
        }
        
        if callback:
            response = f"{callback}({json.dumps(response_data)})"
            return HttpResponse(response, content_type='application/javascript')
            
        return JsonResponse(response_data)

    except Transaction.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Transaction not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def payment_success(request):
    reference = request.GET.get('tx_ref') or request.GET.get('trx_ref')
    transaction = None
    success = False
    
    if reference:
        try:
            transaction = Transaction.objects.get(
                reference=reference,
                user=request.user
            )
            
            # Additional verification step
            if transaction.status == 'completed':
                success = True
            else:
                # If status isn't completed, try to verify
                try:
                    verification = chapa.verify(reference)
                    if verification.get('status') == 'success':
                        transaction.status = 'completed'
                        if transaction.transaction_type == 'deposit':
                            profile = transaction.user.profile
                            profile.balance += transaction.amount
                            profile.save()
                        transaction.save()
                        success = True
                except Exception as e:
                    print(f"Verification failed: {str(e)}")

        except Transaction.DoesNotExist:
            pass
    
    context = {
        'transaction': transaction,
        'success': success
    }
    return render(request, 'payment/success.html', context)

def payment_return(request):
    messages.success(request, 'Payment processed. You can now see your updated balance.')
    return render(request, 'pyments/payment/success.html')

@login_required
def transaction_history(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'payment/history.html', {'transactions': transactions})

def verify_transaction(reference):
    response = chapa.verify(reference)
    logger.info(f"Verification response: {response}")
    return response