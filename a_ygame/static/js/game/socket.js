let socket;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
const reconnectDelay = 3000;
let calledNumbers = [];
let gameActive = false;
let callInterval;

// Initialize WebSocket connection
function initWebSocket() {
    const roomName = document.getElementById('room-name').textContent.replace(/"/g, '');
    const wsScheme = window.location.protocol === "https:" ? "wss://" : "ws://";
    const wsUrl = `${wsScheme}${window.location.host}/ws/bingo/game/${roomName}/`;
    
    socket = new WebSocket(wsUrl);

    socket.onopen = function() {
        console.log('WebSocket connection established');
        reconnectAttempts = 0;
        // Start the game when connected
        startGame();
    };

    // Clear any existing intervals to prevent multiple countdowns
    if (window.countdownInterval) {
        clearInterval(window.countdownInterval);
    }
    
    // Clear any existing intervals to prevent multiple countdowns
    if (window.countdownInterval) {
        clearInterval(window.countdownInterval);
        window.countdownInterval = null;
    }
    
    socket.onmessage = function(e) {
        const data = JSON.parse(e.data);
        console.log('Received message:', data);
        
        switch(data.type) {
            case 'game_ended':
                console.log('Game ended event received:', data);
                gameActive = false;
                handleGameEnded(data);
                break;
            case 'number_called':
                handleNumberCalled(data);
                calledNumbers = data.called_numbers || [];
                console.log('Called numbers:', calledNumbers);
                break;
            case 'error':
                console.log('Error message received:', data);
                showToast(data.message, 'error');
                // Re-enable the BINGO button after 3 seconds
                const bingoButton = document.querySelector('button[onclick="declareBingo()"]');
                if (bingoButton) {
                    setTimeout(() => {
                        bingoButton.disabled = false;
                        bingoButton.innerHTML = 'BINGO!';
                    }, 3000);
                }
                break;
            case 'play_sound':
                playSound(data.sound);
                break;
            case 'player_count_update':
                // Update player count display
                const playerCountElement = document.getElementById('player-count');
                if (playerCountElement) {
                    playerCountElement.textContent = data.count;
                }
                
                // Update UI based on player count
                updateUIForPlayerCount(data.count);
                break;
            case 'countdown_update':
                // Update countdown timer start_game game_started
                const { time_left, message } = data;
                const countdownElement = document.getElementById('countdownValue');
                if (countdownElement) {
                    countdownElement.textContent = time_left;
                    
                    // Show GO! when countdown reaches 0
                    if (time_left === 0) {
                        countdownElement.textContent = '0';
                        setTimeout(() => {
                            countdownElement.textContent = 'Playing...';
                        }, 1000);
                        updateRecentCalls([]);
                    }
                }
                break;
            case 'game_reset':
                // Reset the game state
                gameActive = false;
                // Re-enable card buttons
                const cardButtons = document.querySelectorAll('.card-button');
                cardButtons.forEach(button => {
                    button.classList.remove('disabled');
                    button.onclick = function() { toggleCard(this.dataset.cardNumber); };
                });
                //showToast(data.message || 'Game has been reset');
                break;
            case 'game_started':
                // Game has started
                gameActive = true;
                // Disable card selection
                handleGameStarted();
                
                // Show game started message
                showToast('Game has started!');
                break;
            case 'toast':
                // Handle toast messages
                showToast(data.message);
                break;
        }
    };

    socket.onclose = function(e) {
        console.log('WebSocket connection closed:', e);
        if (reconnectAttempts < maxReconnectAttempts) {
            setTimeout(function() {
                reconnectAttempts++;
                initWebSocket();
            }, reconnectDelay);
        }
    };

    socket.onerror = function(error) {
        console.error('WebSocket error:', error);
    };
}

// Update UI based on player count
function updateUIForPlayerCount(count) {
    const startButton = document.getElementById('start-button');
    if (startButton) {
        if (count >= 2) {
            startButton.disabled = false;
            startButton.classList.remove('opacity-50', 'cursor-not-allowed');
        } else {
            startButton.disabled = true;
            startButton.classList.add('opacity-50', 'cursor-not-allowed');
        }
    }
}

// Handle number called event
async function handleNumberCalled(data) {
    const { number, display, letter, called_numbers } = data;
    console.log('Handling number called:', data);
    
    // Update current number display
    const currentNumberElement = document.getElementById('current-number');
    if (currentNumberElement) {
        currentNumberElement.textContent = display || number;
        
        // Add animation class
        //currentNumberElement.parentElement.classList.add('animate-ping');
        //setTimeout(() => {
        //    currentNumberElement.parentElement.classList.remove('animate-ping');
        //}, 2000);
    }
    
    // Play sound for the called number
    if (soundEnabled) {
        console.log('Playing sounds for number:', number);
        try {
            // Only play the beep sound, the letter and number sounds will be handled by playNumberSound
            await playEffect('number_called');
            await playNumberSound(number);
        } catch (e) {
            console.error('Error playing sounds for number:', e);
        }
    }
    
    // Update called numbers on the board
    if (called_numbers && Array.isArray(called_numbers)) {
        // First clear all marks to ensure we're in sync
        document.querySelectorAll('.number-cell').forEach(cell => {
            cell.classList.remove('bg-green-500');
        });
        
        // Mark all called numbers
        called_numbers.forEach(num => {
            markNumberAsCalled(num);
        });
        
        // Update recent calls display with the most recent 4 numbers
        updateRecentCalls(called_numbers);
    } else {
        // Fallback to single number update
        markNumberAsCalled(number);
        updateRecentCalls([number]);
    }
}

// Mark a number as called on the board and update recent calls
function markNumberAsCalled(number) {
    console.log('Marking number as called:', number);
    
    // Remove sound playing from here since it's handled in handleNumberCalled
    
    // Mark on the bingo card
   // const cardCells = document.querySelectorAll(`.card-cell[data-number="${number}"]`);
    //cardCells.forEach(cell => {
    //    cell.classList.add('bg-green-500');
    //});
    
    // Mark on the number grid
    const numberCells = document.querySelectorAll(`.number-cell[data-number="${number}"]`);
    numberCells.forEach(cell => {
        cell.classList.add('bg-green-500');
    });
    
    //console.log(`Marked ${cardCells.length} card cells and ${numberCells.length} number cells for number ${number}`);
}

// Update the recent calls display to show LAST 5 called numbers
function updateRecentCalls(numbers) {
    console.log('Updating recent calls with numbers:', numbers);
    const recentCallsContainer = document.getElementById('recent-calls');
    if (!recentCallsContainer) {
        console.error('Recent calls container not found');
        return;
    }
    
    // Get the last 5 numbers (most recent calls)
    const lastFiveNumbers = numbers.slice(-5).reverse(); // Reverse to show newest first
    
    // Update the recent calls list
    recentCallsContainer.innerHTML = lastFiveNumbers.map(num => 
        `<div class="px-2 py-1 bg-gray-200 rounded text-center">${num}</div>`
    ).join('');
}

// Update all called numbers on the board when the page loads
function updateCalledNumbersOnBoard() {
    calledNumbers.forEach(number => {
        markNumberAsCalled(number);
    });
}

// Start the countdown when there are enough players
function startCountdown() {
    const roomName = document.getElementById('room-name').textContent.replace(/"/g, '');
    const playerCount = parseInt(document.getElementById('player-count').textContent) || 0;
    
    if (playerCount < 2) {
        showToast('Waiting for more players... (2 required)');
        return;
    }
    
    // Notify server to start countdown
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            'action': 'start_countdown',
            'room_name': roomName
        }));
    }
}

