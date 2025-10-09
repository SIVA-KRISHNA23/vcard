// Modal for save contact
function openModal() {
    const modal = document.getElementById('saveModal');
    modal.style.display = 'flex';
    modal.classList.add('modal-show');
}
function closeModal() {
    const modal = document.getElementById('saveModal');
    modal.classList.remove('modal-show');
    setTimeout(() => { modal.style.display = 'none'; }, 300); // Smooth fade out
}
window.onclick = function(event) {
    const modal = document.getElementById('saveModal');
    if(event.target == modal) closeModal();
}

// Dashboard search filter
function filterUsers() {
    let input = document.getElementById('searchInput').value.toLowerCase();
    let cards = document.querySelectorAll('.user-card');
    cards.forEach(card => {
        let name = card.querySelector('h3').innerText.toLowerCase();
        let email = card.querySelector('p').innerText.toLowerCase();
        card.style.display = (name.includes(input) || email.includes(input)) ? '' : 'none';
    });
}

// Theme Switcher
function toggleTheme() {
    document.body.classList.toggle('dark');
    document.body.classList.toggle('light');
    localStorage.setItem('theme', document.body.classList.contains('dark') ? 'dark' : 'light');
}

// Preserve theme on reload
document.addEventListener('DOMContentLoaded', () => {
    if(localStorage.getItem('theme') === 'dark') {
        document.body.classList.add('dark');
    } else {
        document.body.classList.add('light');
    }
});

// Show QR Popup
function showQR(src) {
    const popup = document.getElementById('qrPopup');
    popup.querySelector('img').src = src;
    popup.style.display = 'flex';
    popup.classList.add('popup-show');
}

// Close QR Popup
function closeQR() {
    const popup = document.getElementById('qrPopup');
    popup.classList.remove('popup-show');
    setTimeout(() => { popup.style.display = 'none'; }, 300);
}

// Copy link with toast
function copyLink(id) {
    const input = document.getElementById(id);
    input.select();
    input.setSelectionRange(0, 99999);
    navigator.clipboard.writeText(input.value);

    const toast = document.getElementById('toast');
    toast.classList.add('show');
    setTimeout(() => { toast.classList.remove('show'); }, 2000);
}

// Optional: animate modal & popup with CSS
