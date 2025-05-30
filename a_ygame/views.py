import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "a_core.settings")
django.setup()

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from a_ygame.models import Player, Game, Room
#from .utils import create_bingo_card, generate_bingo_cards
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
import json
from django.urls import reverse
from django.db.models import Count

presetCards = [
    [9,28,38,52,64,4,16,40,53,71,2,19,'*',56,63,6,23,33,55,70,1,27,42,57,75],
    [4,17,40,52,69,11,24,35,54,61,14,22,'*',55,70,15,28,41,53,73,13,16,43,60,67],
    [4,24,31,49,71,7,18,35,54,65,8,28,'*',51,66,1,29,36,53,75,5,26,40,59,61],
    [8,26,31,48,66,10,24,36,59,61,5,29,'*',54,65,2,30,44,50,72,14,21,43,46,67],
    [3,21,39,48,64,6,16,41,53,74,2,23,'*',51,67,10,27,42,50,73,14,26,33,60,70],
    [13,21,43,50,67,8,18,42,55,68,15,28,'*',48,63,9,16,45,49,64,4,20,35,56,70],
    [14,19,39,48,64,10,23,32,55,74,1,29,'*',49,61,3,22,45,60,72,15,21,43,54,63],
    [2,16,43,48,65,12,28,40,56,70,4,17,'*',50,75,5,20,36,47,74,9,21,44,60,62],
    [1,29,37,54,64,13,19,44,47,70,6,18,'*',56,61,5,21,39,55,68,8,23,35,52,75],
    [15,24,42,51,73,14,23,38,54,61,11,28,'*',55,71,4,26,33,53,66,8,21,39,59,63],
    [7,24,36,49,73,6,19,35,56,75,13,30,'*',48,72,3,23,31,51,67,8,26,45,59,62],
    [9,28,43,56,75,14,24,33,54,64,15,22,'*',48,73,1,23,32,46,63,4,17,40,58,61],
    [4,16,41,49,66,12,29,45,55,69,8,27,'*',56,73,2,25,40,57,63,5,26,38,54,62],
    [6,30,45,59,71,5,24,43,54,67,14,16,'*',56,62,11,29,35,46,74,3,23,32,57,70],
    [2,27,33,46,74,5,21,38,58,70,9,20,'*',50,61,14,24,40,51,66,10,19,44,49,73],
    [14,16,41,60,71,15,19,37,58,68,5,24,'*',46,65,11,30,31,50,67,4,29,44,53,69],
    [7,18,33,56,72,13,29,36,57,69,5,16,'*',55,64,3,24,38,59,62,15,28,42,51,66],
    [12,29,41,46,71,1,18,37,57,70,6,19,'*',51,72,7,24,43,50,75,11,23,36,55,69],
    [8,24,32,46,71,3,25,43,47,63,10,28,'*',59,74,4,27,41,58,70,14,17,40,55,65],
    [7,27,31,60,74,14,29,39,54,72,8,23,'*',59,69,15,30,32,49,73,11,25,44,50,63],
    [4,28,43,57,69,13,24,44,48,62,3,20,'*',46,65,12,21,34,52,64,7,25,45,59,66],
    [2,16,45,50,64,5,19,33,60,72,3,22,'*',47,74,1,26,44,54,63,12,18,36,48,68],
    [5,20,38,57,61,1,21,43,47,63,14,27,'*',49,64,4,24,44,48,68,8,30,32,56,66],
    [12,16,33,56,64,6,26,45,50,73,11,24,'*',46,71,2,23,40,51,67,4,17,43,47,63],
    [9,27,31,52,73,10,22,34,47,66,7,20,'*',49,70,8,16,33,48,71,3,17,43,50,74],
    [5,20,42,49,70,2,18,37,51,65,14,27,'*',58,72,12,26,34,50,64,1,22,45,52,67],
    [6,30,37,58,69,14,19,35,57,75,12,25,'*',59,65,5,17,34,53,66,13,28,38,52,74],
    [9,22,32,55,67,7,27,33,53,71,2,28,'*',51,68,10,24,40,49,64,3,19,38,54,63],
    [14,21,45,60,75,15,19,41,54,71,2,23,'*',58,69,9,29,37,52,65,7,28,34,55,74],
    [6,26,41,57,67,4,24,38,50,62,12,19,'*',60,63,13,20,43,53,65,14,27,33,46,71],
    [8,17,33,51,62,11,26,31,53,67,10,19,'*',57,72,14,24,35,48,66,1,30,39,56,75],
    [2,30,43,57,69,10,23,35,52,73,3,27,'*',59,62,5,24,32,50,70,8,20,34,47,61],
    [10,24,40,57,73,5,28,45,47,70,15,19,'*',59,61,9,29,39,56,68,4,26,33,54,72],
    [4,23,45,47,69,6,25,31,48,73,7,26,'*',59,62,1,20,35,49,74,15,17,40,51,64],
    [6,21,36,56,64,10,28,42,58,73,14,18,'*',55,68,8,29,37,48,72,3,22,32,46,71],
    [6,23,39,53,68,13,17,40,60,70,5,29,'*',59,66,15,24,33,56,69,8,27,44,49,71],
    [14,18,43,53,63,12,21,42,47,72,13,25,'*',55,67,9,30,33,56,65,4,23,34,46,69],
    [13,28,40,51,61,15,19,36,60,64,11,26,'*',58,67,1,30,45,50,62,9,27,31,56,69],
    [9,29,31,51,73,6,19,45,52,71,2,27,'*',59,75,13,24,32,53,70,11,25,42,48,68],
    [9,17,39,46,74,2,21,34,57,69,14,23,'*',53,68,11,30,35,58,61,13,26,42,54,67],
    [12,25,41,48,67,6,19,39,47,69,2,20,'*',57,75,14,16,31,46,63,8,29,33,49,68],
    [4,22,33,53,74,14,27,32,58,72,1,30,'*',56,65,12,19,35,51,71,15,17,43,50,66],
    [5,21,31,53,61,9,17,40,47,69,10,22,'*',46,63,12,16,32,52,68,3,28,41,56,75],
    [12,19,33,53,68,15,26,41,46,71,10,23,'*',58,69,9,18,31,49,64,8,27,44,50,66],
    [15,23,41,56,68,1,27,43,53,75,11,16,'*',60,62,9,18,44,50,72,13,22,34,46,67],
    [13,23,44,57,71,1,30,38,59,65,3,16,'*',51,70,2,29,37,46,74,9,24,35,47,62],
    [4,26,35,46,69,8,20,41,48,62,3,24,'*',50,68,2,30,43,51,74,6,16,39,57,73],
    [14,17,36,51,73,3,24,45,56,72,13,19,'*',50,62,5,26,39,60,66,9,23,40,47,75],
    [15,23,35,54,71,10,18,34,55,66,11,17,'*',50,73,8,26,36,59,72,9,19,42,60,62],
    [9,20,33,49,64,5,25,35,56,63,8,30,'*',51,61,12,17,36,46,65,4,26,41,54,75],
    [15,20,39,59,73,12,24,43,46,74,14,26,'*',56,64,4,18,40,54,68,9,25,33,58,69],
    [7,25,38,59,73,2,18,33,58,66,8,23,'*',50,70,3,16,36,54,67,14,22,32,48,75],
    [5,24,42,51,70,11,21,43,52,74,3,25,'*',59,61,4,29,45,56,68,1,20,37,53,75],
    [8,17,38,60,63,2,27,31,47,66,6,20,'*',53,75,7,25,37,58,70,12,21,34,57,73],
    [10,19,32,58,71,4,29,40,51,73,14,24,'*',50,67,15,18,39,46,72,5,25,37,47,64],
    [3,30,31,53,67,9,22,34,50,69,10,20,'*',59,72,13,23,41,56,73,1,29,37,60,61],
    [7,25,34,54,65,9,18,31,58,68,8,24,'*',48,72,12,19,40,55,61,3,28,43,46,67],
    [11,29,43,47,67,6,18,31,57,72,8,22,'*',49,65,1,16,41,48,69,13,20,37,55,75],
    [10,19,35,55,73,11,24,39,49,71,9,25,'*',60,70,15,22,45,46,61,12,16,41,51,62],
    [6,29,41,58,68,5,25,43,52,71,12,26,'*',49,72,11,22,45,56,65,4,24,35,51,70],
    [7,28,34,55,67,6,23,39,54,61,13,22,'*',50,71,3,26,32,58,69,9,21,44,51,65],
    [5,25,31,55,74,4,29,32,49,62,15,22,'*',52,71,8,16,33,47,61,14,23,38,57,67],
    [13,19,36,51,67,14,20,31,59,70,15,22,'*',58,61,4,16,32,56,63,7,18,37,54,68],
    [3,19,44,60,74,13,20,36,57,67,4,21,'*',58,71,11,25,34,52,62,9,26,38,50,73],
    [13,19,35,47,70,2,27,40,53,75,1,28,'*',60,63,5,24,32,56,61,15,16,43,46,74],
    [12,26,43,47,68,10,18,44,60,73,9,27,'*',53,72,8,25,32,55,67,14,17,38,59,75],
    [5,19,38,56,67,12,18,45,52,68,6,17,'*',50,71,4,25,37,46,63,3,29,34,47,70],
    [4,26,32,52,75,10,25,36,57,67,6,17,'*',54,74,1,19,45,60,68,5,20,31,51,63],
    [13,28,44,60,75,11,22,41,55,73,6,26,'*',53,74,2,16,35,47,68,10,25,42,49,72],
    [6,23,43,53,70,10,21,45,60,65,2,27,'*',57,71,12,22,39,52,72,1,16,37,46,68],
    [12,18,42,57,67,13,28,40,48,62,2,29,'*',49,66,14,17,41,51,75,5,27,33,53,69],
    [6,27,35,46,70,11,16,41,51,69,15,23,'*',54,64,14,21,39,48,68,3,26,32,58,61],
    [14,25,43,46,63,6,16,37,54,62,5,27,'*',58,74,7,23,31,51,73,8,21,40,48,72],
    [4,18,34,58,74,14,26,35,59,63,3,23,'*',51,61,2,22,39,52,65,10,21,42,57,67],
    [13,25,40,56,62,5,24,37,47,75,15,28,'*',60,73,6,29,45,46,65,12,16,32,48,68],
    [9,20,32,59,61,7,16,44,56,69,1,18,'*',51,72,10,29,35,49,66,15,26,41,57,65],
    [2,28,38,55,65,4,20,44,58,70,9,18,'*',49,69,1,24,36,59,72,12,29,42,51,64],
    [11,25,33,58,68,8,27,32,55,66,10,29,'*',60,62,13,16,31,56,74,4,30,43,53,65],
    [9,19,32,49,64,4,20,45,59,72,14,29,'*',58,67,12,17,41,55,65,3,24,35,60,75],
    [12,24,34,46,63,11,19,44,51,71,8,22,'*',49,70,4,26,42,50,67,7,18,38,59,75],
    [3,19,34,48,66,9,29,32,51,74,4,25,'*',55,64,14,28,44,50,72,12,18,42,53,75],
    [9,17,45,52,66,4,24,42,48,68,1,21,'*',46,74,8,23,35,59,64,3,18,37,47,63],
    [8,25,42,59,66,3,24,38,49,69,10,17,'*',46,65,1,16,35,52,61,12,23,40,55,63],
    [3,22,42,53,75,14,18,35,49,69,10,23,'*',60,63,8,24,44,58,70,6,29,41,50,73],
    [11,19,33,60,74,9,23,44,53,61,15,22,'*',47,63,8,18,31,57,70,6,20,34,59,75],
    [2,24,36,46,64,10,30,31,49,67,5,20,'*',51,74,3,22,44,58,62,7,29,32,47,65],
    [9,16,38,60,72,3,24,36,58,66,4,30,'*',59,68,7,28,39,54,71,14,18,35,52,61],
    [15,21,37,52,67,7,29,39,56,69,12,26,'*',49,73,1,30,32,46,72,9,22,33,54,62],
    [4,19,39,58,67,11,28,33,60,72,13,30,'*',47,74,8,24,38,59,71,14,17,36,49,66],
    [2,28,38,46,70,4,22,33,60,65,11,27,'*',59,69,15,21,35,58,71,13,16,31,52,63],
    [11,30,36,47,71,6,19,35,51,75,4,29,'*',48,68,13,20,39,59,66,14,28,32,57,70],
    [11,21,33,55,62,8,18,37,57,68,1,19,'*',53,65,3,26,38,60,61,7,25,39,59,63],
    [2,22,38,47,62,4,29,43,51,65,13,20,'*',50,61,6,18,45,49,63,12,27,40,48,69],
    [10,25,35,48,74,9,30,40,50,73,3,27,'*',56,75,1,19,37,49,62,4,23,44,53,67],
    [15,19,42,46,74,1,28,33,50,67,13,18,'*',54,75,9,22,31,57,73,5,24,36,48,71],
    [8,28,33,59,65,5,29,31,46,71,12,22,'*',57,62,11,24,39,48,73,2,30,42,51,72],
    [13,20,37,57,69,6,19,34,51,75,7,21,'*',60,73,4,30,39,55,68,14,26,31,54,71],
    [15,29,33,47,61,2,28,41,53,67,1,21,'*',55,64,10,27,40,58,71,13,16,32,54,66],
    [7,29,43,57,62,8,20,40,59,65,5,30,'*',53,64,9,18,37,52,66,6,25,44,56,61],
    [12,30,35,47,68,15,28,37,48,65,14,24,'*',55,66,9,25,36,50,73,5,17,34,56,63],
    [14,18,35,48,66,9,26,42,56,67,15,24,'*',58,72,1,30,36,57,75,5,16,40,49,63],
  ]