// Handle bingo declaration
function declareBingo() {
    const cardCells = document.querySelectorAll('.card-cell');
    const username = document.getElementById('current-username').textContent.trim();
    const roomName = document.getElementById('room-name').textContent.trim();

    console.log('Declaring BINGO for room:', roomName);
    console.log('Username:', username);
    
    const cardNumbers = Array.from(cardCells).map(cell => {
        const raw = cell.dataset.number;
        const num = raw === '*' ? '*' : parseInt(raw);
        const index = parseInt(cell.dataset.index);
        if (num === '*') return '*';  // Always include center
        return cell.classList.contains('bg-green-500') ? num : null;
    });
    
    
    console.log('Card numbers (5x5 grid):', cardNumbers);
    
    // Show loading state
    const bingoButton = document.querySelector('button[onclick="declareBingo()"]');
    if (bingoButton) {
        bingoButton.disabled = true;
        bingoButton.innerHTML = 'Checking...';
    }
    
    // Send bingo declaration to the server
    if (socket && socket.readyState === WebSocket.OPEN) {
        const message = {
            'action': 'declare_bingo',
            'username': username,
            'room_name': roomName,
            'card_numbers': cardNumbers
        };
        //console.log('Sending BINGO declaration:', message);
        socket.send(JSON.stringify(message));
    } else {
        console.error('WebSocket not connected. Socket state:', socket ? socket.readyState : 'undefined');
        showToast('Error: Not connected to game server. Please refresh the page.', 'error');
        // Re-enable the button if there's an error
        if (bingoButton) {
            bingoButton.disabled = false;
            bingoButton.innerHTML = 'BINGO!';
        }
    }
}

