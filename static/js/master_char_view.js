function switchTab(tabId, btn) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

    document.getElementById(tabId).classList.add('active');
    btn.classList.add('active');

    // Сброс прокрутки при переключении
    const wrapper = document.querySelector('.tab-content-wrapper');
    if (wrapper) wrapper.scrollTop = 0;
}

function switchSpellTab(tabId, btn) {
    const parent = document.getElementById('spells');
    parent.querySelectorAll('.spells-grid').forEach(p => p.classList.remove('active'));
    parent.querySelectorAll('.spell-subtab').forEach(b => b.classList.remove('active'));
    document.getElementById(tabId + '-spells').classList.add('active');
    btn.classList.add('active');
}

function filterFeatures() {
    const query = document.getElementById('featuresSearch').value.toLowerCase();
    document.querySelectorAll('#featuresGrid .feature-card').forEach(card => {
        const name = card.dataset.name;
        card.style.display = name.includes(query) ? 'flex' : 'none';
    });
}

function filterSpells() {
    const query = document.getElementById('spellsSearch').value.toLowerCase();
    const activeTab = document.querySelector('#spells .spells-grid.active');
    if (activeTab) {
        activeTab.querySelectorAll('.spell-card').forEach(card => {
            const name = card.dataset.name;
            card.style.display = name.includes(query) ? 'flex' : 'none';
        });
    }
}
