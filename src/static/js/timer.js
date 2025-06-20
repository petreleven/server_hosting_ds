// Store active intervals to avoid duplication
const countdownTimers = {};

function updateCountdown(expiresAtStr, countdownElementId, status) {
    const countdownElement = document.getElementById(countdownElementId);
    if (!countdownElement || status === 'provisioning') return;

    // Clear existing interval for this element
    if (countdownTimers[countdownElementId]) {
        clearInterval(countdownTimers[countdownElementId]);
    }

    function update() {
        const now = new Date();
        const expires = new Date(expiresAtStr);
        const diff = expires - now;

        if (diff <= 0) {
            countdownElement.textContent = 'Expired';
            clearInterval(countdownTimers[countdownElementId]);
            return;
        }

        const hours = Math.floor(diff / 1000 / 60 / 60);
        const minutes = Math.floor((diff / 1000 / 60) % 60);
        const seconds = Math.floor((diff / 1000) % 60);

        countdownElement.textContent =
            `${hours}h ${minutes < 10 ? '0' : ''}${minutes}m ${seconds < 10 ? '0' : ''}${seconds}s`;

    }

    update(); // Initial call
    countdownTimers[countdownElementId] = setInterval(update, 1000);
}

// Handle HTMX content replacement
document.body.addEventListener('htmx:afterSwap', (event) => {
    // Only proceed if a server card was updated
    console.log("called")
    const newContent = event.target;
    const countdowns = newContent.querySelectorAll('[id^="countdown-"]');

    countdowns.forEach((el) => {
        const id = el.id;
        const expiresAt = el.dataset.expiresAt;
        const status = el.dataset.status;
        if (expiresAt && status) {
            updateCountdown(expiresAt, id, status);
        }
    });
});
