// Управление модальными окнами
function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', function(e) {
        if (e.target === this) this.classList.remove('active');
    });
});

// Мобильное меню
const menuBtn = document.getElementById('menu-toggle');
const sidebar = document.getElementById('sidebar');

menuBtn.addEventListener('click', () => {
    sidebar.classList.toggle('mobile-open');
});

document.addEventListener('click', (e) => {
    if (window.innerWidth <= 900) {
        if (!sidebar.contains(e.target) && e.target !== menuBtn) {
            sidebar.classList.remove('mobile-open');
        }
    }
});
