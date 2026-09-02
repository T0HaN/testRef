document.addEventListener('DOMContentLoaded', () => {
    const forgotForm = document.getElementById('forgot-form');
    const emailInput = document.getElementById('email');
    const submitBtn = document.getElementById('submit-btn');

    if (emailInput) {
        emailInput.focus();
    }

    forgotForm.addEventListener('submit', (e) => {
        const emailVal = emailInput.value.trim();

        if (!emailVal || !emailVal.includes('@') || !emailVal.includes('.')) {
            e.preventDefault();
            alert('Пожалуйста, укажите корректный адрес электронной почты');
            emailInput.focus();
            return;
        }

        // Защита от случайных дабл-кликов
        submitBtn.disabled = true;
        submitBtn.innerText = 'Отправка свитка...';
        submitBtn.style.opacity = '0.7';
        submitBtn.style.cursor = 'wait';
    });
});