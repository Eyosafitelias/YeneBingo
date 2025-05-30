    // Game state
    const VERSION = '1.0.0';
    let selectedCard = null;
    let socket = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 5;
    const RECONNECT_DELAY = 3000; // 3 seconds
    let gameStarted = false;
    let countdownInterval;
    let timerStarted = false;
    let currentUsername = document.getElementById('current-username').textContent.replace(/"/g, '');
    let timeLeft = 30; // Default time
    let takenCards = new Set();
    let gameEndedHandled = false;

    // Initialize WebSocket connection request_active_cards
    function initWebSocket() {
        const roomName = document.getElementById('room-name').textContent.replace(/"/g, '');
        const wsScheme = window.location.protocol === "https:" ? "wss://" : "ws://";
        const wsUrl = `${wsScheme}${window.location.host}/ws/bingo/card-selection/${roomName}/`;
        
        socket = new WebSocket(wsUrl);

        socket.onopen = function() {
            console.log('WebSocket connection established');
            reconnectAttempts = 0;
            
            // Request current game state when connecting
            socket.send(JSON.stringify({
                'type': 'get_state'
            }));
        };

        socket.onmessage = function(e) {
            try {
                const data = JSON.parse(e.data);
                console.log('Received WebSocket message:', data);
                if (data.type === 'selected_cards_update') {
                    const selected = data.selected_cards || [];
                    // First enable all cards
                    document.querySelectorAll('.card-button').forEach(button => {
                        button.disabled = false;
                        button.classList.remove('bg-red-600');
                        button.classList.add('bg-emerald-500')
                    });
                    
                    selected.forEach(cardNumber => {
                        const button = document.querySelector(`[data-card-number="${cardNumber}"]`);
                        if (button && cardNumber !== selectedCard) {
                            button.disabled = true;
                            button.classList.remove('bg-emerald-500');
                            button.classList.add('bg-red-600');
                        }
                    });
                }

                if (data.type === 'taken_cards_update' || data.type === 'active_cards_response') {
                    // Then disable taken cards
                    const cards = data.taken_cards || data.active_cards || [];
                    cards.forEach(cardNumber => {
                        const button = document.querySelector(`[data-card-number="${cardNumber}"]`);
                        if (button) {
                            button.disabled = true;
                            button.classList.remove('bg-emerald-500')
                            button.classList.add('bg-red-600');
                        }
                    });
                }

                // Handle immediate game started notification
                if (data.type === 'game_started' && data.message.includes('already started')) {
                    disableCardButtons();
                    showToast(data.message);
                    gameEndedHandled = false;
                    gameStarted = true;
                    return;
                }
                else if (data.type === 'game_ended') {
                    gameStarted = false;
                    enableCardButtons();
                    showToast(data.message || 'Game has ended. You can now select cards.');
                    
                    // Reset all cards to default state
                    document.querySelectorAll('.card-button').forEach(button => {
                        button.disabled = false;
                        button.classList.remove('bg-red-600', 'bg-blue-600');
                        button.classList.add('bg-emerald-500');
                    });
                }
                if (data.type === 'active_cards_update') {
                    // Disable buttons for active cards
                    data.active_cards.forEach(cardNumber => {
                        const button = document.querySelector(`[data-card-number="${cardNumber}"]`);
                        if (button) {
                            button.disabled = true;
                            button.classList.add('bg-red-600');
                        }
                    });
                }
                
                if (data.type === 'card_released') {
                    // Enable button when card is released
                    const button = document.querySelector(`[data-card-number="${data.card_number}"]`);
                    if (button) {
                        button.disabled = false;
                        button.classList.remove('bg-red-600');
                    }
                }
                

                switch(data.type) {
                    case 'card_selected':
                        const isSelf = data.username === currentUsername;
                        const cardNumber = data.card_number;

                        // Deselect the old card if this user had one selected
                        if (isSelf && selectedCard && selectedCard !== cardNumber) {
                            const prevButton = document.querySelector(`[data-card-number="${selectedCard}"]`);
                            if (prevButton) {
                                prevButton.classList.remove('bg-blue-600', 'bg-red-600');
                                prevButton.classList.add('bg-emerald-500');
                                prevButton.disabled = false;
                            }
                            selectedCard = null;
                        }

                        const button = document.querySelector(`[data-card-number="${cardNumber}"]`);
                        if (!button) break;

                        if (isSelf) {
                            selectedCard = cardNumber;
                            button.classList.remove('bg-emerald-500', 'bg-red-600');
                            button.classList.add('bg-blue-600');
                            button.disabled = false;
                        } else {
                            if (cardNumber !== selectedCard) {
                                button.classList.remove('bg-emerald-500', 'bg-blue-600');
                                button.classList.add('bg-red-600');
                                button.disabled = true;
                                takenCards.add(parseInt(cardNumber));
                            }
                        }
                        break;

                

                    case 'game_state':
                        // Also robustly enable all card buttons on game_state
                        document.querySelectorAll('.card-button').forEach(button => {
                            button.disabled = false;
                            button.classList.remove('bg-red-600');
                        });
                        break;
                    case 'card_deselected':
                        const diselected_card = document.querySelector(`[data-card-number="${data.card_number}"]`);
                        if (diselected_card) {
                            diselected_card.classList.remove('bg-red-600', 'bg-blue-600');
                            diselected_card.classList.add('bg-emerald-500');
                            diselected_card.disabled = false;
                            
                            // If this was our card, clear selection
                            if (data.username === currentUsername) {
                                selectedCard = null;
                                //document.getElementById('selectedCardDisplay').textContent = '0';
                            }
                            
                            // Update taken cards set
                            takenCards.delete(parseInt(data.card_number));
                            
                            // If game ended, reset game state
                            if (data.game_ended) {
                                gameStarted = false;
                                showToast('Game has ended. You can select a new card.');
                                
                                // Reset preview container
                                const previewContainer = document.getElementById('previewContainer');
                                previewContainer.innerHTML = `
                                    <div class="text-center">
                                        <i class="fas fa-dice-d20 text-3xl mb-2 text-emerald-400"></i>
                                        <p id="previewText" class="text-sm text-gray-300">Select a card to preview</p>
                                    </div>
                                `;
                            }
                        }
                        break;

                    case 'card_released':
                        const releasedButton = document.querySelector(`[data-card-number="${data.card_number}"]`);
                        if (releasedButton) {
                            releasedButton.classList.remove('bg-red-600', 'bg-blue-600');
                            releasedButton.classList.add('bg-emerald-500');
                            releasedButton.disabled = false;
                            
                            // If this was our card, clear selection
                            if (data.username === currentUsername) {
                                selectedCard = null;
                                //(null);
                                document.getElementById('selectedCardDisplay').textContent = '0';
                            }
                            
                            // Update taken cards set
                            takenCards.delete(parseInt(data.card_number));
                            
                            // If game ended, reset game state
                            if (data.game_ended) {
                                gameStarted = false;
                                showToast('Game has ended. You can select a new card.');
                            }
                        }
                        break;
                    
                    case 'countdown_update':
                        timeLeft = data.time_left;
                        document.getElementById('countdownValue').textContent = timeLeft;
                        //showToast(data.message);
                        
                        if (timeLeft <= 0) {
                            clearInterval(countdownInterval);
                            timerStarted = false;
                            gameStarted = true;
                        }
                        break;

                    case 'game_started':
                        gameStarted = true;
                        disableCardButtons();
                        showToast(data.message);
                        break;

                    case 'game_ended':
                        // Only process if we haven't already handled this game end
                        if (gameEndedHandled) break;
                        gameEndedHandled = true;

                        // Reset game state
                        gameStarted = false;
                        selectedCard = null;
                        takenCards.clear();
                        
                        // Check if current user is the winner
                        const isWinner = data.winner === currentUsername;
                        
                        // Update UI immediately for all players
                        document.querySelectorAll('.card-button').forEach(button => {
                            button.disabled = false;
                            button.classList.remove('bg-red-600', 'bg-blue-600');
                            button.classList.add('bg-emerald-500');
                        });
                        
                        // Reset preview
                        document.getElementById('selectedCardDisplay').textContent = '0';
                        const previewContainer = document.getElementById('previewContainer');
                        previewContainer.innerHTML = `
                            <div class="text-center">
                                <i class="fas fa-dice-d20 text-3xl mb-2 text-emerald-400"></i>
                                <p class="text-sm text-gray-300">${isWinner ? 'You won! ' : ''}${data.message}</p>
                            </div>
                        `;

                        // Show celebration for winner
                        if (isWinner) {
                            showToast(`Congratulations! You won ${data.bonus} credits!`);
                            // Add any winner-specific UI effects here
                        } else {
                            showToast(data.message);
                        }
                        break;
                    case 'game_reset':
                        // Reset all UI elements
                        gameStarted = false;
                        selectedCard = null;
                        takenCards.clear();
                        
                        // Reset all buttons to default state
                        document.querySelectorAll('[data-card-number]').forEach(button => {
                            button.classList.remove('bg-red-600', 'bg-blue-600');
                            button.classList.add('bg-emerald-500');
                            button.disabled = false;
                        });
                        
                        // Reset preview
                        //(null);
                        
                        // Enable join game button
                        timeLeft = 30;
                        document.getElementById('countdownValue').textContent = timeLeft;
                        
                        // Show notification
                        showToast(data.message || 'Game has been reset');
                        document.getElementById('joinGameBtn').disabled = false;
                        document.getElementById('joinGameBtn').textContent = 'Join Game';
                        
                        break;                        
                }
            } catch (error) {
                console.error('Error processing WebSocket message:', error);
            }
        };

        socket.onclose = function(e) {
            console.error('Socket closed unexpectedly:', e);
            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                reconnectAttempts++;
                console.log(`Attempting to reconnect (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
                setTimeout(initWebSocket, RECONNECT_DELAY);
            }
        };

        socket.onerror = function(error) {
            console.error('WebSocket error:', error);
        };
    }
    // Toast notification
    function showToast(message) {
        const toast = document.getElementById('toast');
        const toastMessage = document.getElementById('toast-message');
        toastMessage.textContent = message;
        
        // Remove any existing animation classes
        toast.classList.remove('toast-show');
        
        // Force a reflow
        void toast.offsetWidth;
        
        // Add the animation class
        toast.classList.add('toast-show');
        
        // Remove the animation class after it completes
        setTimeout(() => {
            toast.classList.remove('toast-show');
        }, 6000);
    }

    // Start countdown timer
    function startCountdown() {
        // Clear any existing interval
        if (countdownInterval) {
            clearInterval(countdownInterval);
        }
        
        // Update timer display immediately
        document.getElementById('countdownValue').textContent = timeLeft;
    }

    // Disable card buttons
    function disableCardButtons() {
        const cardButtons = document.querySelectorAll('.card-button');
        cardButtons.forEach(button => {
            button.disabled = true;
        });
    }

    // Enable card buttons
    function enableCardButtons() {
        const cardButtons = document.querySelectorAll('.card-button');
        cardButtons.forEach(button => {
            button.disabled = false;
        });
    }

// Handle card selection
    function handleCardSelection(cardNumber) {
        if (gameStarted) {
            showToast('The game has started. Please wait until the game is finished.');
            return;
        }

        if (takenCards.has(parseInt(cardNumber)) && cardNumber !== selectedCard) {
            showToast('This card is already taken by another player');
            return;
        }

        const button = document.querySelector(`[data-card-number="${cardNumber}"]`);
        const previewContainer = document.getElementById('previewContainer');

        if (selectedCard === cardNumber) {
            // Deselect the card
            selectedCard = null;
            button.classList.remove('selected');
            document.getElementById('selectedCardDisplay').textContent = '0';
            
            // Reset preview
            previewContainer.innerHTML = `
                <div class="text-center">
                    <i class="fas fa-dice-d20 text-3xl mb-2 text-emerald-400"></i>
                    <p id="previewText" class="text-sm text-gray-300">Select a card to preview</p>
                </div>
            `;

            // Notify server about deselection
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({
                    'type': 'deselect_card',
                    'card_id': cardNumber
                }));
            }
        } else {
            // Deselect previous card if any
            if (selectedCard) {
                const prevButton = document.querySelector(`[data-card-number="${selectedCard}"]`);
                prevButton.classList.remove('selected');
                
                // Notify server about previous card deselection
                if (socket && socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({
                        'type': 'deselect_card',
                        'card_id': selectedCard
                    }));
                }
            }
            
            // Select new card
            selectedCard = cardNumber;
            button.classList.add('selected');
            
            
            // Show loading preview
            previewContainer.innerHTML = `
                <div class="text-center">
                    <i class="fas fa-spinner fa-spin text-3xl mb-2 text-emerald-400"></i>
                    <p class="text-sm text-gray-300">Loading preview...</p>
                </div>
            `;

            // Fetch the card preview
            fetch(`/bingo/preview-card/${cardNumber}/`)
                .then(response => response.text())
                .then(html => {
                    previewContainer.innerHTML = html;
                })
                .catch(error => {
                    previewContainer.innerHTML = `
                        <div class="text-center">
                            <i class="fas fa-exclamation-circle text-3xl mb-2 text-red-400"></i>
                            <p class="text-sm text-gray-300">Card ${cardNumber} selected</p>
                            <p class="text-xs text-gray-400 mt-2">Click again to deselect</p>
                        </div>
                    `;
                });
            document.getElementById('selectedCardDisplay').textContent = cardNumber;
            // Notify server about selection
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({
                    'type': 'select_card',
                    'card_id': cardNumber
                }));
            }
        }
    }

 // Play selected card
    function playSelectedCard() {
        if (!selectedCard) return;
    
        // Immediately disable the card locally
        const button = document.querySelector(`[data-card-number="${selectedCard}"]`);
        if (!selectedCard) {
            showToast('Please select a card first');
            return;
        }

        if (gameStarted) {
            showToast('The game has already started');
            return;
        }

        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({
                type: 'card_activated',
                card_number: selectedCard
            }));
        }
        if (button) {
            button.disabled = true;
            button.classList.add('bg-red-600', 'disabled');
        }
        const roomName = document.getElementById('room-name').textContent.replace(/"/g, '');
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
        
        fetch(`/bingo/join-game/${roomName}/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                card_number: selectedCard
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.location.href = data.redirect;
            } else {
                showToast(data.message || 'Failed to join game');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Failed to join game. Please try again.');
        });
    }

// Initialize everything when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize WebSocket
    initWebSocket();
    
    // Add click handlers for card buttons
    document.querySelectorAll('.card-button').forEach(button => {
        button.addEventListener('click', function() {
            const cardNumber = this.dataset.cardNumber;
            handleCardSelection(cardNumber);
        });
    });

    // Add click handler for refresh button
    document.getElementById('refresh-button').addEventListener('click', function() {
        if (selectedCard) {
            handleCardSelection(selectedCard); // This will deselect the card
        }
    });

    // Add click handler for start button
    document.getElementById('start-button').addEventListener('click', playSelectedCard);
});
