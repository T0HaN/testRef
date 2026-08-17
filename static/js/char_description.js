// === Просмотр изображения ===
function openImageModal(src) {
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('modalImage');
    modal.style.display = 'block';
    modalImg.src = src;
    document.body.style.overflow = 'hidden'; // блокируем прокрутку фона
}

function closeImageModal() {
    const modal = document.getElementById('imageModal');
    modal.style.display = 'none';
    document.body.style.overflow = '';
}

// Закрытие по клику на фон
document.getElementById('imageModal')?.addEventListener('click', function(e) {
    if (e.target === this) closeImageModal();
});

// Закрытие по Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeImageModal();
});

// Предпросмотр загружаемого файла
document.getElementById('char_image')?.addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (file) {
        if (file.size > 5 * 1024 * 1024) {
            alert('Файл слишком большой! Максимум 5MB.');
            e.target.value = '';
            return;
        }
        const reader = new FileReader();
        reader.onload = function(event) {
            const preview = document.getElementById('charImagePreview');
            preview.innerHTML = '<img src="' + event.target.result + '" alt="Preview">';
            preview.style.cursor = 'zoom-in';
            preview.onclick = function() { openImageModal(event.target.result); };
        };
        reader.readAsDataURL(file);
    }
});