// Start calling numbers when game begins
function startCallingNumbers() {
    if (callInterval) clearInterval(callInterval);
    callInterval = setInterval(callRandomNumber, 3000);
}

// Call a random number
function callRandomNumber() {
    if (!gameActive) return;
    
    // Generate a random number between 1 and 75 that hasn't been called yet
    let number;
    do {
        number = Math.floor(Math.random() * 75) + 1;
    } while (calledNumbers.includes(number) && calledNumbers.length < 75);
    
    if (calledNumbers.length >= 75) {
        // All numbers have been called
        clearInterval(callInterval);
        return;
    }
    
    // Send the number to the server
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            'action': 'number_called',
            'number': number,
            'room_name': document.getElementById('room-name').textContent.replace(/"/g, '')
        }));
    }
}

// Show toast notification
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
    }, 3000);
}

// Sound management
let soundEnabled = localStorage.getItem('bingo_sound_enabled') !== 'false';
const soundToggle = document.getElementById('sound-toggle');
const soundIconOn = document.getElementById('sound-icon-on');
const soundIconOff = document.getElementById('sound-icon-off');

// Audio context for playing sounds
let audioContext;
try {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    // Resume audio context on user interaction
    document.addEventListener('click', () => {
        if (audioContext.state === 'suspended') {
            audioContext.resume();
        }
    }, { once: true });
} catch (e) {
    console.error('Web Audio API is not supported in this browser');
}

// Sound effects
const soundEffects = {
    'bingo': { path: '/static/sounds/win.mp3', volume: 0.7 },
    'number_called': { path: '/static/sounds/beep.mp3', volume: 0.5 }
};

// Preload sound files
const sounds = {
    letters: {},  // Store letter sounds (B.mp3, I.mp3, etc.)
    numbers: {}   // Store number sounds (1.mp3, 2.mp3, etc.)
};

// Get BINGO letter for a number
function getBingoLetter(number) {
    if (number <= 15) return 'B';
    if (number <= 30) return 'I';
    if (number <= 45) return 'N';
    if (number <= 60) return 'G';
    return 'O';
}

// Load sounds
async function loadSounds() {
    try {
        console.log('Loading sounds...');
        
        // Load letter sounds (B.mp3, I.mp3, etc.)
        const letters = ['B', 'I', 'N', 'G', 'O'];
        for (const letter of letters) {
            const audio = new Audio(`/static/sounds/${letter}.mp3`);
            audio.preload = 'auto';
            await new Promise((resolve, reject) => {
                audio.oncanplaythrough = resolve;
                audio.onerror = reject;
                audio.load();
            });
            sounds.letters[letter] = audio;
            console.log(`Loaded letter sound: ${letter}`);
        }
        
        // Load number sounds (1.mp3 through 75.mp3)
        for (let i = 1; i <= 75; i++) {
            const audio = new Audio(`/static/sounds/${i}.mp3`);
            audio.preload = 'auto';
            await new Promise((resolve, reject) => {
                audio.oncanplaythrough = resolve;
                audio.onerror = reject;
                audio.load();
            });
            sounds.numbers[i] = audio;
            console.log(`Loaded number sound: ${i}`);
        }
        
        // Load sound effects
        for (const [key, effect] of Object.entries(soundEffects)) {
            const audio = new Audio(effect.path);
            audio.preload = 'auto';
            await new Promise((resolve, reject) => {
                audio.oncanplaythrough = resolve;
                audio.onerror = reject;
                audio.load();
            });
            sounds[key] = audio;
            console.log(`Loaded sound effect: ${key}`);
        }
        
        console.log('All sounds loaded successfully');
        return true;
    } catch (error) {
        console.error('Error loading sounds:', error);
        return false;
    }
}

// Play a single sound
async function playSound(sound, volume = 0.7) {
    if (!soundEnabled || !sounds[sound]) {
        console.log(`Sound not enabled or not found: ${sound}`);
        return;
    }
    
    try {
        const soundToPlay = sounds[sound].cloneNode();
        soundToPlay.volume = volume;
        
        // Ensure audio context is running
        if (audioContext && audioContext.state === 'suspended') {
            await audioContext.resume();
        }
        
        await soundToPlay.play();
        console.log(`Successfully played sound: ${sound}`);
    } catch (e) {
        console.error(`Error playing sound ${sound}:`, e);
    }
}

