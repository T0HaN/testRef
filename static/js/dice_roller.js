// dice_roller.js - Бросок кубов

let rollCount = 0;
let abilitiesData = {};

function initDiceRoller(abilities) {
    abilitiesData = abilities;
}

function rollDice(sides) {
    const result = Math.floor(Math.random() * sides) + 1;
    displayResult(`d${sides}`, result, result, `${result}`, false);
    addToHistory(`d${sides}`, result);
}

function rollAbilityCheck(abilityKey, modifier) {
    const roll = Math.floor(Math.random() * 20) + 1;
    const total = roll + modifier;
    const breakdown = `${roll} ${modifier >= 0 ? '+' : ''}${modifier}`;
    const isCrit = roll === 20;
    const isFail = roll === 1;
    displayResult(`Проверка ${abilitiesData[abilityKey].name}`, roll, total, breakdown, isCrit, isFail);
    addToHistory(`${abilitiesData[abilityKey].name}`, total, isCrit, isFail);
}

function rollSkillCheck(skillName, bonus) {
    const roll = Math.floor(Math.random() * 20) + 1;
    const total = roll + bonus;
    const breakdown = `${roll} ${bonus >= 0 ? '+' : ''}${bonus}`;
    const isCrit = roll === 20;
    const isFail = roll === 1;
    displayResult(`Навык ${skillName}`, roll, total, breakdown, isCrit, isFail);
    addToHistory(skillName, total, isCrit, isFail);
}

function rollCustom() {
    const formula = document.getElementById('customFormula').value.trim();
    if (!formula) {
        alert('Введите формулу броска!');
        return;
    }

    try {
        const result = parseAndRoll(formula);
        displayResult('Индивидуальный бросок', result.total, result.total, result.breakdown, false, false);
        addToHistory(formula, result.total);
    } catch (e) {
        alert('Ошибка в формуле! Пример: 2d6+3 или 1d20+5');
    }
}

function parseAndRoll(formula) {
    const parts = formula.toLowerCase().split(/([+-])/);
    let total = 0;
    let breakdown = [];

    for (let i = 0; i < parts.length; i += 2) {
        const part = parts[i].trim();
        const sign = i === 0 ? '+' : parts[i-1];

        if (part.includes('d')) {
            const [count, sides] = part.split('d').map(Number);
            let rollSum = 0;
            for (let j = 0; j < count; j++) {
                rollSum += Math.floor(Math.random() * sides) + 1;
            }
            total += sign === '+' ? rollSum : -rollSum;
            breakdown.push(`${sign} ${rollSum} (${count}d${sides})`);
        } else if (part) {
            const num = parseInt(part);
            total += sign === '+' ? num : -num;
            breakdown.push(`${sign} ${num}`);
        }
    }

    return { total, breakdown: breakdown.join(' ') };
}

function displayResult(title, roll, total, breakdown, isCrit = false, isFail = false) {
    rollCount++;
    const container = document.getElementById('resultContainer');

    let resultClass = '';
    let resultText = '';

    if (isCrit) {
        resultClass = 'crit-success';
        resultText = 'КРИТИЧЕСКИЙ УСПЕХ!';
    } else if (isFail) {
        resultClass = 'crit-fail';
        resultText = 'КРИТИЧЕСКИЙ ПРОВАЛ!';
    } else if (total >= 15) {
        resultClass = 'success';
        resultText = 'УСПЕХ';
    } else {
        resultClass = 'fail';
        resultText = 'НЕУДАЧА';
    }

    container.innerHTML = `
        <div class="roll-result ${resultClass} rolling">
            <div class="result-header">${title}</div>
            <div class="result-dice">🎲 ${roll}</div>
            <div class="result-total">${total}</div>
            <div class="result-breakdown">${breakdown}</div>
            <div class="result-type">${resultText}</div>
        </div>
    `;

    setTimeout(() => {
        container.querySelector('.roll-result').classList.remove('rolling');
    }, 500);
}

function addToHistory(name, result, isCrit = false, isFail = false) {
    const history = document.getElementById('rollHistory');
    const time = new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    if (rollCount === 1) {
        history.innerHTML = '';
    }

    const item = document.createElement('div');
    item.className = `history-item ${isCrit || isFail ? 'crit' : ''}`;
    item.innerHTML = `
        <div>
            <div style="font-weight: 600;">${name}</div>
            <div class="history-time">${time}</div>
        </div>
        <div class="history-result">${result}</div>
    `;

    history.insertBefore(item, history.firstChild);

    if (history.children.length > 20) {
        history.removeChild(history.lastChild);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    console.log('Dice Roller page loaded');
});
