        function parseDice(diceStr) {
            const match = diceStr.match(/(\d+)к(\d+)/i) || diceStr.match(/(\d+)d(\d+)/i);
            if (!match) return { count: 1, sides: 4 };
            return { count: parseInt(match[1]), sides: parseInt(match[2]) };
        }

        function rollDice(count, sides) {
            const rolls = [];
            for (let i = 0; i < count; i++) {
                rolls.push(Math.floor(Math.random() * sides) + 1);
            }
            return rolls;
        }

        function formatMod(mod) {
            return mod >= 0 ? `+${mod}` : `${mod}`;
        }

        function getTimeStr() {
            return new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        }

        function addDiceEntry(type, name, rolls, modifier, total, formula, extra) {
            const log = document.getElementById('diceLog');
            const empty = log.querySelector('.dice-empty');
            if (empty) empty.remove();

            const isCrit = rolls.length === 1 && rolls[0] === 20;
            const isFail = rolls.length === 1 && rolls[0] === 1;

            const rollsStr = rolls.join(' + ');
            const critClass = isCrit ? 'dice-crit' : '';
            const failClass = isFail ? 'dice-fail' : '';

            const entry = document.createElement('div');
            entry.className = 'dice-entry';
            entry.innerHTML = `
                <div class="dice-entry-header">
                    <span class="dice-entry-type">${type}</span>
                    <span class="dice-entry-time">${getTimeStr()}</span>
                </div>
                <div class="dice-entry-name">${name}</div>
                <div class="dice-entry-result">
                    <span class="dice-rolls ${critClass} ${failClass}">[${rollsStr}]</span>
                    <span class="dice-modifier">${formatMod(modifier)}</span>
                </div>
                <div class="dice-entry-result">
                    <span class="dice-total">${total}</span>
                    <span class="dice-formula">${formula}</span>
                </div>
                ${extra ? `<div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.3rem;">${extra}</div>` : ''}
                ${isCrit ? '<div style="font-size: 0.85rem; color: var(--accent-green); font-weight: bold;">🎯 КРИТИЧЕСКИЙ УСПЕХ!</div>' : ''}
                ${isFail ? '<div style="font-size: 0.85rem; color: var(--accent-red); font-weight: bold;">💀 КРИТИЧЕСКИЙ ПРОВАЛ!</div>' : ''}
            `;
            log.insertBefore(entry, log.firstChild);

            while (log.children.length > 20) {
                log.removeChild(log.lastChild);
            }
        }

        function clearDiceLog() {
            const log = document.getElementById('diceLog');
            log.innerHTML = `
                <div class="dice-empty">
                    <div class="icon">🎲</div>
                    <div>Кликни по характеристике,<br>навыку или оружию<br>для совершения броска</div>
                </div>
            `;
        }

        function rollStatCheck(statName, modifier) {
            const d20 = Math.floor(Math.random() * 20) + 1;
            const total = d20 + modifier;
            addDiceEntry('Проверка', `Характеристика: ${statName}`, [d20], modifier, total, `1к20 ${formatMod(modifier)} = ${total}`);
        }

        function rollSave(saveName, modifier, proficient, total) {
            const d20 = Math.floor(Math.random() * 20) + 1;
            const finalTotal = d20 + total;
            addDiceEntry('Спасбросок', `Спасбросок: ${saveName}`, [d20], total, finalTotal, `1к20 ${formatMod(total)} = ${finalTotal}`, proficient ? '✅ Владение' : '');
        }

        function rollSkill(skillName, modifier, proficient, total) {
            const d20 = Math.floor(Math.random() * 20) + 1;
            const finalTotal = d20 + total;
            addDiceEntry('Навык', `Навык: ${skillName}`, [d20], total, finalTotal, `1к20 ${formatMod(total)} = ${finalTotal}`, proficient ? '✅ Владение' : '');
        }

        function rollAttack(weaponName, attackBonus) {
            const d20 = Math.floor(Math.random() * 20) + 1;
            const total = d20 + attackBonus;
            const isCritRoll = d20 === 20;
            const isFailRoll = d20 === 1;

            let extraInfo = `Бонус: ${formatMod(attackBonus)}`;
            if (isCritRoll) extraInfo += ' 🎯 КРИТ!';
            if (isFailRoll) extraInfo += ' 💀 ПРОВАЛ!';

            addDiceEntry('Атака', `Оружие: ${weaponName}`, [d20], attackBonus, total, `1к20 ${formatMod(attackBonus)} = ${total}`, extraInfo);
        }

        function rollDamage(weaponName, damageDice, statMod) {
            const { count, sides } = parseDice(damageDice);
            const rolls = rollDice(count, sides);
            const baseDamage = rolls.reduce((a, b) => a + b, 0);
            const totalDamage = baseDamage + statMod;

            let formula = `${count}к${sides} + ${formatMod(statMod)} = ${totalDamage}`;
            addDiceEntry('Урон', `Урон: ${weaponName}`, rolls, statMod, totalDamage, formula, `База: ${baseDamage} + Мод: ${formatMod(statMod)}`);
        }
        // Загрузка токена
        async function uploadToken(event) {
            const file = event.target.files[0];
            if (!file) return;

            if (file.size > 2 * 1024 * 1024) {
                alert('Файл слишком большой! Максимум 2MB.');
                return;
            }

            const reader = new FileReader();
            reader.onload = async (e) => {
                const imageData = e.target.result;

                try {
                    const response = await fetch(`/char/${window.charData.id}/token/upload`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ image: imageData })
                    });

                    const result = await response.json();
                    if (result.status === 'ok') {
                        // Обновляем превью
                        const preview = document.getElementById('token-preview');
                        preview.innerHTML = `<img src="${imageData}" alt="Token" style="width: 100%; height: 100%; object-fit: cover;">`;
                        preview.style.borderStyle = 'solid';
                        preview.style.borderColor = 'var(--accent-gold)';
                        alert('✅ Токен загружен!');
                        location.reload();
                    } else {
                        alert('❌ Ошибка: ' + (result.error || 'неизвестно'));
                    }
                } catch (err) {
                    alert('❌ Ошибка загрузки: ' + err.message);
                }
            };
            reader.readAsDataURL(file);
        }
