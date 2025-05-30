// Include this in your HTML before this script:
// <script src="https://cdn.jsdelivr.net/npm/reconnecting-websocket@4.4.0/dist/reconnecting-websocket.min.js"></script>

// GLOBAL VARIABLES
const loc_username = localStorage.getItem("username");
window.selectedCard = null; // Make selectedCard globally accessible

// Set up WebSocket connection
const urls = "ws://127.0.0.1:8000/ws/clicked" + window.location.pathname;
const ws = new ReconnectingWebSocket(urls);

// When WebSocket connects
ws.onopen = function () {
  ws.send(
    JSON.stringify({
      command: "joined",
      info: `${loc_username} just Joined`,
      user: loc_username,
    })
  );
};

// Handle messages related to card selection
ws.onmessage = function (event) {
  const data = JSON.parse(event.data);
  if (data.type === "card_selected") {
    const cardNumber = data.card_number;
    const button = document.querySelector(`[data-card-number="${cardNumber}"]`);
    if (button) {
      button.classList.remove('bg-emerald-500', 'hover:bg-emerald-600');
      button.classList.add('bg-red-600', 'cursor-not-allowed', 'opacity-50');
      button.disabled = true;
    }
  } else if (data.command === "clicked") {
    const clickedDiv = document.querySelector(`[data-innernum='${data.dataset}']`);
    if (clickedDiv && data.user !== loc_username) {
      clickedDiv.classList.add("clicked");
    }
  }
};

// Toggle card selection
window.toggleCard = function (cardNumber) {
  const button = document.querySelector(`[data-card-number="${cardNumber}"]`);

  if (window.selectedCard === cardNumber) {
    // Deselect
    window.selectedCard = null;
    button.classList.remove('btn-success');
    button.classList.add('selection-cell-user-selected');
    document.getElementById('selectedCardDisplay').textContent = '';
    document.getElementById('previewContainer').innerHTML = '';
  } else {
    // Deselect previous
    if (window.selectedCard) {
      const prevButton = document.querySelector(`[data-card-number="${window.selectedCard}"]`);
      if (prevButton) {
        prevButton.classList.remove('btn-success');
        prevButton.classList.add('selection-cell-user-selected');
      }
    }

    // Select new
    window.selectedCard = cardNumber;
    button.classList.remove('selection-cell-user-selected');
    button.classList.add('btn-success');
    document.getElementById('selectedCardDisplay').textContent = `${cardNumber}`;

    // Show preview
    const previewContainer = document.getElementById('previewContainer');
    previewContainer.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';

    fetch(`/preview-card/${cardNumber}/`)
      .then(response => response.text())
      .then(html => {
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const bingoCard = doc.querySelector('.bingo-card');
        if (bingoCard) {
          previewContainer.innerHTML = bingoCard.outerHTML;
        } else {
          previewContainer.innerHTML = '<p class="text-danger">Error loading preview</p>';
        }
      })
      .catch(error => {
        previewContainer.innerHTML = '<p class="text-danger">Error loading preview</p>';
      });

    // Notify others via socket
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "card_selected",
        card_number: cardNumber,
        user: loc_username
      }));
    }
  }
};

// Refresh card selection
window.refreshSelection = function () {
  if (window.selectedCard) {
    const button = document.querySelector(`[data-card-number="${window.selectedCard}"]`);
    button.classList.remove('btn-success');
    button.classList.add('selection-cell-user-selected');
  }
  window.selectedCard = null;
  document.getElementById('selectedCardDisplay').textContent = '';
  document.getElementById('previewContainer').innerHTML = '';
};