from a_users.models import Profile
@login_required
def rooms(request):
    rooms = Room.objects.all()
    try:
        profile = Profile.objects.get(user=request.user)
        balance = profile.balance
    except Profile.DoesNotExist:
        # Create a profile if it doesn't exist
        profile = Profile.objects.create(user=request.user)
        balance = profile.balance
    
    return render(request, 'a_ygame/rooms.html', {
        'rooms': rooms,
        'balance': balance
    })
    
@login_required
def join_room(request, room_name):
    """Handle joining a room"""
    room = get_object_or_404(Room, room_name=room_name)
    
    # Check if user already has a player instance in this room
    player = Player.objects.filter(user=request.user, room=room).first()
    
    if not player:
        # Create new player instance
        player = Player.objects.create(user=request.user, room=room)
    
    return JsonResponse({
        'success': True,
        'redirect': reverse('game:card_selection', args=[room_name])
    })

@login_required
def card_selection(request, room_name):
    """Display card selection page"""
    room = get_object_or_404(Room, room_name=room_name)
    players = Player.objects.filter(room=room)
    try:
        profile = Profile.objects.get(user=request.user)
        balance = profile.balance
    except Profile.DoesNotExist:
        # Create a profile if it doesn't exist
        profile = Profile.objects.create(user=request.user)
        balance = profile.balance
    # Generate available cards (1-75)
    available_cards = [{'number': i} for i in range(1, 101)]
    
    context = {
        'room': room,
        'players': players,
        'available_cards': available_cards,
        'currentUsername': request.user.username,
        'balance': balance
    }
    
    return render(request, 'a_ygame/card_selection.html', context)

