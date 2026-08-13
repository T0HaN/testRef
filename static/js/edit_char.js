function updateMod(statKey, score) {
    score = parseInt(score) || 10;
    const mod = Math.floor((score - 10) / 2);
    const modStr = mod >= 0 ? `+${mod}` : `${mod}`;
    document.getElementById(`mod_${statKey}`).textContent = `Модификатор: ${modStr}`;
}
