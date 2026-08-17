document.getElementById('spellForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const form = e.target;
    const notification = document.getElementById('notification');

    // Собираем выбранные классы из чекбоксов
    const checkedClasses = Array.from(form.querySelectorAll('input[name="classes"]:checked')).map(cb => cb.value);

    const payload = {
        name_ru: form.name_ru.value,
        name_en: form.name_en.value,
        level: parseInt(form.level.value),
        school: form.school.value,
        casting_time: form.casting_time.value,
        range: form.range.value,
        components: form.components.value,
        duration: form.duration.value,
        description: form.description.value,
        source: form.source.value,
        classes: checkedClasses
    };

    try {
        const response = await fetch('/api/spells', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            notification.className = 'success-msg';
            notification.textContent = 'Заклинание успешно добавлено!';
            notification.style.display = 'block';
            form.reset();
        } else {
            throw new Error('Ошибка сервера');
        }
    } catch (error) {
        notification.className = 'error-msg';
        notification.textContent = 'Не удалось сохранить заклинание. Проверьте соединение с сервером.';
        notification.style.display = 'block';
    }

    setTimeout(() => {
        notification.style.display = 'none';
    }, 5000);
});