@login_required
def join_game(request, room_name):
    """Handle joining a game with selected card"""
    try:
        room = Room.objects.get(room_name=room_name)
        
        # Check if game is already in progress
        if room.is_active:
            return JsonResponse({
                'success': False,
                'message': 'Game is already in progress'
            })
        
        # Get the card number from request
        data = json.loads(request.body)
        card_number = data.get('card_number')
        
        if not card_number:
            return JsonResponse({
                'success': False,
                'message': 'Please select a card'
            })
        
        # Check if card is already taken by another player
        existing_player = Player.objects.filter(room=room, card_number=card_number).first()
        if existing_player and existing_player.user != request.user:
            return JsonResponse({
                'success': False,
                'message': 'This card is already taken by another player'
            })
        
        # Check user's balance
        profile = request.user.profile
        if profile.balance < room.stake:
            return JsonResponse({
                'success': False,
                'message': 'Insufficient balance'
            })
        
        # Get or create player
        player, created = Player.objects.get_or_create(
            user=request.user,
            room=room,
            defaults={'card_number': card_number}
        )
        
        if not created:
            player.card_number = card_number
            player.save()
        
        # Deduct stake from user's balance
        profile.balance -= room.stake
        profile.save()
        
        return JsonResponse({
            'success': True,
            'redirect': reverse('game:game', args=[room_name])
        })
        
    except Room.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Room not found'
        })
    except Exception as e:
        print(f"Error in join_game: {str(e)}")  # Add logging
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

