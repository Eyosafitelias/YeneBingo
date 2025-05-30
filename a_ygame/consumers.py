import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "a_core.settings")
django.setup()

import json
import asyncio
import random
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async
from a_ygame.models import Room, Player, Game
from django.utils import timezone
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

class BingoConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for handling real-time bingo game updates.
    Manages room connections, number selection, and broadcasting updates.
    """
    
    room_states = {}
    active_cards = set()

    async def connect(self):
        """Handle WebSocket connection"""
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'card_selection_{self.room_name}'
        
        # Join room group
        self.game = await database_sync_to_async(
            lambda: Game.objects.filter(
                room_room_name=self.room_name,
                is_active=True).first()
        )()
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        #await self.accept()
        
        # Initialize room state if it doesn't exist
        if self.room_name not in self.room_states:
            self.room_states[self.room_name] = {
                'selected_cards': {},
                'game_started': False,
                'player_count': 0
            }
        
        # Send current game state to the new client
        await self.send_game_state()
        
        # Get current player's card selection
        try:
            room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
            player = await database_sync_to_async(Player.objects.get)(room=room, user=self.user)
            
            if player.card_number:
                # Broadcast the current selection to all clients
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'card_selected',
                        'card_number': player.card_number,
                        'username': self.user.username
                    }
                )
        except Exception as e:
            print(f"Error getting player card on connect: {e}")
        
        # Initialize room state if it doesn't exist
        if self.room_name not in self.room_states:
            self.room_states[self.room_name] = {
                'players': [],
                'countdown': 30,
                'countdown_task': None,
                'game_active': False,
                'game_started': False,
                'calling_numbers': False,
                'number_calling_task': None,
                'called_numbers': []
            }
        
        await self.accept()
        
        # Send initial game state to the client
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'game_state': self.room_states[self.room_name]
        }))

        # Start game timer if not already started
        if not hasattr(self, 'game_timer_started'):
            self.game_timer_started = True
            await self.start_game_timer()
            
        await self.send(text_data=json.dumps({
                'type': 'active_cards_update',
                'active_cards': list(self.active_cards)
            }))
        await self.notify_card_usage('add')
        
    async def disconnect(self, close_code):
        if not hasattr(self, 'room_name') or self.room_name not in self.room_states:
            return
            
        room_state = self.room_states[self.room_name]
        user = self.scope['user']
        
        try:
            if user.is_authenticated and user.username in room_state['players']:
                room_state['players'].remove(user.username)
                

                # Clear the player's card selection
                try:
                    room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
                    player = await database_sync_to_async(Player.objects.get)(room=room, user=user)

                    if player.card_number:
                        card_number = player.card_number
                        
                        # Broadcast to card selection group
                        await self.channel_layer.group_send(
                            f"card_selection_{self.room_name}",
                            {
                                'type': 'card_deselected',
                                'card_number': card_number,
                                'username': user.username
                            }
                        )

                        # Clear card in DB
                        def clear_card(p):
                            p.card_number = None
                            p.save()
                        await database_sync_to_async(clear_card)(player)

                except Exception as e:
                    print(f"[DISCONNECT] Failed to clear card for {user.username}: {e}")
                # Update player count for remaining players
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'player_count_update',
                        'count': len(room_state['players']),
                        'message': f'Player left: {user.username} ({len(room_state["players"])}/2)'
                    }
                )
                
                # If less than 2 players, reset the game and stop number calling
                if len(room_state['players']) < 2:
                    print(f"Less than 2 players remaining, resetting game...")
                    
                    # Stop number calling if it's running
                    if room_state.get('calling_numbers', False):
                        print("Stopping number calling...")
                        room_state['calling_numbers'] = False
                        
                        # Cancel any running number calling task
                        if room_state.get('number_calling_task'):
                            if not room_state['number_calling_task'].done():
                                room_state['number_calling_task'].cancel()
                                try:
                                    await room_state['number_calling_task']
                                except asyncio.CancelledError:
                                    pass
                    
                    # Reset game state
                    room_state.update({
                        'game_active': False,
                        'game_started': False,
                        'called_numbers': [],
                        'countdown': 30,
                        'countdown_task': None,
                        'calling_numbers': False,
                        'number_calling_task': None
                    })
                    
                    # Notify all clients about game reset
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'game_reset',
                            'message': 'Game reset: Not enough players. Waiting for more players...'
                        }
                    )
                    
                    # Clear called numbers from database
                    try:
                        room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
                        game = await database_sync_to_async(lambda: getattr(room, 'game', None))()
                        if game:
                            await database_sync_to_async(game.called_numbers.clear)()
                    except Exception as e:
                        print(f"Error clearing called numbers: {e}")
                
                # Reset game if no players left
                if not room_state['players']:
                    if room_state['countdown_task']:
                        room_state['countdown_task'].cancel()
                    del self.room_states[self.room_name]
                
        finally:
            # Always clean up the connection
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            await self.notify_card_usage('remove')

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')
        message_type = data.get('type')

        print(f"Received message: {data}")  # Debug log
        
        if message_type == 'start_new_game':
            # Handle start new game request
            room_state = self.room_states.get(self.room_name, {})
            room_state.update({
                'game_active': False,
                'game_started': False,
                'called_numbers': [],
                'calling_numbers': False,
                'number_calling_task': None
            })
            
            # Notify all clients that the game has been reset
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_reset',
                    'message': 'Game has been reset. Starting new game...'
                }
            )
            
            # Start a new game
            await self.start_game_timer()
            
        elif action == 'declare_bingo':
            print("Handling bingo declaration...")  # Debug log
            await self.handle_bingo_declaration(data)
        elif action == 'start_countdown':
            if not self.game_active:
                if not self.countdown_task:
                    self.countdown_task = asyncio.create_task(self.start_countdown())
        elif action == 'number_called':
            await self.handle_number_called(data)
        elif data.get('type') == 'card_activated':
            self.active_cards.add(data['card_number'])
            await self.channel_layer.group_send(
                f'card_selection_{self.room_name}',
                {
                    'type': 'card_activated',
                    'card_number': data['card_number']
                }
            )
            
        elif data['type'] == 'card_selected':
            # Check if game has started
            room_state = self.room_states.get(self.room_name, {})
            if room_state.get('game_started', False):
                await self.send(text_data=json.dumps({
                    'type': 'game_started_toast',
                    'message': 'Game has started! Please wait until the game ends to select cards.'
                }))
                return
            
            # Handle card selection
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'card_selected',
                    'card_number': data['card_number'],
                    'user': data['user'],
                    'action': data['action']
                }
            )
        elif data['type'] == 'game_started':
            # Handle game started
            room_state = self.room_states.get(self.room_name, {})
            room_state.update({
                'game_active': True,
                'game_started': True,
                'calling_numbers': False,
                'number_calling_task': None
            })
            await self.send_game_state()
            await self.call_numbers()
        elif data['type'] == 'game_reset':
            # Handle game reset
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'reset_game_state'
                }
            )
        elif data['type'] == 'get_state':
            # Send current game state
            await self.send_game_state()
        elif data['type'] == 'game_over':
            await self.game_ended(data)
        elif data['type'] == 'request_active_cards':
            await self.handle_active_cards_request(data)
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Unknown message type: {message_type}'
            }))

    async def card_selected(self, event):
        """Handle card_selected event from room group"""
        await self.send(text_data=json.dumps({
            'type': 'card_selected',
            'card_number': event['card_number'],
            'user': event['user'],
            'action': event['action']
        }))

    async def game_started(self, event):
        """Handle game started event"""
        await self.send(text_data=json.dumps({
            'type': 'game_started',
            'message': 'Game has started!'
        }))
        
        # Start calling numbers
        await self.call_numbers()

    async def number_called(self, event):
        # Send called number to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'number_called',
            'number': event['number']
        }))

    async def game_state(self, event):
        # Send game state to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'status': event['status']
        }))

    async def start_game_timer(self):
        # Wait for 30 seconds
        await asyncio.sleep(30)
        
        # Get the room and start the game
        room = await self.get_room(self.room_name)
        if room:
            # Start the game
            game = await self.start_game(room)
            if game:
                # Notify all clients that the game has started
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'game_state',
                        'status': 'started'
                    }
                )
                # Start calling numbers
                await self.call_numbers()

    @database_sync_to_async
    def get_room(self):
        """Get room instance for the current room"""
        try:
            return Room.objects.get(room_name=self.room_name)
        except Room.DoesNotExist:
            return None
    async def notify_card_usage(self, action):
        """Notify card selection room about cards being used/released"""
        room = await self.get_room()
        if room:
            players = await database_sync_to_async(Player.objects.filter)(room=room, game__is_active=True)
            for player in players:
                if player.card_number:
                    await self.channel_layer.group_send(
                        f'card_selection_{self.room_name}',
                        {
                            'type': 'game_state_update',
                            'card_number': player.card_number,
                            'action': action
                        }
                    )
    async def start_game(self, room):
        """Start a new game for the room"""
        try:
            # Create a new game
            game = await database_sync_to_async(Game.objects.create)(room=room)
            
            # Ensure called numbers are empty
            game.called_numbers = []
            await database_sync_to_async(game.save)()
            
            # Reset room state
            if self.room_name in self.room_states:
                room_state = self.room_states[self.room_name]
                room_state.update({
                    'game_active': True,
                    'game_started': True,
                    'called_numbers': [],
                    'calling_numbers': False,
                    'number_calling_task': None
                })
            
            return game
        except Exception as e:
            print(f"Error starting game: {e}")
            return None

    async def call_numbers(self):
        """Call random numbers for the bingo game"""
        if not self.room_name:
            print("Room name not set. Cannot call numbers.")
            return

        room_state = self.room_states.get(self.room_name, {})
        if not room_state:
            print(f"No room state found for {self.room_name}")
            return
            
        if room_state.get('calling_numbers') or not room_state.get('game_active'):
            print(f"Not starting number calling. calling_numbers: {room_state.get('calling_numbers')}, game_active: {room_state.get('game_active')}")
            return
            
        room_state['calling_numbers'] = True
        
        try:
            # Get the current game
            room = await self.get_room(self.room_name)
            if not room:
                print(f"No room found for {self.room_name}")
                return

            game = await database_sync_to_async(lambda: Game.objects.filter(room=room, is_active=True).first())()
            if not game:
                print(f"No active game found for room: {self.room_name}")
                return

            # Ensure called numbers are empty
            game.called_numbers = []
            await database_sync_to_async(game.save)()
            print("Initialized empty called numbers list")

            # Generate all possible numbers (1-75 for standard bingo)
            all_numbers = list(range(1, 76))
            available_numbers = all_numbers.copy()  # Start with all numbers available
            random.shuffle(available_numbers)
            
            print(f"Starting number calling with {len(available_numbers)} available numbers")
            
            # Call numbers one by one with a delay
            for number in available_numbers:
                # Check if game is still active and has enough players
                if not room_state.get('game_active', False) or len(room_state['players']) < 2:
                    print("Game no longer active or not enough players, stopping number calling")
                    break
                
                # Get the BINGO letter for the number
                letter = self.get_bingo_letter(number)
                called_number = f"{letter}-{number}"
                print(f"Calling number: {called_number}")
                
                # Add to called numbers in room state
                if 'called_numbers' not in room_state:
                    room_state['called_numbers'] = []
                
                # Add to called numbers
                room_state['called_numbers'].append({
                    'number': number,
                    'display': called_number,
                    'letter': letter
                })
                
                # Send the called number to all clients
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'number_called',
                        'number': number,
                        'display': called_number,
                        'letter': letter,
                        'called_numbers': [n['number'] for n in room_state['called_numbers']]
                    }
                )
                
                # Update the database with the newly called number
                try:
                    game.called_numbers.append(number)
                    await database_sync_to_async(game.save)()
                    print(f"Saved number {number} to database")
                except Exception as e:
                    print(f"Error updating called numbers in database: {e}")
                
                # Wait before calling next number
                await asyncio.sleep(3)  # 3 seconds between numbers
                
        except asyncio.CancelledError:
            print("Number calling was cancelled")
        except Exception as e:
            import traceback
            print(f"Error in call_numbers: {e}")
            print(traceback.format_exc())
        finally:
            room_state['calling_numbers'] = False
            room_state['number_calling_task'] = None
            print("Number calling finished")

    async def send_game_state(self):
        # Get current game state
        room = await self.get_room(self.room_name)
        if room:
            game = await self.get_current_game(room)
            if game:
                await self.send(text_data=json.dumps({
                    'type': 'game_state',
                    'status': 'in_progress' if game.is_active else 'ended',
                    'called_numbers': list(game.called_numbers)
                }))

    @database_sync_to_async
    def get_current_game(self, room):
        try:
            return Game.objects.filter(room=room).latest('created_at')
        except Game.DoesNotExist:
            return None

    async def start_countdown(self):
        """Handle the countdown before game starts"""
        room_state = self.room_states[self.room_name]
        
        try:
            # Reset countdown to initial value
            room_state['countdown'] = 30
            room_state['called_numbers'] = []  # Clear any previously called numbers
            
            # Initial countdown update
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'countdown_update',
                    'time_left': room_state['countdown'],
                    'message': f'Game starting in {room_state["countdown"]} seconds...'
                }
            )
            
            # Also send to card selection group
            await self.channel_layer.group_send(
                f'card_selection_{self.room_name}',
                {
                    'type': 'countdown_update',
                    'time_left': room_state['countdown'],
                    'message': f'Game starting in {room_state["countdown"]} seconds...'
                }
            )
            
            while room_state['countdown'] > 0 and not room_state['game_started'] and len(room_state['players']) >= 2:
                await asyncio.sleep(1)
                room_state['countdown'] -= 1
                
                # Send countdown update to all clients
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'countdown_update',
                        'time_left': room_state['countdown'],
                        'message': f'Game starting in {room_state["countdown"]} seconds...'
                    }
                )
                
                # Also send to card selection group
                await self.channel_layer.group_send(
                    f'card_selection_{self.room_name}',
                    {
                        'type': 'countdown_update',
                        'time_left': room_state['countdown'],
                        'message': f'Game starting in {room_state["countdown"]} seconds...'
                    }
                )
            
            # Only start the game if we have enough players and countdown reached zero
            if room_state['countdown'] <= 0 and len(room_state['players']) >= 2 and not room_state['game_started']:
                print("Countdown finished, starting game...")
                
                # Create new game and clear called numbers
                room = await self.get_room(self.room_name)
                if room:
                    # End any existing active games
                    await self.end_active_games(room)
                    
                    # Create new game
                    game = await self.start_game(room)
                    if game:
                        room_state['game_active'] = True
                        room_state['game_started'] = True
                        room_state['calling_numbers'] = False  # Reset calling numbers flag
                        
                        # Notify all clients that the game has started
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'game_started',
                                'message': 'Game started! No more players can join.'
                            }
                        )
                        
                        # Also notify card selection group
                        await self.channel_layer.group_send(
                            f'card_selection_{self.room_name}',
                            {
                                'type': 'game_started',
                                'message': 'Game started! Cards are no longer selectable.'
                            }
                        )
                        
                        # Start calling numbers after a short delay
                        await asyncio.sleep(1)
                        print("Starting number calling...")
                        await self.call_numbers()
        
        except asyncio.CancelledError:
            # Handle countdown cancellation
            print("Countdown was cancelled")
        except Exception as e:
            print(f"Error in countdown: {e}")
            await self.reset_game_state(room_state)
        finally:
            room_state['countdown_task'] = None

    @database_sync_to_async
    def end_active_games(self, room):
        """End any active games for the room"""
        try:
            active_games = Game.objects.filter(room=room, is_active=True)
            for game in active_games:
                game.is_active = False
                game.called_numbers = []  # Clear called numbers
                game.save()
        except Exception as e:
            print(f"Error ending active games: {e}")

    async def game_ended(self, event):
        """Handle game ended event"""
        try:
            print(f"Handling game ended event: {event}")
            # Send the complete game ended data to all players
            await self.send(text_data=json.dumps({
                'type': 'game_ended',
                'winner': event['winner'],
                'card_number': event['card_number'],
                'card_numbers': event['card_numbers'],
                'called_numbers': event['called_numbers'],
                'bonus': str(event['bonus']),  # Convert Decimal to string
                'total_stake': str(event['total_stake']),  # Convert Decimal to string
                'player_count': event['player_count'],
                'winning_pattern': event['winning_pattern'],
                'message': event['message']
            }))
        except Exception as e:
            print(f"Error in game_ended handler: {str(e)}")
            import traceback
            print(traceback.format_exc())

    async def game_started(self, event):
        """Handle game started event"""
        try:
            print("Handling game started event")
            await self.send(text_data=json.dumps({
                'type': 'game_started',
                'message': event.get('message', 'Game has started')
            }))
        except Exception as e:
            print(f"Error in game_started handler: {str(e)}")

    async def verify_bingo(self, card_numbers, called_numbers):
        """Verify if the bingo is valid based on predefined patterns."""
        try:
            print(f"\n=== BINGO Verification Debug ===")
            print(f"Card numbers (5x5 grid): {card_numbers}")
            print(f"Called numbers: {called_numbers}")
            
            # Convert called_numbers to a set for faster lookup
            called_set = set(called_numbers)
            print(f"Called set: {called_set}")

            # Define winning patterns (list of index lists)
            patterns = [
                # Four Corners
                [0, 4, 20, 24],  # Top-left, Top-right, Bottom-left, Bottom-right

                # Horizontal Lines (5 rows)
                [0, 1, 2, 3, 4],      # First row
                [5, 6, 7, 8, 9],      # Second row
                [10, 11, 13, 14], # Third row
                [15, 16, 17, 18, 19], # Fourth row
                [20, 21, 22, 23, 24], # Fifth row

                # Vertical Lines (5 columns)
                [0, 5, 10, 15, 20],   # First column
                [1, 6, 11, 16, 21],   # Second column
                [2, 7, 17, 22],   # Third column
                [3, 8, 13, 18, 23],   # Fourth column
                [4, 9, 14, 19, 24],   # Fifth column

                # Diagonal Lines
                [0, 6, 18, 24],   # Diagonal (\)
                [4, 8, 16, 20]    # Diagonal (/)
            ]

            # Check if any pattern is fully marked
            for pattern in patterns:
                pattern_numbers = [card_numbers[i] for i in pattern]
                print(f"Checking pattern: {pattern_numbers}")
                # Check if all numbers in the pattern are in the called numbers
                if all(num in called_set for num in pattern_numbers):
                    print(f"Found winning pattern: {pattern_numbers}")
                    return True, pattern

            print("No winning pattern found")
            return False, None

        except Exception as e:
            print(f"Error in verify_bingo: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False, None

    async def handle_bingo_declaration(self, data):
        username = data.get('username')
        room_name = data.get('room_name')
        card_numbers = data.get('card_numbers', [])
        
        try:
            # Get the game and room
            room = await self.get_room(room_name)
            game = await self.get_game(room_name)
            
            if not game or not room:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Game or room not found'
                }))
                return

            # Check if game is still active
            if not game.is_active:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Game has already ended'
                }))
                return

            # Get the player's card number
            player = await database_sync_to_async(Player.objects.get)(room=room, user__username=username)
            card_number = player.card_number

            # Verify the bingo
            is_valid, winning_pattern = await self.verify_bingo(card_numbers, game.called_numbers)
            
            if is_valid:
                # Stop number calling and end game
                room_state = self.room_states.get(room_name, {})
                room_state['calling_numbers'] = False
                room_state['game_active'] = False
                room_state['game_started'] = False
                
                # Update game state
                game.is_active = False
                game.winner = await database_sync_to_async(lambda: player.user)()
                await database_sync_to_async(game.save)()
                
                # Calculate total stake amount
                total_stake = room.stake * len(room_state['players'])
                
                # Calculate bonus based on number of players
                if len(room_state['players']) <= 3:
                    bonus = total_stake
                else:
                    bonus = int(total_stake * 0.8)
                
                # Update player's balance with bonus
                await self.update_player_balance(username, bonus)
                
                # Create game over data
                game_over_data = {
                    'type': 'game_ended',
                    'winner': username,
                    'card_number': card_number,
                    'card_numbers': card_numbers,
                    'called_numbers': game.called_numbers,
                    'bonus': str(bonus),
                    'total_stake': str(total_stake),
                    'player_count': len(room_state['players']),
                    'winning_pattern': winning_pattern,
                    'message': f'{username} has won the game!'
                }
                
                # Broadcast to all players in the game group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    game_over_data
                )
                
                # Also broadcast to card selection group
                await self.channel_layer.group_send(
                    f'card_selection_{room_name}',
                    game_over_data
                )
                
                # Play win sound
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'play_sound',
                        'sound': 'bingo'
                    }
                )
                try:
                    room = await self.get_room(room_name)
                    players = await database_sync_to_async(
                        lambda: list(Player.objects.select_related('user').filter(room=room))
                    )()

                    def clear_card(player):
                        player.card_number = None
                        player.save()

                    for player in players:
                        if player.card_number:
                            await self.channel_layer.group_send(
                                f'card_selection_{room_name}',
                                {
                                    'type': 'card_released',
                                    'card_number': player.card_number,
                                    'username': player.user.username,
                                    'game_ended': True
                                }
                            )
                        await database_sync_to_async(clear_card)(player)
                except Exception as e:
                    print(f"Error clearing card selections: {e}")
                # Wait before resetting game state
                await asyncio.sleep(10)  # Give players 10 seconds to see the results
                
                # Reset the game state
                #await self.reset_game_state(room_state)
        except Exception as e:
            print(f"Error in handle_bingo_declaration: {e}")
            import traceback
            print(traceback.format_exc())

    # In BingoConsumer class
    async def game_over(self, event):
        """Handle game over event"""
        try:
            print(f"Handling game over event: {event}")
            await self.send(text_data=json.dumps({
                'type': 'game_over',
                'winner': event['winner'],
                'card_number': event['card_number'],
                'card_numbers': event['card_numbers'],
                'called_numbers': event['called_numbers'],
                'bonus': event['bonus'],
                'total_stake': event['total_stake'],
                'player_count': event['player_count'],
                'winning_pattern': event['winning_pattern'],
                'message': event['message']
            }))
        except Exception as e:
            print(f"Error in game_over handler: {str(e)}")
            import traceback
            print(traceback.format_exc())

    # In BingoConsumer class
    async def game_reset(self, event):
        """Handle game reset event"""
        try:
            print("Handling game reset event")
            await self.send(text_data=json.dumps({
                'type': 'game_reset',
                'message': event.get('message', 'Game has been reset')
            }))
        except Exception as e:
            print(f"Error in game_reset handler: {str(e)}")
    # This handles the "game_started" event and sends it to all clients
    async def game_started(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_started'
        }))
    async def handle_active_cards_request(self, data):
        """Handle request for active cards from card selection room"""
        try:
            # Get current active game
            room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
            game = await database_sync_to_async(
                lambda: Game.objects.filter(room=room, is_active=True).first()
            )()
            
            if game:
                # Get all players with cards in this game
                players = await database_sync_to_async(
                    lambda: list(Player.objects.filter(game=game).exclude(card_number__isnull=True))
                )()
                active_cards = [p.card_number for p in players]
            else:
                active_cards = []
                
            # Send response back
            await self.send(text_data=json.dumps({
                'type': 'active_cards_response',
                'active_cards': active_cards
            }))
        except Exception as e:
            print(f"Error handling active cards request: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to get active cards'
            }))
    async def request_active_cards(self, event):
        """
        Handle request for active cards from card selection room.
        Responds with currently active card numbers in this game.
        """
        try:
            # Get the current game
            game = await database_sync_to_async(
                lambda: Game.objects.filter(room__room_name=self.room_name, is_active=True).first()
            )()
            
            if game:
                # Get all players with cards in this game
                players = await database_sync_to_async(
                    lambda: list(Player.objects.filter(game=game).exclude(card_number__isnull=True))
                )()
                active_cards = [p.card_number for p in players]
            else:
                active_cards = []
                
            # Send response back to the requesting channel
            await self.channel_layer.send(
                event['channel_name'],
                {
                    'type': 'active_cards_response',
                    'active_cards': active_cards
                }
            )
        except Exception as e:
            print(f"Error handling active cards request: {e}")

    @database_sync_to_async
    def get_active_cards_in_game(self):
        """Get all card numbers currently in use in this game"""
        if not hasattr(self, 'game'):
            return []
            
        return list(Player.objects.filter(
            game=self.game,
            card_number__isnull=False
        ).values_list('card_number', flat=True))
          
class CardSelectionConsumer(AsyncWebsocketConsumer):
    room_states = {}
    taken_cards = {}  # {room_name: set(card_numbers)}
 
    async def update_room_selected_cards(self, card_id, username):
        state = self.room_states[self.room_name]
        state['selected_cards'][card_id] = username
        await self.send_selected_cards_update()

    async def remove_room_selected_card(self, card_id):
        state = self.room_states[self.room_name]
        if card_id in state['selected_cards']:
            del state['selected_cards'][card_id]
        await self.send_selected_cards_update()

    async def send_selected_cards_update(self):
        selected_cards = list(self.room_states[self.room_name]['selected_cards'].keys())
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'selected_cards_update',
                'selected_cards': selected_cards
            }
        )

    async def selected_cards_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'selected_cards_update',
            'selected_cards': event['selected_cards']
        }))

    
    async def send_game_state(self):
        """Send current game state to client"""
        room_state = await self.get_room_state()
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'game_started': room_state.get('game_started', False),
            'countdown': room_state.get('countdown', 30),  # Use room_state's countdown
            'taken_cards': room_state.get('taken_cards', []),
            'player_count': room_state.get('player_count', 0)
        }))

    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'card_selection_{self.room_name}'
        self.user = self.scope['user']
        # Clear any previously selected card if not in an active game

        # Initialize instance attributes
        self.game_started = False
        self.countdown = 30  # Initialize countdown attribute
        self.selected_cards = {}
        
        # Initialize room state if it doesn't exist
        if self.room_name not in self.room_states:
            self.room_states[self.room_name] = {
                'game_started': False,
                'selected_cards': {},
                'countdown': 30,
                'player_count': 0
            }
        # Initialize taken cards for this room if not exists
        if self.room_name not in self.taken_cards:
            self.taken_cards[self.room_name] = set()
            
        # Get all active games in this room and their cards
        active_cards = await self.get_active_cards_for_room()
        self.taken_cards[self.room_name].update(active_cards)

        # Get current game state from database
        room_state = await self.get_room_state()
        self.game_started = room_state.get('game_started', False)
        
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        
        await self.accept()
        try:
            room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
            player = await database_sync_to_async(Player.objects.get)(room=room, user=self.user)

            if not player.game or not player.game.is_active:
                if player.card_number:
                    card_number = player.card_number

                    # Broadcast deselection to other clients
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'card_deselected',
                            'card_number': card_number,
                            'username': self.user.username
                        }
                    )

                    # Clear card in database
                    def clear_card(p):
                        p.card_number = None
                        p.save()
                    await database_sync_to_async(clear_card)(player)

        except Exception as e:
            print(f"[CONNECT] Error clearing stale card selection: {e}")
        # Immediately send game state to client
        
        await self.send_game_state()
        await asyncio.sleep(0.1)
        
        await self.send(text_data=json.dumps({
            'type': 'selected_cards_update',
            'selected_cards': list(self.room_states[self.room_name]['selected_cards'].keys())
        }))

        # Send current taken cards to the new client
        await self.send_taken_cards_update()
        await self.send_full_state()


        
        # If game has started, notify this client specifically
        if self.game_started:
            await self.send(text_data=json.dumps({
                'type': 'game_started',
                'message': 'Game has already started. You cannot join now.'
            }))
        await self.channel_layer.send(
            f'game_{self.room_name}',
            {
                'type': 'request_active_cards',
                'channel_name': self.channel_name
            }
        )
    async def send_full_state(self):
        """Send complete current state to client"""
        # Game state
        room_state = await self.get_room_state()
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'game_started': room_state['game_started'],
            'countdown': room_state['countdown']
        }))
        
        # Taken cards
        await self.send(text_data=json.dumps({
            'type': 'taken_cards_update',
            'taken_cards': list(self.taken_cards.get(self.room_name, set()))
        }))
        
        # Selected cards
    async def active_cards_response(self, event):
        """Handle response with active cards from game room"""
        active_cards = event.get('active_cards', [])
        if active_cards:
            # Update our local state of taken cards
            self.taken_cards[self.room_name].update(active_cards)
            # Broadcast the update to all clients
            await self.send_taken_cards_update()
    @database_sync_to_async
    def get_active_cards_for_room(self):
        """Get all cards currently in active games for this room"""
        from .models import Game
        # First get all active games in this room
        
        active_games = Game.objects.filter(
            room__room_name=self.room_name,
            is_active=True
        )
        active_players = Player.objects.filter(
            room__room_name=self.room_name,
            game__in=active_games
        ).exclude(card_number__isnull=True)
        
        return set(active_players.values_list('card_number', flat=True))
    async def send_taken_cards_update(self):
        """Send current taken cards to all clients in room"""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'taken_cards_update',  # This matches the handler name
                'taken_cards': list(self.taken_cards.get(self.room_name, []))
            }
        )
    async def taken_cards_update(self, event):
        """Handle updates to the list of taken cards"""
        taken_cards = event.get('taken_cards', [])
        self.taken_cards[self.room_name] = set(taken_cards)
        
        # Send the update to the client
        await self.send(text_data=json.dumps({
            'type': 'taken_cards_update',
            'taken_cards': taken_cards
        }))
            
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection and leave room group"""
        try:
            room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
            player = await database_sync_to_async(Player.objects.get)(room=room, user=self.user)
            card_number = player.card_number

            # Only proceed if not in an active game
            if not player.game or not player.game.is_active:
                if card_number:
                    # ✅ Remove from in-memory taken_cards
                    if card_number in self.taken_cards.get(self.room_name, set()):
                        self.taken_cards[self.room_name].remove(card_number)
                        await self.send_taken_cards_update()

                    # ✅ Remove from in-memory selected_cards
                    if self.room_name in self.room_states:
                        selected_cards = self.room_states[self.room_name]['selected_cards']
                        if card_number in selected_cards:
                            del selected_cards[card_number]

                    # ✅ Broadcast deselection to all clients
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'card_deselected',
                            'card_number': card_number,
                            'username': self.user.username
                        }
                    )

                    # ✅ Clear from database
                    player.card_number = None
                    await database_sync_to_async(player.save)()

        except Exception as e:
            print(f"Error clearing card on disconnect: {e}")

        # ✅ Always leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            # Always check game state first
            room_state = await self.get_room_state()
            
            if data['type'] == 'active_cards_response':
                # Update taken cards from response
                active_cards = data.get('active_cards', [])
                self.taken_cards[self.room_name].update(active_cards)
                await self.send_taken_cards_update()
            elif data.get('type') == 'card_activated':
                self.taken_cards[self.room_name].add(data['card_number'])
                await self.send_taken_cards_update()

            
            elif message_type == 'active_cards_update':
                # Update UI based on active cards
                active_cards = set(data.get('active_cards', []))
                self.taken_cards = active_cards
                await self.update_card_buttons(active_cards)
            elif message_type == 'get_state':
                await self.send_game_state()
                await self.send_taken_cards_update()

                # Also send selected cards for full state on reconnect
                selected_cards = list(self.room_states[self.room_name]['selected_cards'].keys())
                await self.send(text_data=json.dumps({
                    'type': 'selected_cards_update',
                    'selected_cards': selected_cards
                }))

            elif message_type == 'deselect_card':
                card_id = data.get('card_id')
                await self.update_player_card(None)

                # remove from temporary selection
                await self.remove_room_selected_card(card_id)

                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'card_deselected',
                        'card_number': card_id,
                        'username': self.user.username
                    }
                )


            elif message_type == 'select_card':
                if room_state.get('game_started', False):
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Game has already started. No more card selections allowed.'
                    }))
                    return
                card_id = data.get('card_id')
                if card_id:
                    # Get current player's card
                    try:
                        room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
                        player = await database_sync_to_async(Player.objects.get)(room=room, user=self.user)
                        
                        if player.card_number and player.card_number != card_id:
                            # Remove previous from selected_cards
                            await self.remove_room_selected_card(player.card_number)

                            # Notify others
                            await self.channel_layer.group_send(
                                self.room_group_name,
                                {
                                    'type': 'card_deselected',
                                    'card_number': player.card_number,
                                    'username': self.user.username
                                }
                            )
                    except Player.DoesNotExist:
                        pass
                    except Exception as e:
                        print(f"Error getting player: {e}")

                # Update player's card selection in database
                await self.update_player_card(card_id)
                await self.update_room_selected_cards(card_id, self.user.username)
                
                # Broadcast card selection to all players
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'card_selected',
                        'card_number': card_id,
                        'username': self.user.username
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Unknown message type: {message_type}'
                }))
        except Exception as e:
            print(f"Error receiving message: {e}")

    async def card_selected(self, event):
        """Handle card_selected event from room group"""
        await self.send(text_data=json.dumps({
            'type': 'card_selected',
            'card_number': event['card_number'],
            'username': event['username']
        }))

    async def card_deselected(self, event):
        """Handle card_deselected event from room group"""
        await self.send(text_data=json.dumps({
            'type': 'card_deselected',
            'card_number': event['card_number'],
            'username': event['username']
        }))

    async def countdown_update(self, event):
        """Handle countdown updates from BingoConsumer"""
        self.countdown = event['time_left']
        await self.send(text_data=json.dumps({
            'type': 'countdown_update',
            'time_left': self.countdown,
            'message': event['message']
        }))

    # In consumers.py - CardSelectionConsumer
    async def game_started(self, event):
        """Handle game started event"""
        self.game_started = True
        
        # Clear any existing countdown
        if hasattr(self, 'countdown_task'):
            self.countdown_task.cancel()
        
        # Notify all clients
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_started',
                'message': 'Game started! Cards are no longer selectable.'
            }
        )
        
        # Also send to the current client
        await self.send(text_data=json.dumps({
            'type': 'game_started',
            'message': 'Game started! Cards are no longer selectable.'
        }))

    async def game_ended(self, event):
        """Handle game ended event"""
        self.game_started = False
        
        # Clear all card selections
        try:
            room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
            players = await database_sync_to_async(
                lambda: list(Player.objects.select_related('user').filter(room=room))
            )()

            def clear_card(player):
                player.card_number = None
                player.save()

            for player in players:
                if player.card_number:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'card_released',
                            'card_number': player.card_number,
                            'username': player.user.username
                        }
                    )
                await database_sync_to_async(clear_card)(player)
            
            # Reset room state
            if self.room_name in self.room_states:
                self.room_states[self.room_name] = {
                    'game_started': False,
                    'selected_cards': {},
                    'player_count': len(players)
                }
            # Clear taken cards in memory
            self.taken_cards[self.room_name] = set()
                    
        except Exception as e:
            print(f"Error clearing cards on game end: {e}")
        
        # Notify all clients
        await self.send(text_data=json.dumps({
            'type': 'game_ended',
            'message': 'Game has ended. You can now select cards.'
        }))
    async def game_state_update(self, event):
        """Handle updates from game room about card status"""
        card_number = event.get('card_number')
        action = event.get('action')  # 'add' or 'remove'
        
        if action == 'add' and card_number not in self.taken_cards.get(self.room_name, set()):
            self.taken_cards[self.room_name].add(card_number)
        elif action == 'remove' and card_number in self.taken_cards.get(self.room_name, set()):
            self.taken_cards[self.room_name].remove(card_number)
            
        await self.send_taken_cards_update()

    async def game_reset(self, event):
        """Handle game reset event when there are not enough players"""
        try:
            self.game_started = False
            self.countdown = 30

            room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
            players = await database_sync_to_async(
                lambda: list(Player.objects.select_related('user').filter(room=room))
            )()

            def clear_card(player):
                player.card_number = None
                player.save()

            for player in players:
                if player.card_number:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'card_deselected',
                            'card_number': player.card_number,
                            'username': player.user.username
                        }
                    )
                await database_sync_to_async(clear_card)(player)

            # Reset room state
            if self.room_name in self.room_states:
                self.room_states[self.room_name] = {
                    'game_started': False,
                    'selected_cards': {},
                    'player_count': len(players)
                }

            await self.send_game_state()
            await self.send(text_data=json.dumps({
                'type': 'game_reset',
                'message': event['message']
            }))
            # Clear taken cards in memory
            self.taken_cards[self.room_name] = set()

        except Exception as e:
            print(f"Error clearing card selections: {e}")


    async def update_player_card(self, card_number):
        """Update player's card selection in database"""
        try:
            room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
            player, created = await database_sync_to_async(Player.objects.get_or_create)(
                user=self.user,
                room=room,
                defaults={'card_number': card_number}
            )
            if not created:
                # Broadcast deselection of previous card if it exists
                if player.card_number and player.card_number != card_number:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'card_deselected',
                            'card_number': player.card_number,
                            'username': self.user.username
                        }
                    )
                
                player.card_number = card_number
                await database_sync_to_async(player.save)()
                
                # Broadcast selection of new card
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'card_selected',
                        'card_number': card_number,
                        'username': self.user.username
                    }
                )
        except Exception as e:
            print(f"Error updating player card: {e}")

    @database_sync_to_async
    def get_room_state(self):
        try:
            room = Room.objects.get(room_name=self.room_name)
            game = Game.objects.filter(room=room, is_active=True).first()
            players = Player.objects.filter(room=room)

            player_count = players.count()
            return {
                'game_started': game is not None and player_count >= 2,
                'countdown': 30,
                'taken_cards': list(self.taken_cards.get(self.room_name, set())),
                'player_count': player_count
            }
        except Room.DoesNotExist:
            return {
                'game_started': False,
                'countdown': 30,
                'taken_cards': [],
                'player_count': 0
            }

        
