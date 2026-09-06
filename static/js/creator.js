document.addEventListener('DOMContentLoaded', () => {
    const typeSelect = document.getElementById('asset_type');
    const metaContainer = document.getElementById('dynamic-metadata-container');
    const metaInput = document.getElementById('metadata_json');
    const assetForm = document.getElementById('asset-form');

    let currentMetadata = {};
    try {
        currentMetadata = JSON.parse(metaInput.value || '{}');
    } catch (e) {
        currentMetadata = {};
    }

    const renderers = {
        map: () => `
            <div class="meta-block">
                <h4 class="meta-title">🗺️ Параметры тактической карты</h4>
                <div class="form-row">
                    <div class="form-group">
                        <label>Ширина сетки (клеток)</label>
                        <input type="number" id="meta_grid_w" value="${currentMetadata.grid_width || 30}">
                    </div>
                    <div class="form-group">
                        <label>Высота сетки (клеток)</label>
                        <input type="number" id="meta_grid_h" value="${currentMetadata.grid_height || 30}">
                    </div>
                </div>
                <div class="form-group">
                    <label>Файл карты высокого разрешения (JPG / WEBP)</label>
                    <input type="file" name="content_file" accept="image/*">
                </div>
            </div>
        `,
        monster: () => `
            <div class="meta-block">
                <h4 class="meta-title">🐉 Характеристики монстра</h4>
                <div class="form-row">
                    <div class="form-group">
                        <label>Класс брони (AC)</label>
                        <input type="number" id="meta_ac" value="${currentMetadata.ac || 12}">
                    </div>
                    <div class="form-group">
                        <label>Очки здоровья (HP)</label>
                        <input type="text" id="meta_hp" value="${currentMetadata.hp || '45 (6d8 + 18)'}">
                    </div>
                    <div class="form-group">
                        <label>Опасность (CR)</label>
                        <input type="text" id="meta_cr" value="${currentMetadata.cr || '2'}">
                    </div>
                </div>
                <div class="form-group">
                    <label>Токен монстра (PNG на прозрачном фоне)</label>
                    <input type="file" name="content_file" accept="image/png,image/webp">
                </div>
            </div>
        `,
        spell: () => `
            <div class="meta-block">
                <h4 class="meta-title">✨ Свойства заклинания</h4>
                <div class="form-row">
                    <div class="form-group">
                        <label>Круг (0 = заговор)</label>
                        <input type="number" id="meta_level" min="0" max="9" value="${currentMetadata.level || 1}">
                    </div>
                    <div class="form-group">
                        <label>Школа магии</label>
                        <input type="text" id="meta_school" value="${currentMetadata.school || 'Воплощение'}">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Дистанция</label>
                        <input type="text" id="meta_range" value="${currentMetadata.range || '60 футов'}">
                    </div>
                    <div class="form-group">
                        <label>Длительность</label>
                        <input type="text" id="meta_duration" value="${currentMetadata.duration || 'Мгновенная'}">
                    </div>
                </div>
            </div>
        `,
        music: () => `
            <div class="meta-block">
                <h4 class="meta-title">🎵 Аудио-дорожка</h4>
                <div class="form-row">
                    <div class="form-group">
                        <label>Атмосфера (Тэги через запятую)</label>
                        <input type="text" id="meta_tags" value="${currentMetadata.tags || 'боевая, подземелье'}">
                    </div>
                    <div class="form-group">
                        <label>Зацикленный трек (Loop)</label>
                        <select id="meta_loop">
                            <option value="true" ${currentMetadata.loop !== false ? 'selected' : ''}>Да</option>
                            <option value="false" ${currentMetadata.loop === false ? 'selected' : ''}>Нет</option>
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label>Аудиофайл (MP3 / OGG)</label>
                    <input type="file" name="content_file" accept="audio/*">
                </div>
            </div>
        `,
        class: () => `
            <div class="meta-block">
                <h4 class="meta-title">🛡️ Параметры класса</h4>
                <div class="form-row">
                    <div class="form-group">
                        <label>Кость хитов</label>
                        <input type="text" id="meta_hit_die" value="${currentMetadata.hit_die || 'd8'}">
                    </div>
                    <div class="form-group">
                        <label>Основная характеристика</label>
                        <input type="text" id="meta_primary_stat" value="${currentMetadata.primary_stat || 'Ловкость'}">
                    </div>
                </div>
            </div>
        `
    };

    function updateFields() {
        const type = typeSelect.value;
        if (renderers[type]) {
            metaContainer.innerHTML = renderers[type]();
        }
    }

    typeSelect.addEventListener('change', updateFields);
    updateFields(); // Первичная отрисовка

    // Перед отправкой сериализуем значения формы в JSON
    assetForm.addEventListener('submit', () => {
        const type = typeSelect.value;
        const meta = { ...currentMetadata };

        if (type === 'map') {
            meta.grid_width = parseInt(document.getElementById('meta_grid_w')?.value || 30);
            meta.grid_height = parseInt(document.getElementById('meta_grid_h')?.value || 30);
        } else if (type === 'monster') {
            meta.ac = parseInt(document.getElementById('meta_ac')?.value || 10);
            meta.hp = document.getElementById('meta_hp')?.value || '';
            meta.cr = document.getElementById('meta_cr')?.value || '1';
        } else if (type === 'spell') {
            meta.level = parseInt(document.getElementById('meta_level')?.value || 0);
            meta.school = document.getElementById('meta_school')?.value || '';
            meta.range = document.getElementById('meta_range')?.value || '';
            meta.duration = document.getElementById('meta_duration')?.value || '';
        } else if (type === 'music') {
            meta.tags = document.getElementById('meta_tags')?.value || '';
            meta.loop = document.getElementById('meta_loop')?.value === 'true';
        } else if (type === 'class') {
            meta.hit_die = document.getElementById('meta_hit_die')?.value || 'd8';
            meta.primary_stat = document.getElementById('meta_primary_stat')?.value || '';
        }

        metaInput.value = JSON.stringify(meta);
    });
});