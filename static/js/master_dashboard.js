// Копирование кода приглашения
        function copyCode(elementId) {
            const code = document.getElementById(elementId).textContent;
            navigator.clipboard.writeText(code).then(() => {
                const btn = event.target;
                const original = btn.textContent;
                btn.textContent = '✅';
                setTimeout(() => btn.textContent = original, 1500);
            });
        }

        // Логика раскрытия формы создания комнаты
        document.addEventListener('DOMContentLoaded', () => {
            const toggleBtn = document.getElementById('toggleCreateBtn');
            const cancelBtn = document.getElementById('cancelCreateBtn');
            const createCard = document.getElementById('createRoomCard');
            const nameInput = document.getElementById('name');

            function showForm() {
                createCard.classList.add('visible');
                toggleBtn.style.display = 'none';
                nameInput.focus();
            }

            function hideForm() {
                createCard.classList.remove('visible');
                toggleBtn.style.display = 'flex';
            }

            toggleBtn.addEventListener('click', showForm);
            cancelBtn.addEventListener('click', hideForm);
        });
