// spells.js — фильтрация заклинаний
function filterSpells() {
            const searchQuery = document.getElementById('spellSearch').value.toLowerCase();
            const levelFilter = document.getElementById('levelFilter').value;
            const schoolFilter = document.getElementById('schoolFilter').value.toLowerCase();

            const cards = document.querySelectorAll('.spell-card');

            cards.forEach(card => {
                const name = card.getAttribute('data-name');
                const level = card.getAttribute('data-level');
                const school = card.getAttribute('data-school');

                const matchesSearch = name.includes(searchQuery);
                const matchesLevel = levelFilter === 'all' || level === levelFilter;
                const matchesSchool = schoolFilter === 'all' || school.includes(schoolFilter);

                if (matchesSearch && matchesLevel && matchesSchool) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });

            // Скрываем/Показываем заголовки списков (например "Заговоры (5)"), если под ними нет карточек
            document.querySelectorAll('.spell-list').forEach(list => {
                const visibleCards = Array.from(list.querySelectorAll('.spell-card')).filter(c => c.style.display !== 'none');
                const header = list.previousElementSibling;

                if (header && header.classList.contains('section-title')) {
                    header.style.display = visibleCards.length > 0 ? 'block' : 'none';
                }
            });
        }