@login_required
def game_room(request, room_name):
    """Handle the game room page"""
    room = get_object_or_404(Room, room_name=room_name)
    
    # Get the player's card
    player = get_object_or_404(Player, user=request.user, room=room)
    
    # Get all players in the room
    players = Player.objects.filter(room=room)
    
    # Get the current game or create a new one if none exists
    game, created = Game.objects.get_or_create(
        room=room,
        is_active=True,
        defaults={'winner': None}
    )
    
    context = {
        'room': room,
        'player': player,
        'players': players,
        'game': game,
        'currentUsername': request.user.username
    }
    
    return render(request, 'a_ygame/game_room.html', context)

@login_required
def preview_card(request, card_number):
    """Handle card preview requests"""
    try:
        # Get the card numbers from the preset cards list
        card_numbers = presetCards[card_number - 1]  # Adjust for 0-based index
        
        # Create a 5x5 grid for the bingo card
        bingo_card = []
        for i in range(0, 25, 5):
            bingo_card.append(card_numbers[i:i+5])
        
        context = {
            'card_numbers': bingo_card,
            'card_number': card_number
        }
        
        return render(request, 'a_ygame/card_preview.html', context)
    except (IndexError, TypeError):
        return HttpResponse('Invalid card number', status=400)

@login_required
def game_view(request, room_name):
    try:
        room = Room.objects.get(room_name=room_name)
        player = Player.objects.get(user=request.user, room=room)
        
        if not player.card_number:
            messages.error(request, 'You must select a card first')
            return redirect('game:card_selection', room_name=room_name)
        
        # Get the card numbers from the preset cards list
        card_numbers = presetCards[player.card_number - 1]  # Adjust for 0-based index
        
        # Create a 5x5 grid for the bingo card
        bingo_card = []
        for i in range(0, 25, 5):
            bingo_card.append(card_numbers[i:i+5])
        
        context = {
            'room': room,
            'player': player,
            'currentUsername': request.user.username,
            'bingo_card': bingo_card
        }
        return render(request, 'a_ygame/game.html', context)
    except (Room.DoesNotExist, Player.DoesNotExist):
        messages.error(request, 'Invalid game room or player')
        return redirect('game:home')
# In your views.py or wherever you handle game ending
def end_game(request, room_name):
    try:
        room = Room.objects.get(room_name=room_name)
        game = Game.objects.filter(room=room, is_active=True).first()
        
        if game:
            game.is_active = False
            game.save()
            
            return JsonResponse({'success': True})
            
        return JsonResponse({'success': False, 'message': 'No active game'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})