class GameConsumer(AsyncWebsocketConsumer):
    # Class-level storage for game state
    room_states = {}  # room_name -> {'players': set(), 'countdown_task': None, 'game_active': False, 'game_started': False, 'called_numbers': [], 'countdown': 30}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_name = None
        self.room_group_name = None

    @database_sync_to_async
    def get_room(self):
        """Get room instance for the current room"""
        try:
            return Room.objects.get(room_name=self.room_name)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def get_game(self, room_name):
        """Get the current active game for the room"""
        try:
            room = Room.objects.get(room_name=room_name)
            return Game.objects.filter(room=room, is_active=True).first()
        except (Room.DoesNotExist, Game.DoesNotExist):
            return None

    async def start_countdown(self):
        """Handle the countdown before game starts"""
        room_state = self.room_states[self.room_name]
        
        try:
            # Reset countdown to initial value
            room_state['countdown'] = 30
            room_state['called_numbers'] = []  # Clear any previously called numbers
            
            # Initial countdown update
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'countdown_update',
                    'time_left': room_state['countdown'],
                    'message': f'Game starting in {room_state["countdown"]} seconds...'
                }
            )
            
            # Also send to card selection group
            await self.channel_layer.group_send(
                f'card_selection_{self.room_name}',
                {
                    'type': 'countdown_update',
                    'time_left': room_state['countdown'],
                    'message': f'Game starting in {room_state["countdown"]} seconds...'
                }
            )
            
            while room_state['countdown'] > 0 and not room_state['game_started'] and len(room_state['players']) >= 2:
                await asyncio.sleep(1)
                room_state['countdown'] -= 1
                
                # Send countdown update to all clients
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'countdown_update',
                        'time_left': room_state['countdown'],
                        'message': f'Game starting in {room_state["countdown"]} seconds...'
                    }
                )
                
                # Also send to card selection group
                await self.channel_layer.group_send(
                    f'card_selection_{self.room_name}',
                    {
                        'type': 'countdown_update',
                        'time_left': room_state['countdown'],
                        'message': f'Game starting in {room_state["countdown"]} seconds...'
                    }
                )
            
            # Only start the game if we have enough players and countdown reached zero
            if room_state['countdown'] <= 0 and len(room_state['players']) >= 2 and not room_state['game_started']:
                print("Countdown finished, starting game...")
                
                # Create new game and clear called numbers
                room = await self.get_room(self.room_name)
                if room:
                    # End any existing active games
                    await self.end_active_games(room)
                    
                    # Create new game
                    game = await self.start_game(room)
                    if game:
                        room_state['game_active'] = True
                        room_state['game_started'] = True
                        room_state['calling_numbers'] = False  # Reset calling numbers flag
                        
                        # Notify all clients that the game has started
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'game_started',
                                'message': 'Game started! No more players can join.'
                            }
                        )
                        
                        # Also notify card selection group
                        await self.channel_layer.group_send(
                            f'card_selection_{self.room_name}',
                            {
                                'type': 'game_started',
                                'message': 'Game started! Cards are no longer selectable.'
                            }
                        )
                        
                        # Start calling numbers after a short delay
                        await asyncio.sleep(1)
                        print("Starting number calling...")
                        await self.call_numbers()
        
        except asyncio.CancelledError:
            # Handle countdown cancellation start_game
            print("Countdown was cancelled")
        except Exception as e:
            print(f"Error in countdown: {e}")
            await self.reset_game_state(room_state)
        finally:
            room_state['countdown_task'] = None

    @database_sync_to_async
    def end_active_games(self, room):
        """End any active games for the room"""
        try:
            active_games = Game.objects.filter(room=room, is_active=True)
            for game in active_games:
                game.is_active = False
                game.called_numbers = []  # Clear called numbers
                game.save()
        except Exception as e:
            print(f"Error ending active games: {e}")

    async def start_game(self, room):
        """Start a new game for the room"""
        try:
            # Create a new game
            game = await database_sync_to_async(Game.objects.create)(room=room)
            
            # Ensure called numbers are empty
            game.called_numbers = []
            await database_sync_to_async(game.save)()
            
            # Reset room state
            if self.room_name in self.room_states:
                room_state = self.room_states[self.room_name]
                room_state.update({
                    'game_active': True,
                    'game_started': True,
                    'called_numbers': [],
                    'calling_numbers': False,
                    'number_calling_task': None
                })
            
            return game
        except Exception as e:
            print(f"Error starting game: {e}")
            return None

    async def call_numbers(self):
        """Call random numbers for the bingo game"""
        if not self.room_name:
            print("Room name not set. Cannot call numbers.")
            return

        room_state = self.room_states.get(self.room_name, {})
        if not room_state:
            print(f"No room state found for {self.room_name}")
            return
            
        if room_state.get('calling_numbers') or not room_state.get('game_active'):
            print(f"Not starting number calling. calling_numbers: {room_state.get('calling_numbers')}, game_active: {room_state.get('game_active')}")
            return
            
        room_state['calling_numbers'] = True
        
        try:
            # Get the current game
            game = await self.get_game(self.room_name)
            if not game:
                print(f"No active game found for room: {self.room_name}")
                return

            # Ensure called numbers are empty
            game.called_numbers = []
            await database_sync_to_async(game.save)()
            print("Initialized empty called numbers list")

            # Generate all possible numbers (1-75 for standard bingo)
            all_numbers = list(range(1, 76))
            available_numbers = all_numbers.copy()  # Start with all numbers available
            random.shuffle(available_numbers)
            
            print(f"Starting number calling with {len(available_numbers)} available numbers")
            
            # Call numbers one by one with a delay
            for number in available_numbers:
                # Check if game is still active and has enough players
                if not room_state.get('game_active', False) or len(room_state['players']) < 2:
                    print("Game no longer active or not enough players, stopping number calling")
                    break
                
                # Get the BINGO letter for the number
                letter = self.get_bingo_letter(number)
                called_number = f"{letter}-{number}"
                print(f"Calling number: {called_number}")
                
                # Add to called numbers in room state
                if 'called_numbers' not in room_state:
                    room_state['called_numbers'] = []
                
                # Add to called numbers
                room_state['called_numbers'].append({
                    'number': number,
                    'display': called_number,
                    'letter': letter
                })
                
                # Send the called number to all clients
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'number_called',
                        'number': number,
                        'display': called_number,
                        'letter': letter,
                        'called_numbers': [n['number'] for n in room_state['called_numbers']]
                    }
                )
                
                # Update the database with the newly called number
                try:
                    game.called_numbers.append(number)
                    await database_sync_to_async(game.save)()
                    print(f"Saved number {number} to database")
                except Exception as e:
                    print(f"Error updating called numbers in database: {e}")
                
                # Wait before calling next number
                await asyncio.sleep(3)  # 3 seconds between numbers
                
        except asyncio.CancelledError:
            print("Number calling was cancelled")
        except Exception as e:
            import traceback
            print(f"Error in call_numbers: {e}")
            print(traceback.format_exc())
        finally:
            room_state['calling_numbers'] = False
            room_state['number_calling_task'] = None
            print("Number calling finished")

    async def send_game_state(self):
        """Send the current game state to the client"""
        game_state = await self.get_room_state()
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'game_state': game_state
        }))

    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'game_{self.room_name}'
        
        # Add the channel to the group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Initialize room state if it doesn't exist
        if self.room_name not in self.room_states:
            self.room_states[self.room_name] = {
                'players': set(),
                'game_active': False,
                'game_started': False,
                'called_numbers': [],
                'countdown': 30,
                'countdown_task': None,
                'calling_numbers': False
            }
        
        # Add the user to the room
        user = self.scope['user']
        if user.is_authenticated:
            self.room_states[self.room_name]['players'].add(user.username)
            
            # Update player count for all clients
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_count_update',
                    'count': len(self.room_states[self.room_name]['players']),
                    'message': f'{user.username} joined the game.'
                }
            )
            
            # Start the countdown if we have enough players and no countdown is running
            room_state = self.room_states[self.room_name]
            if (len(room_state['players']) >= 2 and 
                not room_state['game_started'] and 
                not room_state['countdown_task']):
                room_state['countdown_task'] = asyncio.create_task(self.start_countdown())
        
        await self.accept()
        
        # Send the current game state to the client
        await self.send_game_state()

    async def disconnect(self, close_code):
        if not hasattr(self, 'room_name') or self.room_name not in self.room_states:
            return
            
        room_state = self.room_states[self.room_name]
        user = self.scope['user']
        
        try:
            if user.is_authenticated and user.username in room_state['players']:
                room_state['players'].remove(user.username)
                # Try to clear their card if they had one
                try:
                    room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
                    player = await database_sync_to_async(Player.objects.get)(room=room, user=user)

                    if player.card_number:
                        card_number = player.card_number

                        # Broadcast to card selection group
                        await self.channel_layer.group_send(
                            f"card_selection_{self.room_name}",
                            {
                                'type': 'card_deselected',
                                'card_number': card_number,
                                'username': user.username
                            }
                        )

                        # Clear card in DB
                        def clear_card(p):
                            p.card_number = None
                            p.save()
                        await database_sync_to_async(clear_card)(player)

                except Exception as e:
                    print(f"[DISCONNECT] Failed to clear card for {user.username}: {e}")

                # Update player count for remaining players
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'player_count_update',
                        'count': len(room_state['players']),
                        'message': f'Player left: {user.username} ({len(room_state["players"])}/2)'
                    }
                )
                
                # If less than 2 players, reset the game and stop number calling
                if len(room_state['players']) < 2:
                    print(f"Less than 2 players remaining, resetting game...")
                    
                    # Stop number calling if it's running
                    if room_state.get('calling_numbers', False):
                        print("Stopping number calling...")
                        room_state['calling_numbers'] = False
                        
                        # Cancel any running number calling task
                        if room_state.get('number_calling_task'):
                            if not room_state['number_calling_task'].done():
                                room_state['number_calling_task'].cancel()
                                try:
                                    await room_state['number_calling_task']
                                except asyncio.CancelledError:
                                    pass
                    
                    # Reset game state
                    room_state.update({
                        'game_active': False,
                        'game_started': False,
                        'called_numbers': [],
                        'countdown': 30,
                        'countdown_task': None,
                        'calling_numbers': False,
                        'number_calling_task': None
                    })
                    
                    # Notify all clients about game reset
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'game_reset',
                            'message': 'Game reset: Not enough players. Waiting for more players...'
                        }
                    )
                    
                    # Clear called numbers from database
                    try:
                        room = await database_sync_to_async(Room.objects.get)(room_name=self.room_name)
                        game = await database_sync_to_async(lambda: getattr(room, 'game', None))()
                        if game:
                            await database_sync_to_async(game.called_numbers.clear)()
                    except Exception as e:
                        print(f"Error clearing called numbers: {e}")
                
                # Reset game if no players left
                if not room_state['players']:
                    if room_state['countdown_task']:
                        room_state['countdown_task'].cancel()
                    del self.room_states[self.room_name]
        finally:
            # Always clean up the connection
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')
        message_type = data.get('type')

        print(f"Received message: {data}")  # Debug log
        
        if message_type == 'start_new_game':
            # Handle start new game request
            room_state = self.room_states.get(self.room_name, {})
            room_state.update({
                'game_active': False,
                'game_started': False,
                'called_numbers': [],
                'calling_numbers': False,
                'number_calling_task': None
            })
            
            # Notify all clients that the game has been reset
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_reset',
                    'message': 'Game has been reset. Starting new game...'
                }
            )
            
            # Start a new game
            await self.start_game_timer()
            
        elif action == 'declare_bingo':
            print("Handling bingo declaration...")  # Debug log
            await self.handle_bingo_declaration(data)
        elif action == 'start_countdown':
            if not self.game_active:
                if not self.countdown_task:
                    self.countdown_task = asyncio.create_task(self.start_countdown())
        elif action == 'number_called':
            await self.handle_number_called(data)
        elif action == 'game_ended':
            await self.game_ended(data)

    # In BingoConsumer class
    async def handle_bingo_declaration(self, data):
        username = data.get('username')
        room_name = data.get('room_name')
        card_numbers = data.get('card_numbers', [])
        
        try:
            # Get the game and room
            room = await self.get_room(room_name)
            game = await self.get_game(room_name)
            
            if not game or not room:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Game or room not found'
                }))
                return

            # Check if game is still active
            if not game.is_active:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Game has already ended'
                }))
                return

            # Get the player's card number
            player = await database_sync_to_async(Player.objects.get)(room=room, user__username=username)
            card_number = player.card_number

            # Verify the bingo
            is_valid, winning_pattern = await self.verify_bingo(card_numbers, game.called_numbers)
            
            if is_valid:
                # Stop number calling and end game
                room_state = self.room_states.get(room_name, {})
                room_state['calling_numbers'] = False
                room_state['game_active'] = False
                room_state['game_started'] = False
                
                # Update game state
                game.is_active = False
                game.winner = await database_sync_to_async(lambda: player.user)()
                await database_sync_to_async(game.save)()
                
                # Calculate total stake amount
                total_stake = room.stake * len(room_state['players'])
                
                # Calculate bonus based on number of players
                if len(room_state['players']) <= 3:
                    bonus = total_stake
                else:
                    bonus = int(total_stake * 0.8)
                
                # Update player's balance with bonus
                await self.update_player_balance(username, bonus)
                
                # Create game over data
                game_over_data = {
                    'type': 'game_ended',
                    'winner': username,
                    'card_number': card_number,
                    'card_numbers': card_numbers,
                    'called_numbers': game.called_numbers,
                    'bonus': str(bonus),
                    'total_stake': str(total_stake),
                    'player_count': len(room_state['players']),
                    'winning_pattern': winning_pattern,
                    'message': f'{username} has won the game!'
                }
                
                # Broadcast to all players in the game group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    game_over_data
                )
                
                # Also broadcast to card selection group
                await self.channel_layer.group_send(
                    f'card_selection_{room_name}',
                    game_over_data
                )
                
                # Play win sound
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'play_sound',
                        'sound': 'bingo'
                    }
                )
                
                # Wait before resetting game state
                await asyncio.sleep(10)  # Give players 10 seconds to see the results
                
                # Reset the game state
                await self.reset_game_state(room_state)
        except Exception as e:
            print(f"Error in handle_bingo_declaration: {e}")
            import traceback
            print(traceback.format_exc())

    @database_sync_to_async
    def get_room(self, room_name):
        """Get room instance"""
        try:
            return Room.objects.get(room_name=room_name)
        except Room.DoesNotExist:
            return None
            
    @database_sync_to_async
    def get_player_count(self, room_name):
        """Get number of players in the room"""
        return Player.objects.filter(room__room_name=room_name).count()
        
    async def update_player_balance(self, username, amount):
        """Update player's balance"""
        try:
            user = self.scope['user']
            if user.username == username:
                profile = await sync_to_async(lambda: user.profile)()
                profile.balance += amount
                await sync_to_async(profile.save)()
                
                # Send updated balance to the client
                await self.send(text_data=json.dumps({
                    'type': 'balance_update',
                    'balance': str(profile.balance)
                }))
                
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating balance: {str(e)}")
            return False
            
    async def verify_bingo(self, card_numbers, called_numbers):
        """Verify if the bingo is valid based on predefined patterns."""
        try:
            print(f"\n=== BINGO Verification Debug ===")
            print(f"Card numbers: {card_numbers}")
            print(f"Called numbers: {called_numbers}")

            # Ensure card has 25 items and center is free
            if len(card_numbers) != 25:
                print("Invalid card: must have 25 items.")
                return False, None
            if card_numbers[12] != '*':
                print("Invalid card: center must be '*'.")
                return False, None

            called_set = set(called_numbers)

            # Define winning patterns (index positions)
            patterns = [
                [0, 4, 20, 24],              # Four corners
                [0, 1, 2, 3, 4],             # Rows
                [5, 6, 7, 8, 9],
                [10, 11, 13, 14],
                [15, 16, 17, 18, 19],
                [20, 21, 22, 23, 24],
                [0, 5, 10, 15, 20],          # Columns
                [1, 6, 11, 16, 21],
                [2, 7, 17, 22],
                [3, 8, 13, 18, 23],
                [4, 9, 14, 19, 24],
                [0, 6, 18, 24],              # Diagonals
                [4, 8, 16, 20]
            ]

            for pattern in patterns:
                try:
                    pattern_numbers = [card_numbers[i] for i in pattern]
                except IndexError:
                    print(f"Invalid pattern indexes for card: {pattern}")
                    continue

                print(f"Checking pattern: {pattern_numbers}")
                if all(num in called_set or num == '*' for num in pattern_numbers):
                    print(f"🎉 Valid Bingo found! Pattern: {pattern}")
                    return True, pattern

            print("❌ No valid Bingo found.")
            await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Invalid BINGO! No winning pattern found.'
                }))
            return False, None

        except Exception as e:
            print(f"Error in verify_bingo: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False, None


    async def handle_number_called(self, data):
        number = data.get('number')
        room_name = data.get('room_name')
        
        # Get BINGO letter for the number
        letter = self.get_bingo_letter(number)
        display = f"{letter}{number}"

        try:
            # Get the current game
            game = await self.get_game(room_name)
            if not game:
                print(f"No game found for room: {room_name}")
                return

            # Update called numbers
            called_numbers = game.called_numbers or []
            if number not in called_numbers:
                called_numbers.append(number)
                game.called_numbers = called_numbers
                await self.save_game(game)
                print(f"Saved number {display} to game {game.id}")
            else:
                print(f"Number {display} already called in game {game.id}")

            # Broadcast number to all players
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'number_called',
                    'number': number,
                    'display': display,
                    'letter': letter,
                    'called_numbers': called_numbers
                }
            )
            
            # Play sound for the called number
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'play_sound',
                    'sound': 'number_called',
                    'number': number,
                    'letter': letter
                }
            )
        except Exception as e:
            print(f"Error in handle_number_called: {e}")
            
    async def play_sound(self, event):
        """Handle playing sounds for number calls and wins"""
        await self.send(text_data=json.dumps({
            'type': 'play_sound',
            'sound': event.get('sound'),
            'number': event.get('number'),
            'letter': event.get('letter')
        }))

    async def send_game_state(self):
        game_state = await self.get_room_state()
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'game_state': game_state
        }))

    async def bingo_declaration(self, event):
        username = event['username']
        await self.send(text_data=json.dumps({
            'type': 'bingo_declaration',
            'username': username
        }))

    async def player_count_update(self, event):
        """Handle player count updates"""
        await self.send(text_data=json.dumps({
            'type': 'player_count_update',
            'count': event.get('count', 0),
            'message': event.get('message', '')
        }))

    async def countdown_update(self, event):
        """Handle countdown updates"""
        await self.send(text_data=json.dumps({
            'type': 'countdown_update',
            'time_left': event.get('time_left', 30),
            'message': event.get('message', '')
        }))
        
    async def number_called(self, event):
        """Handle number called event"""
        await self.send(text_data=json.dumps({
            'type': 'number_called',
            'number': event['number'],
            'display': event.get('display', str(event['number'])),
            'letter': event.get('letter', ''),
            'called_numbers': event.get('called_numbers', [])
        }))

    async def game_reset(self, event):
        """Handle game reset event"""
        await self.send(text_data=json.dumps({
            'type': 'game_reset',
            'message': event['message']
        }))

    async def reset_game(self):
        """Reset the game state"""
        if self.countdown_task:
            self.countdown_task.cancel()
            self.countdown_task = None
        self.game_active = False
        self.game_started = False
        self.called_numbers = []
        self.countdown = 30
        self.players.clear()

    async def reset_game_state(self, room_state):
        """Reset the game state while keeping players"""
        # Cancel any running countdown task
        if room_state.get('countdown_task'):
            room_state['countdown_task'].cancel()
        
        # Stop number calling if it's running
        if room_state.get('calling_numbers', False):
            print("[reset_game_state] Stopping number calling...")
            room_state['calling_numbers'] = False
            
            # Cancel any running number calling task
            if room_state.get('number_calling_task'):
                if not room_state['number_calling_task'].done():
                    room_state['number_calling_task'].cancel()
                    try:
                        await room_state['number_calling_task']
                    except asyncio.CancelledError:
                        pass
        
        # Clear the number calling task
        room_state['number_calling_task'] = None
        
        room_state.update({
            'game_active': False,
            'game_started': False,
            'called_numbers': [],
            'countdown': 30,
            'countdown_task': None,
            'calling_numbers': False
        })
        
        # Clear any existing called numbers from the database if needed
        room_name = self.room_name
        if room_name and room_name.startswith('game_'):
            room_name = room_name[5:]  # Remove 'game_' prefix
            try:
                room = await database_sync_to_async(Room.objects.get)(name=room_name)
                game = await database_sync_to_async(lambda: getattr(room, 'game', None))()
                if game:
                    await database_sync_to_async(game.called_numbers.clear)()
            except (Room.DoesNotExist, Exception) as e:
                print(f"Error clearing called numbers: {e}")
        
        # Notify all clients that the game has been reset
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_reset',
                'message': 'Game has been reset. Waiting for players...'
            }
        )
        
        # Notify card selection group to clear cards
        await self.channel_layer.group_send(
            f'card_selection_{self.room_name}',
            {
                'type': 'game_ended',
                'message': 'Game reset: All cards are now available for selection.'
            }
        )

    async def start_countdown(self):
        """Handle the countdown before game starts"""
        room_state = self.room_states[self.room_name]
        
        try:
            # Reset countdown to initial value
            room_state['countdown'] = 30
            room_state['called_numbers'] = []  # Clear any previously called numbers
            
            # Initial countdown update
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'countdown_update',
                    'time_left': room_state['countdown'],
                    'message': f'Game starting in {room_state["countdown"]} seconds...'
                }
            )
            
            # Also send to card selection group
            await self.channel_layer.group_send(
                f'card_selection_{self.room_name}',
                {
                    'type': 'countdown_update',
                    'time_left': room_state['countdown'],
                    'message': f'Game starting in {room_state["countdown"]} seconds...'
                }
            )
            
            while room_state['countdown'] > 0 and not room_state['game_started'] and len(room_state['players']) >= 2:
                await asyncio.sleep(1)
                room_state['countdown'] -= 1
                
                # Send countdown update to all clients
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'countdown_update',
                        'time_left': room_state['countdown'],
                        'message': f'Game starting in {room_state["countdown"]} seconds...'
                    }
                )
                
                # Also send to card selection group
                await self.channel_layer.group_send(
                    f'card_selection_{self.room_name}',
                    {
                        'type': 'countdown_update',
                        'time_left': room_state['countdown'],
                        'message': f'Game starting in {room_state["countdown"]} seconds...'
                    }
                )
            
            # Only start the game if we have enough players and countdown reached zero
            if room_state['countdown'] <= 0 and len(room_state['players']) >= 2 and not room_state['game_started']:
                print("Countdown finished, starting game...")
                
                # Create new game and clear called numbers
                room = await self.get_room(self.room_name)
                if room:
                    # End any existing active games
                    await self.end_active_games(room)
                    
                    # Create new game
                    game = await self.start_game(room)
                    if game:
                        room_state['game_active'] = True
                        room_state['game_started'] = True
                        room_state['calling_numbers'] = False  # Reset calling numbers flag
                        
                        # Notify all clients that the game has started
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'game_started',
                                'message': 'Game started! No more players can join.'
                            }
                        )
                        
                        # Also notify card selection group
                        await self.channel_layer.group_send(
                            f'card_selection_{self.room_name}',
                            {
                                'type': 'game_started',
                                'message': 'Game started! Cards are no longer selectable.'
                            }
                        )
                        
                        # Start calling numbers after a short delay
                        await asyncio.sleep(1)
                        print("Starting number calling...")
                        await self.call_numbers()
        
        except asyncio.CancelledError:
            # Handle countdown cancellation
            print("Countdown was cancelled")
        except Exception as e:
            print(f"Error in countdown: {e}")
            await self.reset_game_state(room_state)
        finally:
            room_state['countdown_task'] = None

    @database_sync_to_async
    def end_active_games(self, room):
        """End any active games for the room"""
        try:
            active_games = Game.objects.filter(room=room, is_active=True)
            for game in active_games:
                game.is_active = False
                game.called_numbers = []  # Clear called numbers
                game.save()
        except Exception as e:
            print(f"Error ending active games: {e}")

    async def start_game(self, room):
        """Start a new game for the room"""
        try:
            # Create a new game
            game = await database_sync_to_async(Game.objects.create)(room=room)
            
            # Ensure called numbers are empty
            game.called_numbers = []
            await database_sync_to_async(game.save)()
            
            # Reset room state
            if self.room_name in self.room_states:
                room_state = self.room_states[self.room_name]
                room_state.update({
                    'game_active': True,
                    'game_started': True,
                    'called_numbers': [],
                    'calling_numbers': False,
                    'number_calling_task': None
                })
            
            return game
        except Exception as e:
            print(f"Error starting game: {e}")
            return None

    def get_bingo_letter(self, number):
        """Get the BINGO letter for a given number"""
        if 1 <= number <= 15:
            return 'B'
        elif 16 <= number <= 30:
            return 'I'
        elif 31 <= number <= 45:
            return 'N'
        elif 46 <= number <= 60:
            return 'G'
        elif 61 <= number <= 75:
            return 'O'
        return ''

    @database_sync_to_async
    def get_room_state(self):
        """Get the current room state from the database"""
        try:
            room = Room.objects.get(room_name=self.room_name)
            game = Game.objects.filter(room=room, is_active=True).first()
            if game:
                return {
                    'game_active': game.is_active,
                    'game_started': True,
                    'called_numbers': list(game.called_numbers) if game.called_numbers else [],
                    'countdown': 30,
                }
        except (Room.DoesNotExist, Exception) as e:
            print(f"Error getting room state: {e}")
        return {
            'game_active': False,
            'game_started': False,
            'called_numbers': [],
            'countdown': 30,
        }
    
    async def game_ended(self, event):
        """Handle game ended event"""
        try:
            print(f"Handling game ended event: {event}")
            self.game_active = False
            self.game_started = False
            self.called_numbers = []
            await self.send(text_data=json.dumps({
                'type': 'game_ended',
                'winner': event['winner'],
                'card_number': event['card_number'],
                'card_numbers': event['card_numbers'],
                'called_numbers': event['called_numbers'],
                'bonus': str(event['bonus']),  # Convert Decimal to string
                'total_stake': str(event['total_stake']),  # Convert Decimal to string
                'player_count': event['player_count'],
                'winning_pattern': event['winning_pattern'],
                'message': event['message']
            }))

            # Also notify card selection group to reset
            await self.channel_layer.group_send(
                f'card_selection_{self.room_name}',
                {
                    'type': 'game_reset',
                    'message': 'Game has ended. Cards are now available.'
                }
            )

        except Exception as e:
            print(f"Error in game_ended handler: {str(e)}")
            import traceback
            print(traceback.format_exc())
    async def game_started(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_started',
            'message': 'Game started! No more players can join.'
        }))
    async def request_active_cards(self, event):
        """
        Handle request for active cards from card selection room.
        Responds with currently active card numbers in this game.
        """
        try:
            # Get the current game
            game = await database_sync_to_async(
                lambda: Game.objects.filter(room__room_name=self.room_name, is_active=True).first()
            )()
            
            if game:
                # Get all players with cards in this game
                players = await database_sync_to_async(
                    lambda: list(Player.objects.filter(game=game).exclude(card_number__isnull=True))
                )()
                active_cards = [p.card_number for p in players]
            else:
                active_cards = []
                
            # Send response back to the requesting channel
            await self.channel_layer.send(
                event['channel_name'],
                {
                    'type': 'active_cards_response',
                    'active_cards': active_cards
                }
            )
        except Exception as e:
            print(f"Error handling active cards request: {e}")