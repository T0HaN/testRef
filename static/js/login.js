document.addEventListener('DOMContentLoaded', () => {
    const usernameInput = document.getElementById('username');
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const consentCheckbox = document.getElementById('consent-checkbox');
    const authForm = document.getElementById('auth-form');

    const emailGroup = document.getElementById('email-group');
    const consentGroup = document.getElementById('consent-group');
    const actionInput = document.getElementById('action-input');
    const submitBtn = document.getElementById('main-submit-btn');
    const toggleLink = document.getElementById('toggle-link');
    const togglePrompt = document.getElementById('toggle-prompt');

    let isLoginMode = true;

    // Фокус на поле при загрузке
    if (usernameInput && !usernameInput.value) {
        usernameInput.focus();
    }

    // Переключение между Входом и Регистрацией
    toggleLink.addEventListener('click', (e) => {
        e.preventDefault();
        isLoginMode = !isLoginMode;

        if (isLoginMode) {
            // Режим Входа
            emailGroup.style.display = 'none';
            emailInput.required = false;
            consentGroup.style.display = 'none';
            consentCheckbox.required = false;
            actionInput.value = 'login';
            submitBtn.innerHTML = '🔐 Войти';
            togglePrompt.textContent = 'Ещё не ведете летопись?';
            toggleLink.textContent = 'Зарегистрироваться';
        } else {
            // Режим Регистрации
            emailGroup.style.display = 'block';
            emailInput.required = true;
            consentGroup.style.display = 'block';
            consentCheckbox.required = true;
            actionInput.value = 'register';
            submitBtn.innerHTML = '📜 Зарегистрироваться';
            togglePrompt.textContent = 'Уже есть аккаунт?';
            toggleLink.textContent = 'Войти';
        }
    });

    // Валидация перед отправкой
    authForm.addEventListener('submit', (e) => {
        const username = usernameInput.value.trim();
        const password = passwordInput.value;

        // Проверка логина
        if (username.length < 3) {
            e.preventDefault();
            alert('Логин должен содержать минимум 3 символа');
            usernameInput.focus();
            return;
        }

        // Проверка пароля
        if (password.length < 4) {
            e.preventDefault();
            alert('Пароль должен содержать минимум 4 символа');
            passwordInput.focus();
            return;
        }

        // Если регистрация — проверяем почту и согласие
        if (!isLoginMode) {
            // Почта
            if (!emailInput.value.includes('@')) {
                e.preventDefault();
                alert('Пожалуйста, введите корректный адрес электронной почты');
                emailInput.focus();
                return;
            }

            // Согласие
            if (!consentCheckbox.checked) {
                e.preventDefault();
                alert('Для регистрации необходимо дать согласие на обработку персональных данных');
                consentCheckbox.focus();
                return;
            }
        }
    });
});
