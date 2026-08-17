// CharList1.js - Character List functionality

document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu toggle
    const menuBtn = document.getElementById('menu-toggle');
    const sidebar = document.getElementById('sidebar');

    if (menuBtn && sidebar) {
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
    }

    // Add hover effects to character cards
    const charCards = document.querySelectorAll('.char-card');
    charCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-3px)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });

    // Add confirmation dialog for delete buttons
    const deleteButtons = document.querySelectorAll('.btn-delete');
    deleteButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            const charName = this.closest('.char-card').querySelector('.char-name')?.textContent;
            if (!confirm(`Вы уверены, что хотите навсегда удалить героя «${charName}»?`)) {
                e.preventDefault();
                return false;
            }
        });
    });

    // Animate skill tags on hover
    const skillTags = document.querySelectorAll('.skill-tag');
    skillTags.forEach(tag => {
        tag.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.05)';
            this.style.transition = 'transform 0.2s ease';
        });
        
        tag.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1)';
        });
    });

    console.log('Character list initialized successfully');
});