// Play sound for a number (e.g., B15)
async function playNumberSound(number) {
    if (!soundEnabled) return;
    
    const letter = getBingoLetter(number);
    console.log(`Playing sounds for number: ${letter}${number}`);
    
    try {
        // Play the letter sound first
        if (sounds.letters[letter]) {
            const letterSound = sounds.letters[letter].cloneNode();
            letterSound.volume = 0.7;
            await letterSound.play();
            console.log(`Played letter sound: ${letter}`);
            
            // Wait for 1 second before playing the number sound
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
        
        // Then play the number sound
        if (sounds.numbers[number]) {
            const numberSound = sounds.numbers[number].cloneNode();
            numberSound.volume = 0.7;
            await numberSound.play();
            console.log(`Played number sound: ${number}`);
        }
    } catch (e) {
        console.error('Error playing number sounds:', e);
    }
}

// Play sound effect
async function playEffect(effectName) {
    if (!soundEnabled) return;
    const effect = soundEffects[effectName];
    if (effect) {
        console.log(`Playing effect: ${effectName}`);
        try {
            await playSound(effectName, effect.volume);
        } catch (e) {
            console.error(`Error playing effect ${effectName}:`, e);
        }
    }
}

// Toggle sound on/off
function toggleSound() {
    soundEnabled = !soundEnabled;
    localStorage.setItem('bingo_sound_enabled', soundEnabled);
    
    if (soundEnabled) {
        soundIconOn.classList.remove('hidden');
        soundIconOff.classList.add('hidden');
        // Play a sound to indicate sound is on
        playEffect('number_called');
    } else {
        soundIconOn.classList.add('hidden');
        soundIconOff.classList.remove('hidden');
    }
}

// Initialize sound toggle button
function initSoundToggle() {
    if (soundEnabled) {
        soundIconOn.classList.remove('hidden');
        soundIconOff.classList.add('hidden');
    } else {
        soundIconOn.classList.add('hidden');
        soundIconOff.classList.remove('hidden');
    }
    
    soundToggle.addEventListener('click', toggleSound);
}

// Start the game
function startGame() {
    console.log('Starting game...');
    
    // Clear any existing game state
    clearGameState();
    
    // Enable the BINGO button
    const bingoButton = document.querySelector('button[onclick="declareBingo()"]');
    if (bingoButton) {
        bingoButton.disabled = false;
    }
    
    // Notify the server that we're ready
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            'type': 'start_game'
        }));
    }
}

// Make card numbers clickable
document.addEventListener('DOMContentLoaded', function() {
    // Initialize sound functionality
    initSoundToggle();
    
    // Load sounds and initialize WebSocket after sounds are loaded
    loadSounds().then(() => {
        console.log('Sounds loaded, initializing game...');
        // Clear any existing game state
        clearGameState();
        
        // Initialize WebSocket
        initWebSocket();
        
        // Add click handler for card cells - only for the current player's card
        //document.addEventListener('click', function(e) {
         //   const cardCell = e.target.closest('.card-cell');
           // if (cardCell && gameActive) {  // Only allow marking if game is active
             //   // Only mark if it's the current player's card
               // const cardNumber = '{{ player.card_number }}';
            //    const currentCardNumber = document.querySelector('.bg-gray-600').textContent.replace('Card ', '').trim();
                
              //  if (cardNumber === currentCardNumber) {
                //    cardCell.classList.toggle('bg-green-500');
            //    }
          //  }
        //});

        // Show initial player count
        const playerCount = parseInt(document.getElementById('player-count').textContent) || 1;
        showToast(`Waiting for players... (${playerCount}/2)`);
        updateUIForPlayerCount(playerCount);
    }).catch(error => {
        console.error('Error initializing game:', error);
        showToast('Error loading game sounds. Please refresh the page.');
    });
});

// Clear game state when page loads or game resets
function clearGameState() {
    // Clear marked cells
    document.querySelectorAll('.card-cell').forEach(cell => {
        cell.classList.remove('bg-green-500');
    });
    
    // Clear called numbers
    calledNumbers = [];
    updateRecentCalls([]);
    
    // Reset current number display
    const currentNumberElement = document.getElementById('current-number');
    if (currentNumberElement) {
        currentNumberElement.textContent = '-';
    }
    
    // Clear number grid highlights
    document.querySelectorAll('.number-cell').forEach(cell => {
        cell.classList.remove('bg-green-500');
    });
    
    // Clear any existing game state in local storage if needed
    if (typeof(Storage) !== 'undefined') {
        localStorage.removeItem(`bingo_card_${window.location.pathname}`);
    }
}

