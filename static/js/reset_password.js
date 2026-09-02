document.addEventListener('DOMContentLoaded', () => {
    const resetForm = document.getElementById('reset-form');
    const newPasswordInput = document.getElementById('new_password');
    const confirmPasswordInput = document.getElementById('confirm_password');
    const submitBtn = document.getElementById('submit-btn');

    if (newPasswordInput) {
        newPasswordInput.focus();
    }

    // Динамическая подсветка совпадения паролей
    function validateMatch() {
        const pass = newPasswordInput.value;
        const conf = confirmPasswordInput.value;

        if (!conf) {
            confirmPasswordInput.classList.remove('input-match', 'input-mismatch');
            return;
        }

        if (pass === conf) {
            confirmPasswordInput.classList.remove('input-mismatch');
            confirmPasswordInput.classList.add('input-match');
        } else {
            confirmPasswordInput.classList.remove('input-match');
            confirmPasswordInput.classList.add('input-mismatch');
        }
    }

    newPasswordInput.addEventListener('input', validateMatch);
    confirmPasswordInput.addEventListener('input', validateMatch);

    // Валидация перед отправкой
    resetForm.addEventListener('submit', (e) => {
        const pass = newPasswordInput.value;
        const conf = confirmPasswordInput.value;

        if (pass.length < 4) {
            e.preventDefault();
            alert('Пароль должен содержать минимум 4 символа');
            newPasswordInput.focus();
            return;
        }

        if (pass !== conf) {
            e.preventDefault();
            alert('Введённые пароли не совпадают');
            confirmPasswordInput.focus();
            return;
        }

        submitBtn.disabled = true;
        submitBtn.innerText = 'Запечатываем...';
        submitBtn.style.opacity = '0.7';
        submitBtn.style.cursor = 'wait';
    });
});