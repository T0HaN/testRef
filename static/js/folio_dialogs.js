// --- ТОСТЫ ---
function showToast(message, type = 'info', duration = 3500) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'folio-toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `folio-toast ${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button class="folio-toast-close">&times;</button>
    `;

    const closeBtn = toast.querySelector('.folio-toast-close');
    closeBtn.onclick = () => removeToast(toast);

    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));

    const timer = setTimeout(() => removeToast(toast), duration);

    function removeToast(el) {
        clearTimeout(timer);
        el.classList.remove('show');
        el.addEventListener('transitionend', () => el.remove(), { once: true });
    }
}

// Перехват стандартного alert
window.alert = function(message) {
    showToast(message, 'info');
};

// --- АСИНХРОННЫЙ CONFIRM ---
function confirmModal(message, title = 'Подтверждение', isDanger = false) {
    return new Promise((resolve) => {
        const backdrop = document.createElement('div');
        backdrop.className = 'folio-dialog-backdrop';

        backdrop.innerHTML = `
            <div class="folio-dialog-box">
                <div class="folio-dialog-title">${title}</div>
                <div class="folio-dialog-message">${message}</div>
                <div class="folio-dialog-actions">
                    <button class="vtt-btn btn-cancel" type="button">Отмена</button>
                    <button class="vtt-btn ${isDanger ? 'danger' : 'primary'} btn-confirm" type="button">Подтвердить</button>
                </div>
            </div>
        `;

        document.body.appendChild(backdrop);
        requestAnimationFrame(() => backdrop.classList.add('show'));

        const close = (result) => {
            document.removeEventListener('keydown', handleKey);
            backdrop.classList.remove('show');
            backdrop.addEventListener('transitionend', () => backdrop.remove(), { once: true });
            resolve(result);
        };

        const handleKey = (e) => {
            if (e.key === 'Escape') close(false);
            if (e.key === 'Enter') close(true);
        };
        document.addEventListener('keydown', handleKey);

        backdrop.querySelector('.btn-confirm').onclick = () => close(true);
        backdrop.querySelector('.btn-cancel').onclick = () => close(false);

        // Закрытие при клике по фону
        backdrop.addEventListener('click', (e) => {
            if (e.target === backdrop) close(false);
        });
    });
}

// Глобальный перехват на случай забытых вызовов confirm()
window.confirm = function(message) {
    return confirmModal(message);
};

// --- АСИНХРОННЫЙ PROMPT ---
function promptModal(message, defaultValue = '', title = 'Ввод данных') {
    return new Promise((resolve) => {
        const backdrop = document.createElement('div');
        backdrop.className = 'folio-dialog-backdrop';

        backdrop.innerHTML = `
            <div class="folio-dialog-box">
                <div class="folio-dialog-title">${title}</div>
                <div class="folio-dialog-message">${message}</div>
                <input type="text" class="folio-dialog-input" value="${defaultValue}" style="width: 100%; padding: 0.6rem; background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-primary); font-family: var(--font-ui); font-size: 0.9rem; outline: none;">
                <div class="folio-dialog-actions">
                    <button class="vtt-btn btn-cancel" type="button">Отмена</button>
                    <button class="vtt-btn primary btn-confirm" type="button">Готово</button>
                </div>
            </div>
        `;

        document.body.appendChild(backdrop);
        requestAnimationFrame(() => backdrop.classList.add('show'));

        const input = backdrop.querySelector('.folio-dialog-input');
        input.focus();
        input.select();

        const close = (result) => {
            document.removeEventListener('keydown', handleKey);
            backdrop.classList.remove('show');
            backdrop.addEventListener('transitionend', () => backdrop.remove(), { once: true });
            resolve(result);
        };

        const handleKey = (e) => {
            if (e.key === 'Escape') close(null);
            if (e.key === 'Enter') close(input.value.trim() || null);
        };
        document.addEventListener('keydown', handleKey);

        backdrop.querySelector('.btn-confirm').onclick = () => close(input.value.trim() || null);
        backdrop.querySelector('.btn-cancel').onclick = () => close(null);

        backdrop.addEventListener('click', (e) => {
            if (e.target === backdrop) close(null);
        });
    });
}

// Глобальный перехват на случай вызовов prompt()
window.prompt = function(message, defaultValue = '') {
    return promptModal(message, defaultValue);
};