// Handle WebSocket messages
function handleWebSocketMessage(event) {
    try {
        const data = JSON.parse(event.data);
        console.log('Received WebSocket message:', data);
        
        switch (data.type) {
            case 'player_count':
                updatePlayerCount(data.count);
                break;
                
            case 'countdown':
                updateCountdown(data.time_left);
                break;
                
            case 'game_state':
                updateGameState(data.state);
                break;
                
            case 'number_called':
                handleNumberCalled(data);
                break;
                
            case 'bingo_declaration':
                if (soundEnabled) {
                    playEffect('bingo');
                }
                showToast(`${data.player_name} called BINGO!`);
                break;
                
            case 'game_ended':
                // Handle game ended event
                handleGameEnded(data);
                break;
                
            case 'error':
                showToast(data.message, 'error');
                break;
        }
    } catch (error) {
        console.error('Error handling WebSocket message:', error);
    }
}

// Function to toggle card selection
function toggleCard(cardNumber) {
    if (gameActive) {
        showToast('The game has started. Please wait until the game is finished.');
        return;
    }
    
    const button = document.querySelector(`[data-card-number="${cardNumber}"]`);
    if (!button) return;
    
    // Check if game has started
    if (gameActive) {
        showToast('Game has started! Please wait until the game ends to select cards.');
        return;
    }
    
    if (button.classList.contains('bg-emerald-500')) {
        // Deselect card
        button.classList.remove('bg-emerald-500');
        button.classList.add('bg-gray-500');
        socket.send(JSON.stringify({
            action: 'deselect_card',
            card_number: cardNumber
        }));
    } else {
        // Select card
        button.classList.remove('bg-gray-500');
        button.classList.add('bg-emerald-500');
        socket.send(JSON.stringify({
            action: 'select_card',
            card_number: cardNumber
        }));
    }
}

// Handle game started event
function handleGameStarted() {
    // Disable card selection
    const cardButtons = document.querySelectorAll('.card-button');
    cardButtons.forEach(button => {
        button.classList.add('disabled');
        button.onclick = function() { toggleCard(this.dataset.cardNumber); };
    });
}

function handleGameEnded(data) {
    // Clear selected card state and UI
    if (typeof selectedCard !== 'undefined') {
        selectedCard = null;
    }
    const selectedCardDisplay = document.getElementById('selectedCardDisplay');
    if (selectedCardDisplay) selectedCardDisplay.textContent = '';
    const previewContainer = document.getElementById('previewContainer');
    if (previewContainer) previewContainer.innerHTML = '';

    const modal = document.getElementById('gameEndModal');
    const grid = document.getElementById('winnerCardGrid');
    const message = document.getElementById('winnerMessage');
    const currentUsername = document.getElementById('current-username')?.textContent?.trim();
    const countdownEl = document.getElementById('countdownValue');

    if (!modal || !grid || !message || !countdownEl) {
        console.error('Missing modal/grid/message/countdown element in DOM');
        return;
    }

    // Personalized win message
    if (data.winner === currentUsername) {
        message.textContent = '🎉 You won!';
    } else {
        message.textContent = `🎉 ${data.winner} has won!`;
    }

    // Build winner card grid
    grid.innerHTML = '';
    data.card_numbers.forEach((number, index) => {
        const div = document.createElement('div');
        div.classList.add('w-10', 'h-10', 'flex', 'items-center', 'justify-center', 'border', 'text-sm');

        if (number === '*' || number === '*') {
            div.textContent = '⭐';
            div.classList.add('bg-yellow-300');
        } else if (data.winning_pattern?.includes(index)) {
            div.textContent = number;
            div.classList.add('bg-green-500', 'text-white');
        } else if (data.called_numbers?.includes(number)) {
            div.textContent = number;
            div.classList.add('bg-green-800', 'text-white');
        } else {
            div.textContent = number;
        }

        grid.appendChild(div);
    });

    // Start 10-second countdown
    let countdown = 10;
    countdownEl.textContent = countdown;

    const roomName = document.getElementById('room-name')?.textContent?.replace(/"/g, '');
    const countdownInterval = setInterval(() => {
        countdown--;
        countdownEl.textContent = countdown;
        if (countdown <= 0) {
            clearInterval(countdownInterval);
            window.location.href = `/bingo/card-selection/${roomName}/`;
        }
    }, 1000);

    modal.classList.remove('hidden');
    // Also remove any visual selection from card buttons
    document.querySelectorAll('.card-button').forEach(button => {
        button.classList.remove('bg-blue-600', 'bg-emerald-500', 'bg-red-600', 'selected');
        button.disabled = false;
    });
}
