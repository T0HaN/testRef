document.addEventListener('DOMContentLoaded', () => {
    // Форма смены почты
    const emailForm = document.getElementById('email-form');
    const newEmailInput = document.getElementById('new_email');
    const emailSubmitBtn = document.getElementById('email-submit-btn');

    // Форма смены пароля
    const passwordForm = document.getElementById('password-form');
    const currentPasswordInput = document.getElementById('current_password');
    const newPasswordInput = document.getElementById('new_password');
    const confirmPasswordInput = document.getElementById('confirm_password');
    const passwordSubmitBtn = document.getElementById('password-submit-btn');

    // 1. Валидация отправки почты
    if (emailForm) {
        emailForm.addEventListener('submit', (e) => {
            const emailVal = newEmailInput.value.trim();

            if (!emailVal || !emailVal.includes('@') || !emailVal.includes('.')) {
                e.preventDefault();
                alert('Укажите корректный адрес электронной почты');
                newEmailInput.focus();
                return;
            }

            emailSubmitBtn.disabled = true;
            emailSubmitBtn.innerText = 'Отправка свитка...';
            emailSubmitBtn.style.opacity = '0.7';
            emailSubmitBtn.style.cursor = 'wait';
        });
    }

    // 2. Интерактивная подсветка совпадения паролей
    function checkPasswordsMatch() {
        const newPass = newPasswordInput.value;
        const confPass = confirmPasswordInput.value;

        if (!confPass) {
            confirmPasswordInput.classList.remove('input-match', 'input-mismatch');
            return;
        }

        if (newPass === confPass) {
            confirmPasswordInput.classList.remove('input-mismatch');
            confirmPasswordInput.classList.add('input-match');
        } else {
            confirmPasswordInput.classList.remove('input-match');
            confirmPasswordInput.classList.add('input-mismatch');
        }
    }

    if (newPasswordInput && confirmPasswordInput) {
        newPasswordInput.addEventListener('input', checkPasswordsMatch);
        confirmPasswordInput.addEventListener('input', checkPasswordsMatch);
    }

    // 3. Валидация отправки пароля
    if (passwordForm) {
        passwordForm.addEventListener('submit', (e) => {
            const curPass = currentPasswordInput.value;
            const newPass = newPasswordInput.value;
            const confPass = confirmPasswordInput.value;

            if (!curPass) {
                e.preventDefault();
                alert('Введите текущий пароль');
                currentPasswordInput.focus();
                return;
            }

            if (newPass.length < 4) {
                e.preventDefault();
                alert('Новый пароль должен быть не короче 4 символов');
                newPasswordInput.focus();
                return;
            }

            if (newPass !== confPass) {
                e.preventDefault();
                alert('Новые пароли не совпадают');
                confirmPasswordInput.focus();
                return;
            }

            passwordSubmitBtn.disabled = true;
            passwordSubmitBtn.innerText = 'Запечатываем ключ...';
            passwordSubmitBtn.style.opacity = '0.7';
            passwordSubmitBtn.style.cursor = 'wait';
        });
    }
});