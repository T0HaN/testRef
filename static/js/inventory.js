function switchMainTab(tabName) {
    document.querySelectorAll('.main-tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('[id^="tab-"]').forEach(p => p.style.display = 'none');
    event.target.classList.add('active');
    document.getElementById('tab-' + tabName).style.display = 'block';
}

function showCat(category) {
    document.querySelectorAll('.cat-tab').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.querySelectorAll('.catalog-item').forEach(item => {
        item.style.display = (category === 'all' || item.dataset.cat === category) ? 'block' : 'none';
    });
}

function updateCustomForm() {
    const type = document.getElementById('custom_type').value;
    document.getElementById('custom_weapon').style.display = type === 'weapon' ? 'block' : 'none';
    document.getElementById('custom_armor').style.display = type === 'armor' ? 'block' : 'none';
    document.getElementById('custom_gear').style.display = type === 'gear' ? 'block' : 'none';

    const isAmmo = document.querySelector('input[name="weapon_props"][value="ammunition"]')?.checked || false;
    const isThrown = document.querySelector('input[name="weapon_props"][value="thrown"]')?.checked || false;
    document.getElementById('ammo_type_group').style.display = (isAmmo || isThrown) ? 'block' : 'none';
}
updateCustomForm();

// Функция для надевания/снятия брони через Fetch API
async function toggleArmorJS(charId, idx) {
    const btn = document.getElementById(`btn-armor-${idx}`);

    const originalText = btn.innerText;
    btn.innerText = "⏳...";
    btn.disabled = true;

    try {
        const response = await fetch(`/char/${charId}/armor/toggle/${idx}`, {
            method: 'POST',
            headers: {
                'Accept': 'application/json'
            }
        });

        if (response.ok) {
            const data = await response.json();

            document.getElementById('char-ac').innerText = data.new_ac;

            if (data.equipped) {
                // Хак для надежного обновления других кнопок того же типа (например, если снялась старая броня)
                location.reload();
            } else {
                btn.innerText = "Надеть";
                btn.classList.add('success');
            }
        } else {
            console.error("Ошибка при экипировке брони");
            btn.innerText = originalText;
        }
    } catch (error) {
        console.error("Сетевая ошибка:", error);
        btn.innerText = originalText;
    } finally {
        btn.disabled = false;
    }
}
