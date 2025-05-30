// Sound management
let soundEnabled = localStorage.getItem('bingo_sound_enabled') !== 'false';
const soundEffects = {
    'bingo': { path: '/static/sounds/win.mp3', volume: 0.7 },
    'number_called': { path: '/static/sounds/beep.mp3', volume: 0.5 }
};

// Preload sound files
const sounds = {};

// Load sounds
async function loadSounds() {
    // Load BINGO numbers
    for (let i = 1; i <= 75; i++) {
        const letter = getBingoLetter(i);
        const audio = new Audio(`/static/sounds/${letter}${i}.mp3`);
        audio.load();
        sounds[`${letter}${i}`] = audio;
    }
    
    // Load sound effects
    Object.entries(soundEffects).forEach(([key, effect]) => {
        const audio = new Audio(effect.path);
        audio.load();
        sounds[key] = audio;
    });
}

// Play a single sound
function playSound(sound, volume = 0.7) {
    return new Promise((resolve) => {
        if (!soundEnabled || !sounds[sound]) {
            resolve();
            return;
        }
        
        const soundToPlay = sounds[sound].cloneNode();
        soundToPlay.volume = volume;
        
        soundToPlay.onended = () => resolve();
        soundToPlay.play().catch(e => {
            console.error('Error playing sound:', e);
            resolve();
        });
    });
}

// Play sound for a number (e.g., B15)
function playNumberSound(number) {
    if (!soundEnabled) return;
    
    const letter = getBingoLetter(number);
    const soundKey = `${letter}${number}`;
    
    // Play the number sound
    playSound(soundKey).catch(e => {
        console.error('Error playing number sound:', e);
    });
}

// Play sound effect
function playEffect(effectName) {
    if (!soundEnabled) return;
    
    const effect = soundEffects[effectName];
    if (effect) {
        playSound(effectName, effect.volume);
    }
}

// Toggle sound on/off
function toggleSound() {
    soundEnabled = !soundEnabled;
    localStorage.setItem('bingo_sound_enabled', soundEnabled);
    
    const soundToggle = document.getElementById('sound-toggle');
    const soundIconOn = document.getElementById('sound-icon-on');
    const soundIconOff = document.getElementById('sound-icon-off');
    
    if (soundToggle && soundIconOn && soundIconOff) {
        soundToggle.classList.toggle('text-gray-500');
        soundIconOn.classList.toggle('hidden');
        soundIconOff.classList.toggle('hidden');
    }
}

// Initialize sound toggle button
function initSoundToggle() {
    const soundToggle = document.getElementById('sound-toggle');
    if (soundToggle) {
        soundToggle.addEventListener('click', toggleSound);
        
        // Set initial state
        const soundIconOn = document.getElementById('sound-icon-on');
        const soundIconOff = document.getElementById('sound-icon-off');
        if (soundIconOn && soundIconOff) {
            if (!soundEnabled) {
                soundToggle.classList.add('text-gray-500');
                soundIconOn.classList.add('hidden');
                soundIconOff.classList.remove('hidden');
            }
        }
    }
}

