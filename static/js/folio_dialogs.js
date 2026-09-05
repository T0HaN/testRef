// Тосты
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

// Асинхронный confirm
function confirmModal(message, title = 'Подтверждение', isDanger = false) {
    return new Promise((resolve) => {
        const backdrop = document.createElement('div');
        backdrop.className = 'folio-dialog-backdrop';

        backdrop.innerHTML = `
            <div class="folio-dialog-box">
                <div class="folio-dialog-title">${title}</div>
                <div class="folio-dialog-message">${message}</div>
                <div class="folio-dialog-actions">
                    <button class="vtt-btn btn-cancel">Отмена</button>
                    <button class="vtt-btn ${isDanger ? 'danger' : 'primary'} btn-confirm">Подтвердить</button>
                </div>
            </div>
        `;

        document.body.appendChild(backdrop);
        requestAnimationFrame(() => backdrop.classList.add('show'));

        const close = (result) => {
            backdrop.classList.remove('show');
            backdrop.addEventListener('transitionend', () => backdrop.remove(), { once: true });
            resolve(result);
        };

        backdrop.querySelector('.btn-confirm').onclick = () => close(true);
        backdrop.querySelector('.btn-cancel').onclick = () => close(false);
    });
}