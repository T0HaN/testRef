    // ==================== ДАННЫЕ ПЕРСОНАЖА ====================
    const myCharId = String(window.charData.id);
    const myCharName = window.charData.name;
    const myUsername = window.userData.username;
    const myTokenImage = window.charData.token_image || "";
    const maxHp = window.charData.hp.max;
    const TOKEN_SIZE = 60;

    // --- Управление панелью вкладок ---
    const slidePanel = document.getElementById('slidePanel');
    const panelTitle = document.getElementById('panelTitle');
    const tabBtns = document.querySelectorAll('.icon-tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    const titles = {
        'players': 'Участники',
        'dice': 'Броски кубов',
        'combat': 'Трекер боя',
        'weapons': 'Оружие и Атаки',
        'checks': 'Проверки',
        'inventory': 'Инвентарь',
        'spells': 'Заклинания'
    };

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');
            if (btn.classList.contains('active')) { closePanel(); return; }

            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            btn.classList.add('active');

            const content = document.getElementById('tab-' + tabId);
            if(content) content.classList.add('active');

            panelTitle.textContent = titles[tabId] || 'Панель';
            slidePanel.classList.add('open');
        });
    });

    function closePanel() {
        slidePanel.classList.remove('open');
        tabBtns.forEach(b => b.classList.remove('active'));
    }

    // --- Управление виджетом хитов ---
    const hpToggleBtn = document.getElementById('hpToggleBtn');
    const floatingHp = document.getElementById('floatingHp');

    hpToggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        floatingHp.classList.toggle('show');
    });
    document.addEventListener('click', (e) => {
        if (!floatingHp.contains(e.target) && !hpToggleBtn.contains(e.target)) {
            floatingHp.classList.remove('show');
        }
    });

    // --- Управление Чатом (Панель) ---
    function toggleRightPanel() {
        const rightPanel = document.getElementById('rightPanel');
        const chatToggleBtn = document.getElementById('chatToggleBtn');
        rightPanel.classList.toggle('collapsed');
        chatToggleBtn.textContent = rightPanel.classList.contains('collapsed') ? '◀' : '▶';
    }

    // ==================== ЛЕНИВАЯ ЗАГРУЗКА ИСТОРИИ (LAZY LOADING) ====================
    let chatOffset = window.roomData.chatHistoryLength;
    let isLoadingChat = false;
    let allChatLoaded = false;
    const chatLog = document.getElementById('chatLog');

    window.addEventListener('DOMContentLoaded', () => {
        chatLog.scrollTop = chatLog.scrollHeight;
    });

    chatLog.addEventListener('scroll', async () => {
        if (chatLog.scrollTop <= 1 && !isLoadingChat && !allChatLoaded) {
            await loadOlderMessages();
        }
    });

    async function loadOlderMessages() {
        isLoadingChat = true;
        const loader = document.getElementById('chatLoader');
        if (loader) loader.style.display = 'block';

        try {
            const response = await fetch(`/api/room/${window.roomData.id}/chat/history?offset=${chatOffset}&limit=20`);
            const data = await response.json();

            if (!data.messages || data.messages.length === 0) {
                allChatLoaded = true;
                if (!document.getElementById('chatStart')) {
                    const start = document.createElement('div');
                    start.id = 'chatStart';
                    start.style.cssText = 'text-align: center; color: var(--text-secondary); font-size: 0.85rem; margin-top: 1rem; margin-bottom: 1rem; opacity: 0.5;';
                    start.textContent = 'Начало сессии...';
                    chatLog.insertBefore(start, loader ? loader.nextSibling : chatLog.firstChild);
                }
                return;
            }

            const oldScrollHeight = chatLog.scrollHeight;
            const fragment = document.createDocumentFragment();

            data.messages.forEach(msg => {
                const el = createMessageElement(msg);
                if (el) fragment.appendChild(el);
            });

            chatLog.insertBefore(fragment, loader ? loader.nextSibling : chatLog.firstChild);
            chatLog.scrollTop = chatLog.scrollHeight - oldScrollHeight;
            chatOffset += data.messages.length;

        } catch (err) {
            console.error("Ошибка загрузки истории:", err);
        } finally {
            isLoadingChat = false;
            if (loader) loader.style.display = 'none';
        }
    }

    function escapeHtmlText(str) {
        if (!str) return '';
        return String(str).replace(/[&<>"']/g, function(m) {
            return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];
        });
    }

    function createMessageElement(data) {
        const isSelf = data.username === myUsername;
        const author = data.char_name || data.username || 'Неизвестно';
        const entry = document.createElement('div');

        if (data.type === 'chat_message') {
            entry.className = 'chat-msg' + (isSelf ? ' self' : '');
            entry.innerHTML = `
                <div class="author">${data.is_master ? '👑' : '🎭'} ${escapeHtmlText(author)}</div>
                <div class="text">${escapeHtmlText(data.text)}</div>
            `;
            return entry;
        } else if (data.type === 'dice_roll') {

            if (data.is_hidden) {
                entry.className = 'dice-entry';
                entry.innerHTML = `
                    <div style="font-size: 0.75rem; color: var(--accent-gold); margin-bottom: 0.25rem;">
                        👑 <strong>${escapeHtmlText(author)}</strong>
                    </div>
                    <div style="font-weight: 600; color: var(--text-secondary); font-style: italic;">совершает тайный бросок 🎲...</div>
                `;
                return entry;
            }

            entry.className = 'dice-entry' + (data.is_crit ? ' crit' : '') + (data.is_fail ? ' fail' : '');
            const name = data.name || `d${data.sides}`;
            let modifierStr = '';
            if (data.modifier !== 0) modifierStr = data.modifier > 0 ? ` +${data.modifier}` : ` ${data.modifier}`;

            let resultTags = '';
            if (data.is_crit) resultTags += ' 🎯 КРИТ!';
            if (data.is_fail) resultTags += ' 💀 ПРОВАЛ!';

            entry.innerHTML = `
                <div style="font-size: 0.75rem; color: ${isSelf ? 'var(--accent-gold-dim)' : 'var(--accent-gold)'}; margin-bottom: 0.25rem;">
                    ${data.is_master ? '👑' : '🎭'} <strong>${escapeHtmlText(author)}</strong>
                </div>
                <div style="font-weight: 600; color: var(--text-primary);">${escapeHtmlText(name)}</div>
                <div class="roll">${data.total}</div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.2rem;">
                    [${data.roll}]${modifierStr}${resultTags}
                </div>
            `;
            return entry;
        }
        return null;
    }

    // ==================== WEBSOCKET ====================
    let roomWs = null;
    let isMaster = false;

    function connectWs() {
        roomWs = new WebSocket(`/ws/room/${window.roomData.id}`);

        roomWs.onopen = () => {
            console.log('WebSocket подключён');
            roomWs.send(JSON.stringify({ username: myUsername, char_name: myCharName }));
            updateTokenButtons();
        };

        roomWs.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleWsMessage(data);
        };

        roomWs.onclose = () => {
            console.log('WebSocket отключён. Переподключение через 3 сек...');
            setTimeout(connectWs, 3000);
        };
    }

    connectWs();

    function handleWsMessage(data) {
        switch (data.type) {
            case 'init':
                isMaster = data.is_master;
                break;
            case 'map_update':
                loadMapFromData(data.image, data.width, data.height);
                break;
            case 'map_clear':
                mapImage = null;
                drawings = [];
                fowPaths = [];
                renderFowCanvas();
                document.getElementById('vtt-placeholder').style.display = 'flex';
                render();
                break;
            case 'fow_sync':
                fowPaths = data.fow_paths || [];
                renderFowCanvas();
                render();
                break;
            case 'draw_init':
                drawings = data.drawings || [];
                render();
                break;
            case 'draw_line':
                drawings.push(data.line);
                render();
                break;
            case 'draw_clear':
                drawings = [];
                render();
                break;

            case 'measure':
                if (data.username !== myUsername) {
                    activeMeasurements[data.username] = { start: data.start, end: data.end, color: data.color };
                    render();
                }
                break;

            case 'dice_roll':
                addDiceEntryFromServer(data);
                break;
            case 'chat_message':
                addChatMessageFromServer(data);
                break;
            case 'combat_update':
                combatants = data.combatants;
                renderCombatList();
                break;
            case 'tokens_init':
                allTokens = {};
                data.tokens.forEach(t => {
                    allTokens[t.char_id || t.token_id] = t;
                    preloadTokenImage(t);
                });
                render();
                updateTokenButtons();
                break;
            case 'token_add':
                allTokens[data.token.char_id || data.token.token_id] = data.token;
                preloadTokenImage(data.token);
                render();
                updateTokenButtons();
                break;
            case 'token_remove':
                if (data.is_monster && data.name) showDeathNotification(data.name);
                delete allTokens[data.char_id || data.token_id];
                render();
                updateTokenButtons();
                break;
            case 'token_move':
                const moveId = data.token.char_id || data.token.token_id;
                if (allTokens[moveId]) {
                    allTokens[moveId].x = data.token.x;
                    allTokens[moveId].y = data.token.y;
                    if (data.token.width !== undefined) allTokens[moveId].width = data.token.width;
                    if (data.token.height !== undefined) allTokens[moveId].height = data.token.height;
                    render();
                }
                break;
            case 'hp_update':
                if (String(data.char_id) === String(myCharId)) {
                    updateHpDisplays(data.hp_current);
                    if (data.hp_current <= 0) showUnconsciousNotification(data.username || myCharName);
                }
                const tokenIdInCombat = String(data.char_id);
                const combatant = combatants.find(c => String(c.token_id) === tokenIdInCombat || String(c.char_id) === tokenIdInCombat);
                if (combatant) {
                    combatant.hp_current = data.hp_current;
                    combatant.hp_max = data.hp_max;
                    renderCombatList();
                }
                break;
            case 'player_join':
                if (data.username !== myUsername) {
                    addSystemChatMessage('🟢', data.char_name || data.username, 'присоединился к игре.');
                    refreshPlayersTab();
                }
                break;
            case 'player_leave':
                addSystemChatMessage('🔴', data.char_name || data.username, 'покинул игру.');
                refreshPlayersTab();
                break;
            case 'grid_size_update':
                gridSize = data.grid_size;
                render();
                break;
            case 'tokens_clear':
                allTokens = {};
                combatants = [];
                renderCombatList();
                render();
                updateTokenButtons();
                break;
        }
    }

    // ==================== ЧАТ И БРОСКИ (ЛОГИКА) ====================
    function sendDiceRoll(name, roll, sides, modifier, total, isCrit, isFail, isHidden = false) {
        if (roomWs && roomWs.readyState === WebSocket.OPEN) {
            roomWs.send(JSON.stringify({
                type: 'dice_roll',
                name, roll, sides, modifier, total,
                is_crit: isCrit, is_fail: isFail,
                is_hidden: isHidden
            }));
        }
    }

    function rollDice(sides, customName) {
        const name = customName || document.getElementById('check-name')?.value || `d${sides}`;
        const roll = Math.floor(Math.random() * sides) + 1;
        const isCrit = sides === 20 && roll === 20;
        const isFail = sides === 20 && roll === 1;
        sendDiceRoll(name, roll, sides, 0, roll, isCrit, isFail, false);
        document.getElementById('check-name').value = '';
    }

    function rollCheck(name = 'Проверка', modifier = 0) {
        const roll = Math.floor(Math.random() * 20) + 1;
        const total = roll + modifier;
        sendDiceRoll(name, roll, 20, modifier, total, roll === 20, roll === 1, false);
    }

    function rollAttack(weaponName, attackBonus) {
        const roll = Math.floor(Math.random() * 20) + 1;
        sendDiceRoll(`Атака: ${weaponName}`, roll, 20, attackBonus, roll + attackBonus, roll === 20, roll === 1, false);
    }

    function rollDamage(weaponName, damageDice, statMod) {
        const match = damageDice.match(/(\d+)к(\d+)/i) || damageDice.match(/(\d+)d(\d+)/i);
        if (!match) return;
        const count = parseInt(match[1]);
        const sides = parseInt(match[2]);
        let total = statMod;
        for (let i = 0; i < count; i++) total += Math.floor(Math.random() * sides) + 1;
        sendDiceRoll(`Урон: ${weaponName}`, total, sides, statMod, total, false, false, false);
    }

    function sendChatMessage() {
        const input = document.getElementById('chatInput');
        const text = input.value.trim();
        if (!text) return;
        if (roomWs && roomWs.readyState === WebSocket.OPEN) {
            roomWs.send(JSON.stringify({ type: 'chat_message', text: text }));
            input.value = '';
        }
    }

    function addDiceEntryFromServer(data) {
        const entry = createMessageElement(data);
        if (entry) {
            chatLog.appendChild(entry);
            chatOffset++;
            scrollToBottomLog();
            const startMsg = document.getElementById('chatStart');
            if (startMsg) startMsg.style.display = 'none';
        }
    }

    function addChatMessageFromServer(data) {
        const entry = createMessageElement(data);
        if (entry) {
            chatLog.appendChild(entry);
            chatOffset++;
            scrollToBottomLog();
            const startMsg = document.getElementById('chatStart');
            if (startMsg) startMsg.style.display = 'none';
        }
    }

    // ==================== УВЕДОМЛЕНИЯ ====================
    function showDeathNotification(monsterName) {
        const n = document.createElement('div');
        n.innerHTML = `💀 <strong>${escapeHtmlText(monsterName)}</strong> повержен!`;
        n.style.cssText = `position:fixed; top:50%; left:50%; transform:translate(-50%,-50%) scale(0.8); background:linear-gradient(145deg,rgba(139,58,58,0.95),rgba(80,20,20,0.95)); color:#e0d4b8; padding:1.5rem 2.5rem; border-radius:12px; border:2px solid #c9a961; box-shadow:0 10px 40px rgba(0,0,0,0.8); z-index:10000; font-family:'Georgia',serif; font-size:1.3rem; text-align:center; opacity:0; transition:all 0.4s ease; pointer-events:none;`;
        document.body.appendChild(n);
        requestAnimationFrame(() => { n.style.opacity = '1'; n.style.transform = 'translate(-50%,-50%) scale(1)'; });
        setTimeout(() => { n.style.opacity = '0'; n.style.transform = 'translate(-50%,-50%) scale(1.1)'; setTimeout(() => n.remove(), 400); }, 3000);
    }

    function showUnconsciousNotification(charName) {
        const n = document.createElement('div');
        n.innerHTML = `💀 <strong>${escapeHtmlText(charName)}</strong> без сознания!<br><span style="font-size:0.9rem;opacity:0.8;">Делает спасброски от смерти...</span>`;
        n.style.cssText = `position:fixed; top:50%; left:50%; transform:translate(-50%,-50%) scale(0.8); background:linear-gradient(145deg,rgba(139,58,58,0.95),rgba(80,20,20,0.95)); color:#e0d4b8; padding:1.5rem 2.5rem; border-radius:12px; border:2px solid #c9a961; box-shadow:0 10px 40px rgba(0,0,0,0.8); z-index:10000; font-family:'Georgia',serif; font-size:1.3rem; text-align:center; opacity:0; transition:all 0.4s ease; pointer-events:none;`;
        document.body.appendChild(n);
        requestAnimationFrame(() => { n.style.opacity = '1'; n.style.transform = 'translate(-50%,-50%) scale(1)'; });
        setTimeout(() => { n.style.opacity = '0'; n.style.transform = 'translate(-50%,-50%) scale(1.1)'; setTimeout(() => n.remove(), 400); }, 4000);
    }

    // ==================== УПРАВЛЕНИЕ ХИТАМИ И МОНЕТАМИ ====================
    function updateHpDisplays(newHp) {
        document.getElementById('hp-float-val').textContent = newHp;
        document.getElementById('hp-mini-val').textContent = newHp;
    }

    function adjustPlayerHp(amount) {
        let current = parseInt(document.getElementById('hp-float-val').textContent);
        let newVal = Math.max(0, Math.min(current + amount, maxHp));
        updateHpDisplays(newVal);

        const formData = new FormData();
        formData.append('username', myUsername);
        formData.append('current_hp', newVal);
        formData.append('temp_hp', window.charData.hp.temp);
        formData.append('room_id', window.roomData.id);

        fetch(`/char/${window.charData.id}/hp`, { method: 'POST', body: formData }).catch(console.error);

        if (roomWs && roomWs.readyState === WebSocket.OPEN) {
            roomWs.send(JSON.stringify({ type: 'combatant_hp_update', token_id: myCharId, hp_current: newVal }));
        }
    }

    function syncCoins() {
        const gp = document.getElementById('coin-gp').value || 0;
        const sp = document.getElementById('coin-sp').value || 0;
        const cp = document.getElementById('coin-cp').value || 0;

        const formData = new FormData();
        formData.append('gp', gp);
        formData.append('sp', sp);
        formData.append('cp', cp);

        fetch(`/char/${window.charData.id}/coins/set`, { method: 'POST', body: formData }).catch(console.error);
    }

    // ==================== БОЕВОЙ ТРЕКЕР ====================
    let combatants = [];

    function renderCombatList() {
        const container = document.getElementById('combat-list');
        if (!container) return;

        combatants.sort((a, b) => b.initiative - a.initiative);

        if (combatants.length === 0) {
            container.innerHTML = '<div style="color: var(--text-secondary); text-align: center; margin-top: 2rem;">Бой еще не начался</div>';
            return;
        }

        let html = '';
        combatants.forEach(c => {
            const borderColor = c.is_monster ? 'var(--accent-red)' : 'var(--accent-gold)';
            const isSelf = String(c.token_id) === String(myCharId) || String(c.char_id) === String(myCharId);
            const hpCurrent = (c.hp_current !== undefined && c.hp_current !== null) ? c.hp_current : 0;
            const hpMax = (c.hp_max !== undefined && c.hp_max !== null) ? c.hp_max : '?';
            const isUnconscious = hpCurrent <= 0;

            const bgIcon = c.image
                ? `<img src="${escapeHtmlText(c.image)}" style="width: 36px; height: 36px; border-radius: 50%; object-fit: cover; border: 2px solid ${isUnconscious ? '#ff0000' : borderColor};">`
                : `<div style="width: 36px; height: 36px; border-radius: 50%; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; border: 2px solid ${isUnconscious ? '#ff0000' : borderColor}; font-size: 1.2rem;">${c.is_monster ? '' : '🎭'}</div>`;

            html += `
            <div class="player-card" style="padding: 0.5rem; ${isUnconscious ? 'opacity: 0.6;' : ''}">
                ${bgIcon}
                <div class="info" style="flex:1;">
                    <div class="char-name" style="color: ${isSelf ? 'var(--accent-gold)' : 'var(--text-primary)'};">${escapeHtmlText(c.name)} ${isSelf ? '(вы)' : ''}</div>
                    ${isUnconscious ? `<div style="font-size: 0.7rem; color: #ff4444; font-weight: bold;">💀 Без сознания</div>` : (hpMax !== '?' ? `<div style="font-size: 0.7rem; color: var(--text-secondary);">❤️ ${escapeHtmlText(hpCurrent)}/${escapeHtmlText(hpMax)}</div>` : '')}
                </div>
                <div style="background: var(--bg-tertiary); border-radius: 4px; padding: 0.3rem 0.6rem; text-align: center;">
                    <div style="font-size: 0.6rem; color: var(--text-secondary);">ИНИЦ</div>
                    <div style="font-size: 1.1rem; font-weight: bold; color: var(--accent-gold); line-height: 1;">${c.initiative}</div>
                </div>
            </div>`;
        });
        container.innerHTML = html;
    }

    // ==================== VTT CANVAS & TOKENS ====================
    function sendTokenUpdate(action, tokenData) {
        if (roomWs && roomWs.readyState === WebSocket.OPEN) {
            roomWs.send(JSON.stringify({ type: 'token_update', action: action, token: tokenData }));
        }
    }

    let allTokens = {};
    let tokenImages = {};

    function preloadTokenImage(token) {
        const id = token.char_id || token.token_id;
        if (!token.image || tokenImages[id]) return;
        const img = new Image();
        img.onload = () => {
            tokenImages[id] = img;
            render();
        };
        img.src = token.image;
    }

    function updateTokenButtons() {
        const addBtn = document.getElementById('btnAddToken');
        const removeBtn = document.getElementById('btnRemoveToken');
        const hasValidToken = myTokenImage && myTokenImage.length > 100;

        if (!hasValidToken) {
            addBtn.disabled = true;
            addBtn.title = 'Загрузите токен в листе персонажа';
        } else {
            addBtn.disabled = false;
            addBtn.title = 'Добавить мой токен на карту';
        }

        removeBtn.disabled = !allTokens[String(myCharId)];
    }

    function addMyToken() {
        if (!myTokenImage || !mapImage || allTokens[myCharId]) return;

        const dexMod = window.charData.stats.DEX.modifier;
        const roll = Math.floor(Math.random() * 20) + 1;
        const initiative = roll + dexMod;

        const token = {
            char_id: myCharId,
            char_name: myCharName,
            image: myTokenImage,
            x: mapNaturalWidth / 2,
            y: mapNaturalHeight / 2,
            size: TOKEN_SIZE,
            width: TOKEN_SIZE,
            height: TOKEN_SIZE,
            initiative: initiative,
            dex_mod: dexMod,
            ac: window.charData.attributes.ac,
            hp_current: window.charData.hp.current,
            hp_max: window.charData.hp.max,
            is_monster: false
        };

        sendTokenUpdate('add', token);
    }

    function removeMyToken() {
        if (allTokens[myCharId]) sendTokenUpdate('remove', { char_id: myCharId });
    }

    const canvas = document.getElementById('vtt-canvas');
    const ctx = canvas.getContext('2d');
    const container = document.getElementById('vttContainer');

    let mapImage = null;
    let mapNaturalWidth = 0;
    let mapNaturalHeight = 0;
    let view = { x: 0, y: 0, scale: 1 };

    let gridVisible = true;
    let gridSize = 50;
    let drawings = [];

    // ТУМАН ВОЙНЫ
    let fowCanvas = document.createElement('canvas');
    let fCtx = fowCanvas.getContext('2d');
    let fowPaths = [];
    const PLAYER_FOG_COLOR = '#0a0a0c';

    let isPanning = false;
    let panStart = { x: 0, y: 0 };
    let viewStart = { x: 0, y: 0 };
    let draggingToken = null;
    let dragOffset = { x: 0, y: 0 };

    let currentMode = 'move';
    let activeMeasurements = {};
    let measureStart = null;
    let measureEnd = null;

    function setTool(mode) {
        currentMode = mode;
        document.getElementById('toolMove').classList.toggle('active', mode === 'move');
        document.getElementById('toolRuler').classList.toggle('active', mode === 'ruler');
        canvas.className = `mode-${mode}`;
    }

    function resizeCanvas() {
        if (canvas.width === container.clientWidth && canvas.height === container.clientHeight) return;
        canvas.width = container.clientWidth;
        canvas.height = container.clientHeight;
        render();
    }

    const vttObserver = new ResizeObserver(() => {
        requestAnimationFrame(resizeCanvas);
    });
    vttObserver.observe(container);

    function renderFowCanvas() {
        if (!mapImage) return;
        fCtx.clearRect(0, 0, fowCanvas.width, fowCanvas.height);

        fowPaths.forEach(p => {
            if (p.type === 'hide_all') {
                fCtx.globalCompositeOperation = 'source-over';
                fCtx.fillStyle = PLAYER_FOG_COLOR;
                fCtx.fillRect(0, 0, fowCanvas.width, fowCanvas.height);
            } else if (p.type === 'path') {
                fCtx.globalCompositeOperation = p.mode === 'reveal' ? 'destination-out' : 'source-over';
                fCtx.strokeStyle = p.mode === 'reveal' ? 'rgba(0,0,0,1)' : PLAYER_FOG_COLOR;
                fCtx.lineWidth = p.width;
                fCtx.lineCap = 'round';
                fCtx.lineJoin = 'round';
                fCtx.beginPath();
                if (p.points.length > 0) {
                    fCtx.moveTo(p.points[0].x, p.points[0].y);
                    for(let i=1; i<p.points.length; i++) fCtx.lineTo(p.points[i].x, p.points[i].y);
                    fCtx.stroke();
                }
            }
        });
    }

    function render() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#0a0a0c';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.save();
        ctx.translate(view.x, view.y);
        ctx.scale(view.scale, view.scale);

        if (mapImage) {
            ctx.drawImage(mapImage, 0, 0, mapNaturalWidth, mapNaturalHeight);
        }

        if (gridVisible && mapImage) {
            drawGrid();
        }

        drawings.forEach(drawLine);

        drawMeasurements();

        if (mapImage && fowPaths.length > 0) {
            ctx.drawImage(fowCanvas, 0, 0);
        }

        for (const charId in allTokens) {
            drawToken(allTokens[charId]);
        }
        ctx.restore();
    }

    function drawMeasurements() {
        if (measureStart && measureEnd) {
            drawRuler(measureStart, measureEnd, '#3498db');
        }
        for (let user in activeMeasurements) {
            let m = activeMeasurements[user];
            if (m.start && m.end) {
                drawRuler(m.start, m.end, m.color || '#c9a961');
            }
        }
    }

    function drawRuler(p1, p2, color) {
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = 4 / view.scale;
        ctx.lineCap = 'round';
        ctx.setLineDash([12 / view.scale, 12 / view.scale]);

        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();

        let dx = p2.x - p1.x;
        let dy = p2.y - p1.y;
        let distCells = Math.hypot(dx, dy) / gridSize;
        let distFt = Math.round(distCells * 5);

        let midX = (p1.x + p2.x) / 2;
        let midY = (p1.y + p2.y) / 2;

        ctx.setLineDash([]);
        ctx.font = `bold ${16 / view.scale}px var(--font-ui)`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        let text = `${distFt} фт.`;
        let pad = 6 / view.scale;
        let textWidth = ctx.measureText(text).width;

        ctx.fillStyle = 'rgba(20, 20, 24, 0.9)';
        ctx.beginPath();
        ctx.roundRect(midX - textWidth/2 - pad, midY - (10/view.scale) - pad, textWidth + pad*2, (20/view.scale) + pad*2, 4/view.scale);
        ctx.fill();

        ctx.fillStyle = color;
        ctx.fillText(text, midX, midY);
        ctx.restore();
    }

    function drawLine(lineData) {
        if (!lineData.points || lineData.points.length < 2) return;
        ctx.beginPath();
        ctx.strokeStyle = lineData.color;
        ctx.lineWidth = lineData.width;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';

        ctx.moveTo(lineData.points[0].x, lineData.points[0].y);
        for (let i = 1; i < lineData.points.length; i++) {
            ctx.lineTo(lineData.points[i].x, lineData.points[i].y);
        }
        ctx.stroke();
    }

    function drawGrid() {
        ctx.strokeStyle = 'rgba(201, 169, 97, 0.25)';
        ctx.lineWidth = 1 / view.scale;

        const startX = Math.floor(-view.x / view.scale / gridSize) * gridSize;
        const startY = Math.floor(-view.y / view.scale / gridSize) * gridSize;
        const endX = startX + canvas.width / view.scale + gridSize * 2;
        const endY = startY + canvas.height / view.scale + gridSize * 2;

        ctx.beginPath();
        for (let x = startX; x <= endX; x += gridSize) {
            ctx.moveTo(x, startY);
            ctx.lineTo(x, endY);
        }
        for (let y = startY; y <= endY; y += gridSize) {
            ctx.moveTo(startX, y);
            ctx.lineTo(endX, y);
        }
        ctx.stroke();
    }

    // 🆕 ИСПРАВЛЕНО: ОТРИСОВКА ТОКЕНА ДЛЯ ИГРОКА (УЧИТЫВАЕТ ПРОПСЫ БЕЗ ПОДПИСЕЙ И РАЗМЕРЫ W x H)
    function drawToken(token) {
        const id = token.token_id || token.char_id;
        const img = tokenImages[id];

        const w = token.width || token.size || 60;
        const h = token.height || token.size || 60;

        const displayName = token.char_name || token.name || '???';
        const isDying = token.is_monster && token.hp_current !== undefined && token.hp_current !== null && token.hp_current <= 0;

        ctx.save();
        ctx.shadowColor = isDying ? 'rgba(255, 0, 0, 0.9)' : 'rgba(0, 0, 0, 0.7)';
        ctx.shadowBlur = (isDying ? 20 : 8) / view.scale;
        ctx.shadowOffsetX = 2 / view.scale;
        ctx.shadowOffsetY = 2 / view.scale;

        if (token.is_object) {
            // Пропсы у игроков: без подписи, произвольные пропорции, без синей подсветки
            if (img) {
                ctx.drawImage(img, token.x - w / 2, token.y - h / 2, w, h);
            } else {
                ctx.fillStyle = '#3498db';
                ctx.fillRect(token.x - w / 2, token.y - h / 2, w, h);
            }
        } else {
            // Персонажи и монстры
            ctx.beginPath();
            ctx.arc(token.x, token.y, w / 2, 0, Math.PI * 2);
            ctx.closePath();

            let fillColor = '#4a6b4a';
            if (token.is_monster) fillColor = '#8b3a3a';
            if (isDying) fillColor = '#ff4444';

            if (img) {
                ctx.save(); ctx.clip();
                if (isDying) ctx.globalAlpha = 0.5;
                ctx.drawImage(img, token.x - w / 2, token.y - h / 2, w, h);
                if (isDying) {
                    ctx.globalAlpha = 1; ctx.fillStyle = 'rgba(139, 58, 58, 0.5)';
                    ctx.fillRect(token.x - w / 2, token.y - h / 2, w, h);
                }
                ctx.restore();
            } else {
                ctx.fillStyle = fillColor;
                ctx.fill();
            }

            ctx.strokeStyle = isDying ? '#ff0000' : fillColor;
            ctx.lineWidth = (isDying ? 4 : 3) / view.scale;
            ctx.beginPath(); ctx.arc(token.x, token.y, w / 2, 0, Math.PI * 2); ctx.stroke();

            ctx.font = `bold ${14 / view.scale}px Georgia`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.strokeStyle = '#0a0a0c';
            ctx.lineWidth = 4 / view.scale;
            ctx.strokeText(displayName, token.x, token.y + w / 2 + 4 / view.scale);
            ctx.fillStyle = '#e0d4b8';
            ctx.fillText(displayName, token.x, token.y + w / 2 + 4 / view.scale);
        }
        ctx.restore();
    }

    function screenToMap(sx, sy) {
        const rect = canvas.getBoundingClientRect();
        return {
            x: (sx - rect.left - view.x) / view.scale,
            y: (sy - rect.top - view.y) / view.scale
        };
    }

    // 🆕 ИСПРАВЛЕНО: Проверка клика с учетом прямоугольных размеров токена
    function getTokenAt(mapX, mapY) {
        for (const charId in allTokens) {
            const t = allTokens[charId];
            const w = t.width || t.size || 60;
            const h = t.height || t.size || 60;
            if (mapX >= t.x - w/2 && mapX <= t.x + w/2 && mapY >= t.y - h/2 && mapY <= t.y + h/2) {
                return t;
            }
        }
        return null;
    }

    function loadMapFromData(imageData, width, height) {
        if (!imageData) return;
        const img = new Image();
        img.onload = () => {
            mapImage = img;
            mapNaturalWidth = width || img.naturalWidth;
            mapNaturalHeight = height || img.naturalHeight;

            fowCanvas.width = mapNaturalWidth;
            fowCanvas.height = mapNaturalHeight;
            renderFowCanvas();

            document.getElementById('vtt-placeholder').style.display = 'none';
            fitMap();
        };
        img.src = imageData;
    }

    function fitMap() {
        if (!mapImage) return;
        const padding = 40;
        const scaleX = (canvas.width - padding * 2) / mapNaturalWidth;
        const scaleY = (canvas.height - padding * 2) / mapNaturalHeight;
        view.scale = Math.min(scaleX, scaleY, 1);
        view.x = (canvas.width - mapNaturalWidth * view.scale) / 2;
        view.y = (canvas.height - mapNaturalHeight * view.scale) / 2;
        render();
    }

    function zoomIn() { zoomAt(canvas.width/2, canvas.height/2, 1.25); }
    function zoomOut() { zoomAt(canvas.width/2, canvas.height/2, 0.8); }

    function zoomAt(cx, cy, factor) {
        const newScale = Math.max(0.05, Math.min(10, view.scale * factor));
        const scaleChange = newScale / view.scale;
        view.x = cx - (cx - view.x) * scaleChange;
        view.y = cy - (cy - view.y) * scaleChange;
        view.scale = newScale;
        render();
    }

    function toggleGrid() {
        gridVisible = !gridVisible;
        document.getElementById('btnGrid').classList.toggle('active', gridVisible);
        render();
    }

    function sendMeasurement() {
        if (roomWs && roomWs.readyState === WebSocket.OPEN) {
            roomWs.send(JSON.stringify({ type: 'measure', start: measureStart, end: measureEnd, color: '#3498db' }));
        }
    }

    canvas.addEventListener('contextmenu', (e) => {
        e.preventDefault();
    });

    canvas.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return; // Строго ЛКМ
        const mapPos = screenToMap(e.clientX, e.clientY);

        if (currentMode === 'ruler') {
            measureStart = mapPos; measureEnd = mapPos; sendMeasurement(); return;
        }

        const token = getTokenAt(mapPos.x, mapPos.y);
        // Игрок можеть двигать ТОЛЬКО свой токен
        if (token && String(token.char_id) === myCharId) {
            draggingToken = token;
            dragOffset.x = mapPos.x - token.x;
            dragOffset.y = mapPos.y - token.y;
            canvas.classList.add('panning');
            e.stopPropagation();
        } else {
            isPanning = true;
            panStart = { x: e.clientX, y: e.clientY };
            viewStart = { x: view.x, y: view.y };
            canvas.classList.add('panning');
        }
    });

    window.addEventListener('mousemove', (e) => {
        if (currentMode === 'ruler' && measureStart) {
            measureEnd = screenToMap(e.clientX, e.clientY);
            sendMeasurement(); render(); return;
        }

        if (draggingToken) {
            const mapPos = screenToMap(e.clientX, e.clientY);
            draggingToken.x = mapPos.x - dragOffset.x;
            draggingToken.y = mapPos.y - dragOffset.y;
            render();
            return;
        }
        if (!isPanning) return;
        view.x = viewStart.x + (e.clientX - panStart.x);
        view.y = viewStart.y + (e.clientY - panStart.y);
        render();
    });

    window.addEventListener('mouseup', (e) => {
        if (currentMode === 'ruler' && measureStart) {
            measureStart = null; measureEnd = null; sendMeasurement(); render(); return;
        }

        if (draggingToken) {
            sendTokenUpdate('move', draggingToken);
            draggingToken = null;
        }
        isPanning = false;
        canvas.classList.remove('panning');
    });

    canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        zoomAt(e.clientX - rect.left, e.clientY - rect.top, e.deltaY < 0 ? 1.15 : 0.87);
    }, { passive: false });

    function refreshPlayersTab() {
        fetch(window.location.href)
            .then(res => res.text())
            .then(html => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');

                const newPlayers = doc.getElementById('tab-players');
                if (newPlayers) {
                    document.getElementById('tab-players').innerHTML = newPlayers.innerHTML;
                }

                const newMeta = doc.querySelector('.room-meta');
                const oldMeta = document.querySelector('.room-meta');
                if (newMeta && oldMeta) {
                    oldMeta.innerHTML = newMeta.innerHTML;
                }
            })
            .catch(err => console.error('Ошибка синхронизации списка игроков:', err));
    }

    function addSystemChatMessage(emoji, name, message) {
        const log = document.getElementById('chatLog');
        const entry = document.createElement('div');
        entry.style.cssText = 'text-align: center; color: var(--text-secondary); font-size: 0.85rem; margin: 0.8rem 0; opacity: 0.6;';
        entry.appendChild(document.createTextNode(emoji + ' '));
        const nameEl = document.createElement('strong');
        nameEl.textContent = name;
        entry.appendChild(nameEl);
        entry.appendChild(document.createTextNode(' ' + message));
        log.appendChild(entry);
        scrollToBottomLog();
    }

    setInterval(() => fetch('/player/heartbeat', { method: 'POST' }).catch(() => {}), 30000);

