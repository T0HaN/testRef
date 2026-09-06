document.addEventListener('DOMContentLoaded', () => {
    const typeSelect = document.getElementById('asset_type');
    const metaContainer = document.getElementById('dynamic-metadata-container');
    const metaInput = document.getElementById('metadata_json');
    const assetForm = document.getElementById('asset-form');

    let meta = {};
    try {
        meta = JSON.parse(metaInput.value || '{}');
    } catch (e) {
        meta = {};
    }

    // Вспомогательная функция для добавления строчек действий/черт
    function createDynamicRow(targetContainer, nameVal = '', descVal = '') {
        const row = document.createElement('div');
        row.className = 'dynamic-item-row';
        row.innerHTML = `
            <div class="dynamic-row-inputs">
                <input type="text" class="item-name" placeholder="Название (напр. Укус)" value="${escapeHtml(nameVal)}">
                <textarea class="item-desc" rows="2" placeholder="Описание, модификаторы попадания и урон">${escapeHtml(descVal)}</textarea>
            </div>
            <button type="button" class="btn-remove-row" title="Удалить">✕</button>
        `;
        row.querySelector('.btn-remove-row').addEventListener('click', () => row.remove());
        targetContainer.appendChild(row);
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str).replace(/"/g, '&quot;');
    }

    // Рендереры шаблонов под каждый тип ассета
    const templates = {
        // --- 1. КАРТА ---
        map: () => `
            <div class="meta-block">
                <h4 class="meta-title">🗺️ Параметры боевой карты (Battlemap)</h4>
                <div class="form-row">
                    <div class="form-group">
                        <label>Ширина сетки (клеток)</label>
                        <input type="number" id="meta_grid_w" min="5" max="200" value="${meta.grid_width || 30}">
                    </div>
                    <div class="form-group">
                        <label>Высота сетки (клеток)</label>
                        <input type="number" id="meta_grid_h" min="5" max="200" value="${meta.grid_height || 30}">
                    </div>
                </div>
                <div class="form-group">
                    <label>Файл карты высокого разрешения (JPG, PNG, WEBP)</label>
                    <input type="file" name="content_file" accept="image/*">
                </div>
            </div>
        `,

        // --- 2. МОНСТР (STAT-BLOCK) ---
        // --- 2. МОНСТР (STAT-BLOCK) ---
        monster: () => {
            const attrs = meta.attributes || {};
            return `
            <div class="meta-block">
                <h4 class="meta-title">🐉 Лист монстра (Stat-block D&D 5e)</h4>

                <div class="form-group">
                    <label>Размер, тип и мировоззрение (мета-строка)</label>
                    <input type="text" id="meta_monster_meta" value="${meta.meta || ''}" placeholder="Средний гуманоид (любой расы), нейтральный">
                </div>

                <!-- Сетка боевых параметров (КД, ХП, Скорость, Опасность) -->
                <div class="monster-combat-grid">
                    <div class="form-group">
                        <label>КД (Armor Class)</label>
                        <input type="number" id="meta_ac" value="${meta.armor_class || 12}">
                    </div>
                    <div class="form-group">
                        <label>Хиты (HP)</label>
                        <input type="number" id="meta_hp" value="${meta.hit_points || 30}">
                    </div>
                    <div class="form-group">
                        <label>Кость хитов</label>
                        <input type="text" id="meta_hit_dice" value="${meta.hit_dice || '4d8+8'}" placeholder="4d8+8">
                    </div>
                    <div class="form-group">
                        <label>Скорость</label>
                        <input type="text" id="meta_speed" value="${meta.speed || '30 фт.'}" placeholder="30 фт.">
                    </div>
                    <div class="form-group full-width-sm">
                        <label>Опасность (CR)</label>
                        <input type="text" id="meta_cr" value="${meta.challenge_rating || '1'}" placeholder="1/4, 2, 5...">
                    </div>
                </div>

                <label style="margin-top: 1rem; margin-bottom: 0.4rem; display: block;">Характеристики и авто-модификаторы</label>
                <div class="stats-grid">
                    ${['str', 'dex', 'con', 'int', 'wis', 'cha'].map(stat => {
                        const val = attrs[stat] ?? 10;
                        const mod = Math.floor((val - 10) / 2);
                        const names = { str: 'СИЛ', dex: 'ЛОВ', con: 'ТЕЛ', int: 'ИНТ', wis: 'МДР', cha: 'ХАР' };
                        return `
                            <div class="stat-cell">
                                <span class="stat-name">${names[stat]}</span>
                                <input type="number" id="stat_${stat}" class="stat-val" value="${val}" min="1" max="30">
                                <span class="stat-mod" id="mod_${stat}">${mod >= 0 ? '+' + mod : mod}</span>
                            </div>
                        `;
                    }).join('')}
                </div>

                <!-- Секции списков с кнопками над ними -->
                <div class="dynamic-list-section">
                    <div class="section-title-row">
                        <label>Особенности и черты (Traits)</label>
                        <button type="button" class="btn-add-item" id="add-trait-btn">+ Добавить черту</button>
                    </div>
                    <div id="traits-container" class="items-stack"></div>
                </div>

                <div class="dynamic-list-section">
                    <div class="section-title-row">
                        <label>Действия (Actions)</label>
                        <button type="button" class="btn-add-item" id="add-action-btn">+ Добавить действие</button>
                    </div>
                    <div id="actions-container" class="items-stack"></div>
                </div>

                <div class="dynamic-list-section">
                    <div class="section-title-row">
                        <label>Легендарные действия (Legendary Actions)</label>
                        <button type="button" class="btn-add-item" id="add-leg-action-btn">+ Добавить действие</button>
                    </div>
                    <div id="leg-actions-container" class="items-stack"></div>
                </div>

                <div class="form-group" style="margin-top: 1.25rem;">
                    <label>Токен монстра для тактической карты (PNG / WEBP с прозрачностью)</label>
                    <input type="file" name="content_file" accept="image/png,image/webp">
                </div>
            </div>
            `;
        },

        // --- 3. ЗАКЛИНАНИЕ ---
        spell: () => {
            const classesList = ['Бард', 'Жрец', 'Друид', 'Паладин', 'Следопыт', 'Чародей', 'Колдун', 'Волшебник', 'Изобретатель'];
            const activeClasses = Array.isArray(meta.classes) ? meta.classes : [];
            const schools = ['Воплощение', 'Ограждение', 'Очарование', 'Иллюзия', 'Некромантия', 'Прорицание', 'Преобразование', 'Вызов'];

            return `
            <div class="meta-block">
                <h4 class="meta-title">✨ Свойства заклинания</h4>

                <div class="form-row">
                    <div class="form-group">
                        <label>Название (EN) <span class="hint-text">(для поиска по SRD)</span></label>
                        <input type="text" id="meta_spell_name_en" value="${meta.name_en || ''}" placeholder="Fireball">
                    </div>
                    <div class="form-group">
                        <label>Круг</label>
                        <select id="meta_spell_level">
                            ${[0,1,2,3,4,5,6,7,8,9].map(lvl => `
                                <option value="${lvl}" ${meta.level === lvl ? 'selected' : ''}>
                                    ${lvl === 0 ? 'Заговор (0 круг)' : lvl + ' круг'}
                                </option>
                            `).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Школа магии</label>
                        <select id="meta_spell_school">
                            ${schools.map(sc => `<option value="${sc}" ${meta.school === sc ? 'selected' : ''}>${sc}</option>`).join('')}
                        </select>
                    </div>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label>Время накладывания</label>
                        <input type="text" id="meta_spell_casting_time" value="${meta.casting_time || '1 действие'}" placeholder="1 действие / 1 бонусное действие">
                    </div>
                    <div class="form-group">
                        <label>Дистанция</label>
                        <input type="text" id="meta_spell_range" value="${meta.range || '150 футов'}" placeholder="На себя / 60 футов / Касание">
                    </div>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label>Компоненты</label>
                        <input type="text" id="meta_spell_components" value="${meta.components || 'В, С'}" placeholder="В, С, М (щепотка серы)">
                    </div>
                    <div class="form-group">
                        <label>Длительность</label>
                        <input type="text" id="meta_spell_duration" value="${meta.duration || 'Мгновенная'}" placeholder="Мгновенная / Концентрация 1 минута">
                    </div>
                </div>

                <div class="form-group">
                    <label>Доступно классам</label>
                    <div class="class-checkboxes-grid">
                        ${classesList.map(c => `
                            <label class="custom-checkbox">
                                <input type="checkbox" class="spell-class" value="${c}" ${activeClasses.includes(c) ? 'checked' : ''}>
                                <span>${c}</span>
                            </label>
                        `).join('')}
                    </div>
                </div>

                <div class="form-group">
                    <label>Источник (книга правил или модуль)</label>
                    <input type="text" id="meta_spell_source" value="${meta.source || 'Player’s Handbook'}" placeholder="Player’s Handbook / Homebrew">
                </div>
            </div>
            `;
        },

        // --- 4. КЛАСС ---
        class: () => `
            <div class="meta-block">
                <h4 class="meta-title">🛡️ Параметры класса / архетипа</h4>
                <div class="form-row">
                    <div class="form-group">
                        <label>Кость хитов (Hit Die)</label>
                        <select id="meta_hit_die">
                            <option value="d6" ${meta.hit_die === 'd6' ? 'selected' : ''}>d6 (Волшебник, Чародей)</option>
                            <option value="d8" ${meta.hit_die === 'd8' || !meta.hit_die ? 'selected' : ''}>d8 (Плут, Жрец, Бард, Монах)</option>
                            <option value="d10" ${meta.hit_die === 'd10' ? 'selected' : ''}>d10 (Воин, Паладин, Следопыт)</option>
                            <option value="d12" ${meta.hit_die === 'd12' ? 'selected' : ''}>d12 (Варвар)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Основная характеристика</label>
                        <input type="text" id="meta_primary_stat" value="${meta.primary_stat || 'Сила или Ловкость'}">
                    </div>
                </div>
            </div>
        `,

        // --- 5. МУЗЫКА ---
        music: () => `
            <div class="meta-block">
                <h4 class="meta-title">🎵 Аудио-дорожка и эмбиент</h4>
                <div class="form-row">
                    <div class="form-group">
                        <label>Тэги атмосферы (через запятую)</label>
                        <input type="text" id="meta_tags" value="${meta.tags || 'битва, подземелье, босс'}" placeholder="таверна, мистика, дождь">
                    </div>
                    <div class="form-group">
                        <label>Зацикленный трек (Loop)</label>
                        <select id="meta_loop">
                            <option value="true" ${meta.loop !== false ? 'selected' : ''}>Да (бесшовный повтор)</option>
                            <option value="false" ${meta.loop === false ? 'selected' : ''}>Нет (разовое воспроизведение)</option>
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label>Аудиофайл (MP3, OGG, WAV)</label>
                    <input type="file" name="content_file" accept="audio/*">
                </div>
            </div>
        `
    };

    function renderDynamicFields() {
        const selectedType = typeSelect.value;
        if (templates[selectedType]) {
            metaContainer.innerHTML = templates[selectedType]();

            if (selectedType === 'monster') {
                // Вешаем слушатели на расчёт характеристик
                ['str', 'dex', 'con', 'int', 'wis', 'cha'].forEach(s => {
                    const input = document.getElementById(`stat_${s}`);
                    const mod = document.getElementById(`mod_${s}`);
                    if (!input || !mod) return;
                    input.addEventListener('input', () => {
                        const val = parseInt(input.value) || 10;
                        const m = Math.floor((val - 10) / 2);
                        mod.textContent = m >= 0 ? '+' + m : m;
                    });
                });

                // Контейнеры и кнопки
                const traitsContainer = document.getElementById('traits-container');
                const actionsContainer = document.getElementById('actions-container');
                const legActionsContainer = document.getElementById('leg-actions-container');

                document.getElementById('add-trait-btn').addEventListener('click', () => createDynamicRow(traitsContainer));
                document.getElementById('add-action-btn').addEventListener('click', () => createDynamicRow(actionsContainer));
                document.getElementById('add-leg-action-btn').addEventListener('click', () => createDynamicRow(legActionsContainer));

                // Восстановление сохранённых черт при редактировании
                if (Array.isArray(meta.traits)) {
                    meta.traits.forEach(t => createDynamicRow(traitsContainer, t.name, t.description));
                }
                if (Array.isArray(meta.actions)) {
                    meta.actions.forEach(a => createDynamicRow(actionsContainer, a.name, a.description));
                }
                if (Array.isArray(meta.legendary_actions)) {
                    meta.legendary_actions.forEach(a => createDynamicRow(legActionsContainer, a.name, a.description));
                }
            }
        }
    }

    typeSelect.addEventListener('change', renderDynamicFields);
    renderDynamicFields();

    // Сборка JSON перед сабмитом формы
    assetForm.addEventListener('submit', () => {
        const type = typeSelect.value;
        const currentMeta = { ...meta };

        if (type === 'map') {
            currentMeta.grid_width = parseInt(document.getElementById('meta_grid_w')?.value) || 30;
            currentMeta.grid_height = parseInt(document.getElementById('meta_grid_h')?.value) || 30;
        } else if (type === 'monster') {
            currentMeta.meta = document.getElementById('meta_monster_meta')?.value.trim() || '';
            currentMeta.armor_class = parseInt(document.getElementById('meta_ac')?.value) || 10;
            currentMeta.hit_points = parseInt(document.getElementById('meta_hp')?.value) || 10;
            currentMeta.hit_dice = document.getElementById('meta_hit_dice')?.value.trim() || '1d8';
            currentMeta.speed = document.getElementById('meta_speed')?.value.trim() || '30 фт.';
            currentMeta.challenge_rating = document.getElementById('meta_cr')?.value.trim() || '1';

            currentMeta.attributes = {
                str: parseInt(document.getElementById('stat_str')?.value) || 10,
                dex: parseInt(document.getElementById('stat_dex')?.value) || 10,
                con: parseInt(document.getElementById('stat_con')?.value) || 10,
                int: parseInt(document.getElementById('stat_int')?.value) || 10,
                wis: parseInt(document.getElementById('stat_wis')?.value) || 10,
                cha: parseInt(document.getElementById('stat_cha')?.value) || 10
            };

            // Сбор динамических черт и действий
            const traits = [];
            document.querySelectorAll('#traits-container .dynamic-item-row').forEach(row => {
                const name = row.querySelector('.item-name')?.value.trim();
                const desc = row.querySelector('.item-desc')?.value.trim();
                if (name) traits.push({ name, description: desc });
            });
            currentMeta.traits = traits;

            const actions = [];
            document.querySelectorAll('#actions-container .dynamic-item-row').forEach(row => {
                const name = row.querySelector('.item-name')?.value.trim();
                const desc = row.querySelector('.item-desc')?.value.trim();
                if (name) actions.push({ name, description: desc });
            });
            currentMeta.actions = actions;

            const legActions = [];
            document.querySelectorAll('#leg-actions-container .dynamic-item-row').forEach(row => {
                const name = row.querySelector('.item-name')?.value.trim();
                const desc = row.querySelector('.item-desc')?.value.trim();
                if (name) legActions.push({ name, description: desc });
            });
            currentMeta.legendary_actions = legActions;

        } else if (type === 'spell') {
            const classes = [];
            document.querySelectorAll('.spell-class:checked').forEach(cb => classes.push(cb.value));

            currentMeta.name_en = document.getElementById('meta_spell_name_en')?.value.trim() || '';
            currentMeta.level = parseInt(document.getElementById('meta_spell_level')?.value) || 0;
            currentMeta.school = document.getElementById('meta_spell_school')?.value || 'Воплощение';
            currentMeta.casting_time = document.getElementById('meta_spell_casting_time')?.value.trim() || '1 действие';
            currentMeta.range = document.getElementById('meta_spell_range')?.value.trim() || '60 футов';
            currentMeta.components = document.getElementById('meta_spell_components')?.value.trim() || 'В, С';
            currentMeta.duration = document.getElementById('meta_spell_duration')?.value.trim() || 'Мгновенная';
            currentMeta.classes = classes;
            currentMeta.source = document.getElementById('meta_spell_source')?.value.trim() || 'Homebrew';
        } else if (type === 'class') {
            currentMeta.hit_die = document.getElementById('meta_hit_die')?.value || 'd8';
            currentMeta.primary_stat = document.getElementById('meta_primary_stat')?.value.trim() || '';
        } else if (type === 'music') {
            currentMeta.tags = document.getElementById('meta_tags')?.value.trim() || '';
            currentMeta.loop = document.getElementById('meta_loop')?.value === 'true';
        }

        metaInput.value = JSON.stringify(currentMeta);
    });
});