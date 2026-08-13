// CharList.js - Character Sheet functionality

document.addEventListener('DOMContentLoaded', function() {
    // Initialize character sheet animations
    const sections = document.querySelectorAll('.section, .ability, .header-value');
    
    sections.forEach((element, index) => {
        element.style.animationDelay = `${index * 0.1}s`;
    });

    // Add hover effects to ability cards
    const abilities = document.querySelectorAll('.ability');
    abilities.forEach(ability => {
        ability.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-5px)';
        });
        
        ability.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });

    // Checkbox toggle animation for skills and saving throws
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const parent = this.closest('.skill') || this.closest('.saving-throw');
            if (this.checked) {
                parent.style.background = 'rgba(212, 175, 55, 0.2)';
            } else {
                parent.style.background = 'rgba(20, 20, 35, 0.5)';
            }
        });
    });

    // HP value click interaction
    const hpValues = document.querySelectorAll('.hp-value');
    hpValues.forEach(hpValue => {
        hpValue.addEventListener('click', function() {
            const newValue = prompt('Enter new HP value:', this.textContent);
            if (newValue !== null && newValue.trim() !== '') {
                this.textContent = newValue.trim();
            }
        });
    });

    // Stat card hover effect enhancement
    const statCards = document.querySelectorAll('.stat-card');
    statCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.05)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1)';
        });
    });

    // Header value edit on double-click
    const headerValues = document.querySelectorAll('.header-value');
    headerValues.forEach(value => {
        value.addEventListener('dblclick', function() {
            const currentText = this.textContent;
            const newValue = prompt('Edit value:', currentText);
            if (newValue !== null && newValue.trim() !== '') {
                this.textContent = newValue.trim();
            }
        });
    });

    console.log('Character sheet initialized successfully');
});
