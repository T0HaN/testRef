// ===== Модификаторы характеристик =====
function updateMod(input, modId) {
    let score = parseInt(input.value, 10);
    if (isNaN(score)) score = 10;
    // Clamp в допустимые границы
    score = Math.max(1, Math.min(30, score));
    const mod = Math.floor((score - 10) / 2);
    const modText = mod >= 0 ? `+${mod}` : `${mod}`;
    document.getElementById(modId).textContent = modText;
    if (input.name === 'DEX') {
        document.getElementById('initiative').value = modText;
    }
}

// ===== Лимит навыков =====
const MAX_SKILLS = 6;

document.addEventListener('DOMContentLoaded', () => {
    // Инициализация модификаторов
    document.querySelectorAll('.stat-score').forEach(input => {
        const modId = `${input.name}-mod`;
        updateMod(input, modId);
    });

    // Подклассы
    const classSelect = document.getElementById('char_class');
    const subSelect = document.getElementById('subclass');
    const subclassesData = window.subclassesData || {};

    if (classSelect && subSelect) {
        classSelect.addEventListener('change', () => {
            const selectedClass = classSelect.value;
            const options = subclassesData[selectedClass] || [];
            subSelect.innerHTML = '<option value="Нет">Нет</option>';
            options.forEach(sub => {
                if (sub) {
                    const opt = document.createElement('option');
                    opt.value = sub;
                    opt.textContent = sub;
                    subSelect.appendChild(opt);
                }
            });
        });
        if (classSelect.value) {
            classSelect.dispatchEvent(new Event('change'));
        }
    }

    // Ограничение количества навыков
    document.querySelectorAll('.skill-checkbox').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const checked = document.querySelectorAll('.skill-checkbox:checked');
            if (checked.length > MAX_SKILLS) {
                e.target.checked = false;
                alert(`⚠️ Максимум ${MAX_SKILLS} навыков! Выбрано: ${checked.length - 1}`);
            }
        });
    });

    // Валидация формы при отправке
    const form = document.getElementById('charForm');
    form.addEventListener('submit', (e) => {
        const hpCurrent = parseInt(document.getElementById('hp_current').value) || 0;
        const hpMax = parseInt(document.getElementById('hp_max').value) || 1;

        if (hpCurrent > hpMax) {
            e.preventDefault();
            alert('⚠️ Текущие ХП не могут превышать максимум!');
            document.getElementById('hp_current').value = hpMax;
            document.getElementById('hp_current').focus();
            return false;
        }

        // Дополнительная проверка XP
        const xp = parseInt(document.getElementById('xp').value) || 0;
        if (xp > 999999) {
            e.preventDefault();
            alert('⚠️ Опыт не может превышать 999999!');
            document.getElementById('xp').value = 999999;
            document.getElementById('xp').focus();
            return false;
        }
    });
});
