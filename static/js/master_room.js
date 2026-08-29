const myUsername = window.userData.username;
const myCharName = 'Мастер подземелий';

// --- Управление панелью вкладок ---
const slidePanel = document.getElementById('slidePanel');
const panelTitle = document.getElementById('panelTitle');
const tabBtns = document.querySelectorAll('.icon-tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

const titles = {
    'players': 'Участники',
    'combat': 'Трекер боя',
    'scenes': 'Сцены',
    'dice': 'Броски кубов',
    'history': 'История наград',
    'monsters': 'Бестиарий',
    'props': 'Пропсы',
    'rewards': 'Награды' // 🆕
};

tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const tabId = btn.getAttribute('data-tab');
        if (btn.classList.contains('active')) { closePanel(); return; }
        tabBtns.forEach(b => b.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        const content = document.getElementById('tab-' + tabId);
        if (content) content.classList.add('active');
        panelTitle.textContent = titles[tabId] || 'Панель';
        slidePanel.classList.add('open');
    });
});

function closePanel() {
    slidePanel.classList.remove('open');
    tabBtns.forEach(b => b.classList.remove('active'));
}

function toggleRightPanel() {
    const rightPanel = document.getElementById('rightPanel');
    const chatToggleBtn = document.getElementById('chatToggleBtn');
    rightPanel.classList.toggle('collapsed');
    chatToggleBtn.textContent = rightPanel.classList.contains('collapsed') ? '◀' : '▶';
}

// --- Lazy Loading History ---
let chatOffset = window.roomData.chatHistoryLength;
let isLoadingChat = false;
let allChatLoaded = false;
const chatLog = document.getElementById('chatLog');

window.addEventListener('DOMContentLoaded', () => {
    chatLog.scrollTop = chatLog.scrollHeight;
    loadScenes();
});

chatLog.addEventListener('scroll', async () => {
    if (chatLog.scrollTop <= 1 && !isLoadingChat && !allChatLoaded) await loadOlderMessages();
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
    } catch (err) { console.error("Ошибка загрузки истории:", err); }
    finally { isLoadingChat = false; if (loader) loader.style.display = 'none'; }
}

function escapeHtmlText(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, function(m) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]; });
}

function createMessageElement(data) {
    const isSelf = data.username === myUsername;
    const author = data.char_name || data.username || 'Неизвестно';
    const entry = document.createElement('div');

    if (data.type === 'chat_message') {
        entry.className = 'chat-msg' + (isSelf ? ' self' : '');
        entry.innerHTML = `<div class="author">${data.is_master ? '👑' : '🎭'} ${escapeHtmlText(author)}</div><div class="text">${escapeHtmlText(data.text)}</div>`;
        return entry;
    } else if (data.type === 'dice_roll') {
        entry.className = 'dice-entry' + (data.is_crit ? ' crit' : '') + (data.is_fail ? ' fail' : '');
        const name = data.name || `d${data.sides}`;
        let modifierStr = '';
        if (data.modifier !== 0) modifierStr = data.modifier > 0 ? ` +${data.modifier}` : ` ${data.modifier}`;
        let resultTags = '';
        if (data.is_crit) resultTags += ' 🎯 КРИТ!';
        if (data.is_fail) resultTags += ' 💀 ПРОВАЛ!';
        if (data.is_hidden) resultTags += ' 👁️ (Скрыто)';

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
let isMaster = true;
let mapImage = null;
let mapNaturalWidth = 0;
let mapNaturalHeight = 0;

function connectWs() {
    roomWs = new WebSocket(`/ws/room/${window.roomData.id}`);
    roomWs.onopen = () => { roomWs.send(JSON.stringify({ username: myUsername, char_name: myCharName })); };
    roomWs.onmessage = (event) => { handleWsMessage(JSON.parse(event.data)); };
    roomWs.onclose = () => { setTimeout(connectWs, 3000); };
}
connectWs();

function handleWsMessage(data) {
    switch (data.type) {
        case 'init': isMaster = data.is_master; break;
        case 'map_update': loadMapFromData(data.image, data.width, data.height); break;
        case 'map_clear': mapImage = null; drawings = []; fowPaths = []; renderFowCanvas(); document.getElementById('vtt-placeholder').style.display = 'flex'; render(); break;
        case 'grid_size_update':
            gridSize = data.grid_size;
            if(document.getElementById('gridSizeSlider')) { document.getElementById('gridSizeSlider').value = gridSize; document.getElementById('gridSizeLabel').textContent = gridSize; }
            render(); break;
        case 'tokens_clear':
            allTokens = {};
            combatants = [];
            renderCombatList();
            render();
            break;
        case 'draw_init': drawings = data.drawings || []; render(); break;
        case 'draw_line': drawings.push(data.line); render(); break;
        case 'draw_clear': drawings = []; render(); break;
        case 'fow_sync':
            fowPaths = data.fow_paths || [];
            renderFowCanvas();
            render();
            break;
        case 'measure':
            if (data.username !== myUsername) {
                activeMeasurements[data.username] = { start: data.start, end: data.end, color: data.color };
                render();
            }
            break;

        case 'dice_roll': addDiceEntryFromServer(data); break;
        case 'chat_message': addChatMessageFromServer(data); break;
        case 'combat_update': combatants = data.combatants; renderCombatList(); break;
        case 'tokens_init': allTokens = {}; data.tokens.forEach(t => { const id = t.token_id || t.char_id; allTokens[id] = t; preloadTokenImage(t); }); render(); break;
        case 'token_add': const addId = data.token.token_id || data.token.char_id; allTokens[addId] = data.token; preloadTokenImage(data.token); render(); break;
        case 'token_remove': const removeId = data.token_id || data.char_id; delete allTokens[removeId]; render(); break;
        case 'token_move': const moveId = data.token.token_id || data.token.char_id; if (allTokens[moveId]) { allTokens[moveId].x = data.token.x; allTokens[moveId].y = data.token.y; allTokens[moveId].width = data.token.width; allTokens[moveId].height = data.token.height; render(); } break;
        case 'hp_update':
            const input = document.getElementById(`master-hp-${data.char_id}`);
            if (input) {
                input.value = data.hp_current;
                input.style.backgroundColor = 'rgba(201, 169, 97, 0.3)';
                setTimeout(() => { input.style.backgroundColor = 'var(--bg-primary)'; }, 500);
            }
            break;
        case 'player_join': if (data.username !== myUsername) { addSystemChatMessage(`🟢 <strong>${data.char_name || data.username}</strong> присоединился к игре.`); refreshPlayersTab(); } break;
        case 'player_leave': addSystemChatMessage(`🔴 <strong>${data.char_name || data.username}</strong> покинул игру.`); refreshPlayersTab(); break;
    }
}

// ==================== ЧАТ И БРОСКИ ====================
function sendDiceRoll(name, roll, sides, modifier, total, isCrit, isFail, isHidden = false) {
    if (roomWs && roomWs.readyState === WebSocket.OPEN) { roomWs.send(JSON.stringify({ type: 'dice_roll', name, roll, sides, modifier, total, is_crit: isCrit, is_fail: isFail, is_hidden: isHidden })); }
}
function rollDice(sides) {
    const nameInput = document.getElementById('check-name');
    const name = nameInput?.value || `d${sides}`;
    const roll = Math.floor(Math.random() * sides) + 1;
    const isHidden = document.getElementById('hiddenRollCheck')?.checked || false;
    sendDiceRoll(name, roll, sides, 0, roll, sides === 20 && roll === 20, sides === 20 && roll === 1, isHidden);
    if (nameInput) nameInput.value = '';
}
function rollCheck() { rollDice(20); }
function sendChatMessage() {
    const input = document.getElementById('chatInput');
    const text = input.value.trim();
    if (!text) return;
    if (roomWs && roomWs.readyState === WebSocket.OPEN) { roomWs.send(JSON.stringify({ type: 'chat_message', text: text })); input.value = ''; }
}
function scrollToBottomLog() { chatLog.scrollTop = chatLog.scrollHeight; }
function addDiceEntryFromServer(data) { const entry = createMessageElement(data); if (entry) { chatLog.appendChild(entry); chatOffset++; scrollToBottomLog(); document.getElementById('chatStart')?.remove(); } }
function addChatMessageFromServer(data) { const entry = createMessageElement(data); if (entry) { chatLog.appendChild(entry); chatOffset++; scrollToBottomLog(); document.getElementById('chatStart')?.remove(); } }

// ==================== VTT КАРТА И ТОКЕНЫ ====================
let tokenImages = {};
function preloadTokenImage(token) {
    const id = token.token_id || token.char_id;
    if (!token.image || tokenImages[id]) return;
    const img = new Image(); img.onload = () => { tokenImages[id] = img; render(); }; img.src = token.image;
}

const canvas = document.getElementById('vtt-canvas');
const ctx = canvas.getContext('2d');
const container = document.getElementById('vttContainer');

let view = { x: 0, y: 0, scale: 1 };
let gridVisible = true;
let gridSize = 50;
let isPanning = false;
let panStart = { x: 0, y: 0 };
let viewStart = { x: 0, y: 0 };
let draggingToken = null;
let dragOffset = { x: 0, y: 0 };
let allTokens = {};

// ПЕРЕМЕННЫЕ РИСОВАНИЯ
let currentMode = 'move';
let brushColor = '#e0d4b8';
let brushSize = 4;
let isDrawing = false;
let currentPath = [];
let drawings = [];

// ТУМАН ВОЙНЫ
let fowCanvas = document.createElement('canvas');
let fCtx = fowCanvas.getContext('2d');
let fowPaths = [];
let fogBrushSize = 60;
let fowBrushMode = 'reveal';
const MASTER_FOG_COLOR = 'rgba(20, 20, 24, 0.75)';

// ЛИНЕЙКА
let activeMeasurements = {};
let measureStart = null;
let measureEnd = null;

function resizeCanvas() {
    if (canvas.width === container.clientWidth && canvas.height === container.clientHeight) return;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    render();
}
const vttObserver = new ResizeObserver(() => { requestAnimationFrame(resizeCanvas); });
vttObserver.observe(container);

function toggleToolbar() {
    const content = document.getElementById('toolbarContent');
    const chevron = document.getElementById('toolbarChevron');
    if (content.style.display === 'none') {
        content.style.display = 'flex';
        chevron.style.transform = 'rotate(0deg)';
    } else {
        content.style.display = 'none';
        chevron.style.transform = 'rotate(180deg)';
    }
}

function setTool(mode) {
    currentMode = mode;
    document.getElementById('toolMove').classList.toggle('active', mode === 'move');
    document.getElementById('toolRuler').classList.toggle('active', mode === 'ruler');
    document.getElementById('toolDraw').classList.toggle('active', mode === 'draw');
    document.getElementById('toolFow').classList.toggle('active', mode === 'fow');

    document.getElementById('drawSettings').style.display = mode === 'draw' ? 'flex' : 'none';
    document.getElementById('fowSettings').style.display = mode === 'fow' ? 'flex' : 'none';

    canvas.className = `mode-${mode}`;
}

function setBrushColor(color, btn) { brushColor = color; document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); }
function setBrushSize(size) { brushSize = parseInt(size); }
function clearDrawings() { if (!confirm("Очистить все рисунки на карте?")) return; drawings = []; render(); if (roomWs && roomWs.readyState === WebSocket.OPEN) roomWs.send(JSON.stringify({ type: 'draw_clear' })); }

// УПРАВЛЕНИЕ ТУМАНОМ
function setFowMode(mode) { fowBrushMode = mode; document.getElementById('fowModeReveal').classList.toggle('active', mode === 'reveal'); document.getElementById('fowModeHide').classList.toggle('active', mode === 'hide'); }
function fowHideAll() { if (!confirm("Залить всю карту туманом?")) return; fowPaths = [{type: 'hide_all'}]; renderFowCanvas(); render(); if (roomWs && roomWs.readyState === WebSocket.OPEN) roomWs.send(JSON.stringify({ type: 'fow_update', action: 'hide_all' })); }
function fowClearAll() { if (!confirm("Удалить весь туман с карты?")) return; fowPaths = []; renderFowCanvas(); render(); if (roomWs && roomWs.readyState === WebSocket.OPEN) roomWs.send(JSON.stringify({ type: 'fow_update', action: 'clear_all' })); }

function renderFowCanvas() {
    if (!mapImage) return;
    fCtx.clearRect(0, 0, fowCanvas.width, fowCanvas.height);
    fowPaths.forEach(p => {
        if (p.type === 'hide_all') {
            fCtx.globalCompositeOperation = 'source-over';
            fCtx.fillStyle = MASTER_FOG_COLOR;
            fCtx.fillRect(0, 0, fowCanvas.width, fowCanvas.height);
        } else if (p.type === 'path') {
            fCtx.globalCompositeOperation = p.mode === 'reveal' ? 'destination-out' : 'source-over';
            fCtx.strokeStyle = p.mode === 'reveal' ? 'rgba(0,0,0,1)' : MASTER_FOG_COLOR;
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

// 🆕 ИСПРАВЛЕНО: ОТРИСОВКА ТОКЕНОВ С УЧЕТОМ ПРОПСОВ (БЕЗ ПОДПИСЕЙ И С ПОДДЕРЖКОЙ W x H)
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
        // Предметы (пропсы): без синей подсветки, без подписи, произвольные пропорции
        if (img) {
            ctx.drawImage(img, token.x - w / 2, token.y - h / 2, w, h);
        } else {
            ctx.fillStyle = '#3498db';
            ctx.fillRect(token.x - w / 2, token.y - h / 2, w, h);
        }
    } else {
        // Персонажи и монстры: круглые токены с подписью
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

// RENDER
function render() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#0a0a0c';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.save();
    ctx.translate(view.x, view.y);
    ctx.scale(view.scale, view.scale);

    if (mapImage) { ctx.drawImage(mapImage, 0, 0, mapNaturalWidth, mapNaturalHeight); }
    if (gridVisible && mapImage) { drawGrid(); }

    drawings.forEach(drawLine);
    if (currentMode === 'draw' && currentPath.length > 0) {
        drawLine({ points: currentPath, color: brushColor, width: brushSize });
    }

    drawMeasurements();

    if (mapImage && fowPaths.length > 0) { ctx.drawImage(fowCanvas, 0, 0); }
    for (const tokenId in allTokens) { drawToken(allTokens[tokenId]); }
    ctx.restore();

    document.getElementById('zoomLevel').textContent = Math.round(view.scale * 100) + '%';
    if (mapImage) document.getElementById('mapSize').textContent = `${mapNaturalWidth}×${mapNaturalHeight}`;
}

function drawMeasurements() {
    if (measureStart && measureEnd) { drawRuler(measureStart, measureEnd, '#c9a961'); }
    for (let user in activeMeasurements) {
        let m = activeMeasurements[user];
        if (m.start && m.end) { drawRuler(m.start, m.end, m.color || '#3498db'); }
    }
}

function drawRuler(p1, p2, color) {
    ctx.save();
    ctx.strokeStyle = color; ctx.lineWidth = 4 / view.scale; ctx.lineCap = 'round'; ctx.setLineDash([12 / view.scale, 12 / view.scale]);
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    let distCells = Math.hypot(p2.x - p1.x, p2.y - p1.y) / gridSize;
    let distFt = Math.round(distCells * 5);
    let midX = (p1.x + p2.x) / 2; let midY = (p1.y + p2.y) / 2;
    ctx.setLineDash([]); ctx.font = `bold ${16 / view.scale}px var(--font-ui)`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    let text = `${distFt} фт.`; let pad = 6 / view.scale; let textWidth = ctx.measureText(text).width;
    ctx.fillStyle = 'rgba(20, 20, 24, 0.9)'; ctx.beginPath(); ctx.roundRect(midX - textWidth/2 - pad, midY - (10/view.scale) - pad, textWidth + pad*2, (20/view.scale) + pad*2, 4/view.scale); ctx.fill();
    ctx.fillStyle = color; ctx.fillText(text, midX, midY);
    ctx.restore();
}

function drawLine(lineData) {
    if (!lineData.points || lineData.points.length < 2) return;
    ctx.beginPath(); ctx.strokeStyle = lineData.color; ctx.lineWidth = lineData.width; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.moveTo(lineData.points[0].x, lineData.points[0].y);
    for (let i = 1; i < lineData.points.length; i++) { ctx.lineTo(lineData.points[i].x, lineData.points[i].y); }
    ctx.stroke();
}

function drawGrid() {
    ctx.strokeStyle = 'rgba(201, 169, 97, 0.25)'; ctx.lineWidth = 1 / view.scale;
    const startX = Math.floor(-view.x / view.scale / gridSize) * gridSize; const startY = Math.floor(-view.y / view.scale / gridSize) * gridSize;
    const endX = startX + canvas.width / view.scale + gridSize * 2; const endY = startY + canvas.height / view.scale + gridSize * 2;
    ctx.beginPath();
    for (let x = startX; x <= endX; x += gridSize) { ctx.moveTo(x, startY); ctx.lineTo(x, endY); }
    for (let y = startY; y <= endY; y += gridSize) { ctx.moveTo(startX, y); ctx.lineTo(endX, y); }
    ctx.stroke();
}

function loadMapFromData(imageData, width, height) {
    if (!imageData) return; const img = new Image();
    img.onload = () => { mapImage = img; mapNaturalWidth = width || img.naturalWidth; mapNaturalHeight = height || img.naturalHeight; fowCanvas.width = mapNaturalWidth; fowCanvas.height = mapNaturalHeight; renderFowCanvas(); document.getElementById('vtt-placeholder').style.display = 'none'; fitMap(); }; img.src = imageData;
}

function changeGridSize(size) { gridSize = parseInt(size); document.getElementById('gridSizeLabel').textContent = gridSize; render(); if (roomWs && roomWs.readyState === WebSocket.OPEN && isMaster) roomWs.send(JSON.stringify({ type: 'grid_size_update', grid_size: gridSize })); }
function clearAllTokens() { if (!confirm("Удалить все токены с карты и очистить трекер боя?")) return; if (roomWs && roomWs.readyState === WebSocket.OPEN) { roomWs.send(JSON.stringify({ type: 'tokens_clear' })); } }
function clearMap() { if(!confirm("Удалить карту для всех игроков?")) return; if (roomWs && roomWs.readyState === WebSocket.OPEN) { roomWs.send(JSON.stringify({ type: 'map_clear' })); roomWs.send(JSON.stringify({ type: 'tokens_clear' })); } }

async function activateScene(sceneId) { try { const response = await fetch(`/api/room/${window.roomData.id}/scene/${sceneId}/activate`, { method: 'POST' }); const data = await response.json(); if (data.status === 'ok') { if (roomWs && roomWs.readyState === WebSocket.OPEN) { roomWs.send(JSON.stringify({ type: 'tokens_clear' })); } loadScenes(); } } catch (e) { console.error(e); } }
function fitMap() { if (!mapImage) return; const padding = 40; const scaleX = (canvas.width - padding * 2) / mapNaturalWidth; const scaleY = (canvas.height - padding * 2) / mapNaturalHeight; view.scale = Math.min(scaleX, scaleY, 1); view.x = (canvas.width - mapNaturalWidth * view.scale) / 2; view.y = (canvas.height - mapNaturalHeight * view.scale) / 2; render(); }
function zoomIn() { zoomAt(canvas.width/2, canvas.height/2, 1.25); } function zoomOut() { zoomAt(canvas.width/2, canvas.height/2, 0.8); }
function zoomAt(cx, cy, factor) { const newScale = Math.max(0.05, Math.min(10, view.scale * factor)); const scaleChange = newScale / view.scale; view.x = cx - (cx - view.x) * scaleChange; view.y = cy - (cy - view.y) * scaleChange; view.scale = newScale; render(); }
function toggleGrid() { gridVisible = !gridVisible; document.getElementById('gridToggleBtn').classList.toggle('active', gridVisible); render(); }
function screenToMap(sx, sy) { const rect = canvas.getBoundingClientRect(); return { x: (sx - rect.left - view.x) / view.scale, y: (sy - rect.top - view.y) / view.scale }; }

// 🆕 ИСПРАВЛЕНО: Проверка клика по токену с учетом прямоугольных размеров (width x height)
function getTokenAt(mapX, mapY) {
    for (const tokenId in allTokens) {
        const t = allTokens[tokenId];
        const w = t.width || t.size || 60;
        const h = t.height || t.size || 60;
        if (mapX >= t.x - w/2 && mapX <= t.x + w/2 && mapY >= t.y - h/2 && mapY <= t.y + h/2) {
            return t;
        }
    }
    return null;
}

function sendMeasurement() { if (roomWs && roomWs.readyState === WebSocket.OPEN) { roomWs.send(JSON.stringify({ type: 'measure', start: measureStart, end: measureEnd, color: '#c9a961' })); } }

// 🆕 НОВОЕ: Логика контекстного меню по ПКМ
let contextMenuToken = null;

canvas.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    const mapPos = screenToMap(e.clientX, e.clientY);
    const token = getTokenAt(mapPos.x, mapPos.y);

    const menu = document.getElementById('vttContextMenu');
    if (token) {
        contextMenuToken = token;
        menu.style.display = 'block';
        menu.style.left = e.clientX + 'px';
        menu.style.top = e.clientY + 'px';
    } else {
        menu.style.display = 'none';
        contextMenuToken = null;
    }
});

window.addEventListener('click', () => {
    document.getElementById('vttContextMenu').style.display = 'none';
});

function contextMenuAction(action) {
    if (!contextMenuToken) return;
    const tokenId = contextMenuToken.token_id || contextMenuToken.char_id;

    if (action === 'delete') {
        removeTokenFromMap(tokenId);
    } else if (action === 'scale_up' || action === 'scale_down') {
        let factor = action === 'scale_up' ? 1.2 : 0.8;
        contextMenuToken.width = (contextMenuToken.width || contextMenuToken.size || 60) * factor;
        contextMenuToken.height = (contextMenuToken.height || contextMenuToken.size || 60) * factor;

        render();

        if (roomWs && roomWs.readyState === WebSocket.OPEN) {
            roomWs.send(JSON.stringify({
                type: 'token_update',
                action: 'move',
                token: contextMenuToken
            }));
        }
    }
    document.getElementById('vttContextMenu').style.display = 'none';
}

canvas.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    const mapPos = screenToMap(e.clientX, e.clientY);

    if (currentMode === 'ruler') { measureStart = mapPos; measureEnd = mapPos; sendMeasurement(); return; }
    if (currentMode === 'draw' || currentMode === 'fow') { isDrawing = true; currentPath = [mapPos]; return; }

    const token = getTokenAt(mapPos.x, mapPos.y);
    if (token) { draggingToken = token; dragOffset.x = mapPos.x - token.x; dragOffset.y = mapPos.y - token.y; canvas.classList.add('panning'); e.stopPropagation(); }
    else { isPanning = true; panStart = { x: e.clientX, y: e.clientY }; viewStart = { x: view.x, y: view.y }; canvas.classList.add('panning'); }
});

window.addEventListener('mousemove', (e) => {
    if (currentMode === 'ruler' && measureStart) { measureEnd = screenToMap(e.clientX, e.clientY); sendMeasurement(); render(); return; }
    if (isDrawing) {
        const mapPos = screenToMap(e.clientX, e.clientY); const last = currentPath[currentPath.length - 1];
        if ((mapPos.x - last.x)**2 + (mapPos.y - last.y)**2 > 4) {
            currentPath.push(mapPos);
            if (currentMode === 'fow') { fCtx.globalCompositeOperation = fowBrushMode === 'reveal' ? 'destination-out' : 'source-over'; fCtx.strokeStyle = fowBrushMode === 'reveal' ? 'rgba(0,0,0,1)' : MASTER_FOG_COLOR; fCtx.lineWidth = fogBrushSize; fCtx.lineCap = 'round'; fCtx.lineJoin = 'round'; fCtx.beginPath(); fCtx.moveTo(last.x, last.y); fCtx.lineTo(mapPos.x, mapPos.y); fCtx.stroke(); }
            render();
        } return;
    }
    if (draggingToken) { const mapPos = screenToMap(e.clientX, e.clientY); draggingToken.x = mapPos.x - dragOffset.x; draggingToken.y = mapPos.y - dragOffset.y; render(); return; }
    if (!isPanning) return; view.x = viewStart.x + (e.clientX - panStart.x); view.y = viewStart.y + (e.clientY - panStart.y); render();
});

window.addEventListener('mouseup', (e) => {
    if (currentMode === 'ruler' && measureStart) { measureStart = null; measureEnd = null; sendMeasurement(); render(); return; }
    if (isDrawing) {
        isDrawing = false;
        if (currentPath.length > 1) {
            if (currentMode === 'draw') { const finalLine = { points: currentPath, color: brushColor, width: brushSize }; drawings.push(finalLine); if (roomWs && roomWs.readyState === WebSocket.OPEN) { roomWs.send(JSON.stringify({ type: 'draw_line', line: finalLine })); } }
            else if (currentMode === 'fow') { const finalPath = { type: 'path', mode: fowBrushMode, points: currentPath, width: fogBrushSize }; fowPaths.push(finalPath); if (roomWs && roomWs.readyState === WebSocket.OPEN) { roomWs.send(JSON.stringify({ type: 'fow_update', action: 'add_path', path: finalPath })); } }
        }
        currentPath = []; render(); return;
    }
    if (draggingToken) { const tokenId = draggingToken.token_id || draggingToken.char_id; if (roomWs && roomWs.readyState === WebSocket.OPEN) roomWs.send(JSON.stringify({ type: 'token_update', action: 'move', token: draggingToken })); draggingToken = null; }
    isPanning = false; canvas.classList.remove('panning');
});

canvas.addEventListener('wheel', (e) => { e.preventDefault(); const rect = canvas.getBoundingClientRect(); zoomAt(e.clientX - rect.left, e.clientY - rect.top, e.deltaY < 0 ? 1.15 : 0.87); }, { passive: false });

function adjustMasterHp(charId, username, amount) { const input = document.getElementById(`master-hp-${charId}`); let newVal = Math.max(0, parseInt(input.value || 0) + amount); input.value = newVal; saveMasterHp(charId, username, newVal); }
function saveMasterHp(charId, username, current) { const formData = new FormData(); formData.append('username', username); formData.append('current_hp', current); formData.append('temp_hp', 0); formData.append('room_id', window.roomData.id); fetch(`/char/${charId}/hp`, { method: 'POST', body: formData }).catch(err => console.error('Ошибка сохранения HP:', err)); if (roomWs && roomWs.readyState === WebSocket.OPEN) { roomWs.send(JSON.stringify({ type: 'combatant_hp_update', token_id: String(charId), hp_current: parseInt(current) })); } }

function addCustomToken() {
    const name = prompt("Введите название объекта:", "Маркер");
    if (!name) return;
    addPropToMap(name, null, 50);
}

// 🆕 ИСПРАВЛЕНО: Автоматическое определение пропорций изображения (ширина/высота) для пропсов
function addPropToMap(name, imgUrl, defaultSize) {
    const mapX = (-view.x + canvas.width / 2) / view.scale;
    const mapY = (-view.y + canvas.height / 2) / view.scale;
    const tokenId = 'object_' + Date.now() + Math.floor(Math.random() * 1000);
    const baseSize = parseInt(defaultSize) || 50;

    const token = {
        token_id: tokenId,
        char_id: tokenId,
        name: name,
        char_name: name,
        x: mapX,
        y: mapY,
        width: baseSize,
        height: baseSize,
        image: imgUrl || null,
        is_object: true
    };

    if (imgUrl) {
        const tempImg = new Image();
        tempImg.onload = () => {
            const ratio = tempImg.naturalWidth / tempImg.naturalHeight;
            if (ratio > 1) {
                token.width = baseSize * ratio;
            } else {
                token.height = baseSize / ratio;
            }
            allTokens[tokenId] = token;
            preloadTokenImage(token);
            render();
            sendTokenAdd(token);
        };
        tempImg.src = imgUrl;
    } else {
        allTokens[tokenId] = token;
        render();
        sendTokenAdd(token);
    }
}

function sendTokenAdd(token) {
    if (roomWs && roomWs.readyState === WebSocket.OPEN) {
        roomWs.send(JSON.stringify({ type: 'token_update', action: 'add', token: token }));
    }
}

async function uploadNewProp(inputElement) {
    const file = inputElement.files[0];
    if (!file) return;

    const nameInput = document.getElementById('newPropName');
    const catInput = document.getElementById('newPropCategory');
    const name = nameInput.value.trim() || 'Новый предмет';
    const category = catInput.value || 'Разное';

    const btn = inputElement.nextElementSibling;
    const originalText = btn.innerHTML;
    btn.innerHTML = '⏳ Обработка...';
    btn.disabled = true;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    formData.append('category', category);
    formData.append('default_size', 50);

    try {
        const response = await fetch(`/api/props/upload`, { method: 'POST', body: formData });
        const data = await response.json();
        if (data.status === 'ok') {
            window.location.reload();
        } else {
            alert('Ошибка: ' + data.message);
        }
    } catch (e) {
        console.error(e);
        alert('Ошибка при загрузке файла');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
        inputElement.value = '';
    }
}

function addMonsterToMap(name, img, hp, ac) {
    const mapX = (-view.x + canvas.width / 2) / view.scale;
    const mapY = (-view.y + canvas.height / 2) / view.scale;
    const tokenId = 'monster_' + Date.now() + Math.floor(Math.random() * 1000);

    const token = {
        token_id: tokenId, char_id: tokenId,
        name: name, char_name: name,
        hp_current: parseInt(hp) || 0, hp_max: parseInt(hp) || 0, ac: ac,
        x: mapX, y: mapY, size: 60, image: img,
        is_monster: true
    };

    allTokens[tokenId] = token;
    combatants.push({
        token_id: tokenId, char_id: tokenId, name: name,
        hp_current: token.hp_current, hp_max: token.hp_max, ac: ac,
        initiative: 0, is_monster: true
    });

    if (img) preloadTokenImage(token);
    renderCombatList();
    render();

    if (roomWs && roomWs.readyState === WebSocket.OPEN) {
        roomWs.send(JSON.stringify({ type: 'token_update', action: 'add', token: token }));
        roomWs.send(JSON.stringify({ type: 'combat_update', combatants: combatants }));
    }
}

function removeTokenFromMap(tokenId) {
    delete allTokens[tokenId];
    combatants = combatants.filter(c => c.token_id !== tokenId && c.char_id !== tokenId);

    renderCombatList();
    render();

    if (roomWs && roomWs.readyState === WebSocket.OPEN) {
        roomWs.send(JSON.stringify({ type: 'token_update', action: 'remove', token: { token_id: tokenId, char_id: tokenId } }));
        roomWs.send(JSON.stringify({ type: 'combat_update', combatants: combatants }));
    }
}

function removeMonsterFromMap(tokenId) { removeTokenFromMap(tokenId); }

function adjustMonsterHp(tokenId, delta) { const combatant = combatants.find(c => String(c.token_id) === String(tokenId) || String(c.char_id) === String(tokenId)); if (!combatant) return; let newHp = Math.max(0, Math.min((combatant.hp_current || 0) + delta, combatant.hp_max || 9999)); combatant.hp_current = newHp; renderCombatList(); if (roomWs && roomWs.readyState === WebSocket.OPEN) { roomWs.send(JSON.stringify({ type: 'combatant_hp_update', token_id: String(tokenId), hp_current: newHp })); } if (!combatant.is_monster) { const formData = new FormData(); formData.append('current_hp', newHp); formData.append('temp_hp', 0); formData.append('room_id', window.roomData.id); fetch(`/char/${tokenId}/hp`, { method: 'POST', body: formData }).catch(err => console.error(err)); } if (newHp <= 0 && combatant.is_monster) { const n = document.createElement('div'); n.innerHTML = `💀 <strong>${combatant.name}</strong> повержен!`; n.style.cssText = `position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:linear-gradient(145deg,rgba(139,58,58,0.95),rgba(80,20,20,0.95)); color:#e0d4b8; padding:1.5rem 2.5rem; border-radius:12px; border:2px solid #c9a961; z-index:10000; font-family:'Georgia',serif; font-size:1.3rem; text-align:center; transition:all 0.4s ease; pointer-events:none;`; document.body.appendChild(n); setTimeout(() => { n.style.opacity = '0'; setTimeout(() => n.remove(), 400); }, 3000); roomWs.send(JSON.stringify({ type: 'token_update', action: 'remove', token: { token_id: tokenId, char_id: tokenId } })); } }

function renderCombatList() { const container = document.getElementById('combat-list'); if (!container) return; if (!combatants || combatants.length === 0) { container.innerHTML = '<div class="empty-state">Нет участников боя</div>'; return; } combatants.sort((a, b) => b.initiative - a.initiative); let html = ''; combatants.forEach(c => { const hpCurrent = (c.hp_current !== undefined && c.hp_current !== null) ? c.hp_current : 0; const hpMax = (c.hp_max !== undefined && c.hp_max !== null) ? c.hp_max : '?'; const borderColor = c.is_monster ? 'var(--accent-red)' : 'var(--accent-gold)'; html += `<div class="player-card" style="background: var(--bg-secondary); border: 2px solid ${borderColor}; border-radius: 8px; padding: 0.8rem; margin-bottom: 0.8rem;"><div style="text-align: center; font-family: var(--font-main); font-size: 1.1rem; font-weight: 700; color: var(--accent-gold); margin-bottom: 0.6rem; display: flex; justify-content: space-between; align-items: center;"><span>${c.name}</span><button class="vtt-btn danger" style="padding: 0.2rem 0.5rem; font-size: 0.7rem;" onclick="removeMonsterFromMap('${c.token_id}')">✕</button></div><div style="display: flex; justify-content: space-around; margin-bottom: 0.6rem;"><div style="text-align: center;"><div style="font-size: 0.7rem; color: var(--text-secondary);">КД</div><div style="font-size: 1rem; font-weight: bold; color: var(--accent-gold);">${c.ac ? String(c.ac).split(' ')[0] : '?'}</div></div><div style="text-align: center;"><div style="font-size: 0.7rem; color: var(--text-secondary);">Хиты</div><div style="font-size: 1rem; font-weight: bold; color: var(--accent-green);">${hpCurrent}/${hpMax}</div></div><div style="text-align: center;"><div style="font-size: 0.7rem; color: var(--text-secondary);">Иниц</div><div style="font-size: 1rem; font-weight: bold; color: var(--accent-red);">${c.initiative}</div></div></div><div style="display: flex; justify-content: center; gap: 0.4rem;"><button class="hp-btn-sm damage" onclick="adjustMonsterHp('${c.token_id}', -5)">-5</button><button class="hp-btn-sm damage" onclick="adjustMonsterHp('${c.token_id}', -1)">-1</button><button class="hp-btn-sm heal" onclick="adjustMonsterHp('${c.token_id}', 1)">+1</button><button class="hp-btn-sm heal" onclick="adjustMonsterHp('${c.token_id}', 5)">+5</button></div></div>`; }); container.innerHTML = html; }

function showMonsterDetails(mData) { const modal = document.getElementById('monsterModal'); if (!modal) return; document.getElementById('monsterModalHeader').innerHTML = `${mData.token_image ? `<img src="${mData.token_image}" class="monster-modal-avatar">` : `<div class="monster-modal-avatar-placeholder">👹</div>`} <div style="flex:1"><h2 class="monster-modal-title">${escapeHtmlText(mData.name)}</h2>${mData.challenge_rating ? `<div class="monster-modal-cr">CR: ${mData.challenge_rating}</div>` : ''}</div>`; const sGrid = document.getElementById('monsterModalStats'); sGrid.innerHTML = ''; ['STR','DEX','CON','INT','WIS','CHA'].forEach(s => { let v = '?'; if(mData.stats && mData.stats[s]) { v = typeof mData.stats[s] === 'object' ? (mData.stats[s].score || '?') : mData.stats[s]; } sGrid.innerHTML += `<div class="monster-modal-stat"><span class="monster-modal-stat-label">${s}</span><span class="monster-modal-stat-value">${v}</span></div>`; }); document.getElementById('monsterModalInfo').innerHTML = `<div>🛡️ КД: ${escapeHtmlText(mData.armor_class || '?')}</div><div>❤️ Хиты: ${escapeHtmlText(mData.hit_points || '?')}</div>${mData.speed ? `<div>🏃 Скор: ${escapeHtmlText(mData.speed)}</div>` : ''}`; const tSec = document.getElementById('monsterModalTraitsSection'); if (mData.traits && mData.traits.length > 0) { document.getElementById('monsterModalTraits').innerHTML = renderModalActionList(mData.traits); tSec.style.display = 'block'; } else tSec.style.display = 'none'; const aSec = document.getElementById('monsterModalActionsSection'); if (mData.actions && mData.actions.length > 0) { document.getElementById('monsterModalActions').innerHTML = renderModalActionList(mData.actions); aSec.style.display = 'block'; } else aSec.style.display = 'none'; const lSec = document.getElementById('monsterModalLegendarySection'); if (mData.legendary_actions && mData.legendary_actions.length > 0) { document.getElementById('monsterModalLegendary').innerHTML = renderModalActionList(mData.legendary_actions); lSec.style.display = 'block'; } else lSec.style.display = 'none'; const dSec = document.getElementById('monsterModalDescSection'); if (mData.description) { document.getElementById('monsterModalDesc').innerHTML = escapeHtmlText(mData.description).replace(/\n/g, '<br>'); dSec.style.display = 'block'; } else dSec.style.display = 'none'; modal.classList.add('active'); }
function closeMonsterModal() { document.getElementById('monsterModal').classList.remove('active'); }
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeMonsterModal(); });
function refreshPlayersTab() { fetch(window.location.href).then(res => res.text()).then(html => { const doc = new DOMParser().parseFromString(html, 'text/html'); const newPlayers = doc.getElementById('tab-players'); if (newPlayers) document.getElementById('tab-players').innerHTML = newPlayers.innerHTML; const newMeta = doc.querySelector('.room-meta'); const oldMeta = document.querySelector('.room-meta'); if (newMeta && oldMeta) oldMeta.innerHTML = newMeta.innerHTML; }).catch(err => console.error(err)); }
function addSystemChatMessage(text) { const log = document.getElementById('chatLog'); const entry = document.createElement('div'); entry.style.cssText = 'text-align: center; color: var(--text-secondary); font-size: 0.85rem; margin: 0.8rem 0; opacity: 0.6;'; entry.innerHTML = text; log.appendChild(entry); scrollToBottomLog(); }
async function loadScenes() { try { const response = await fetch(`/api/room/${window.roomData.id}/scenes`); const data = await response.json(); if (data.status === 'ok') renderScenesList(data.scenes); } catch (e) { console.error(e); } }
function renderScenesList(scenes) { const container = document.getElementById('scenes-list'); if (scenes.length === 0) { container.innerHTML = '<div class="empty-state">Нет сохраненных сцен</div>'; return; } let html = ''; scenes.forEach(scene => { const isActive = scene.is_active; html += `<div style="background: var(--bg-secondary); border: 2px solid ${isActive ? 'var(--accent-gold)' : 'var(--border-color)'}; border-radius: 8px; overflow: hidden; position: relative;"><div style="height: 100px; background-image: url('${scene.background_url}'); background-size: cover; background-position: center; opacity: ${isActive ? '1' : '0.6'};"></div><div style="padding: 0.6rem; display: flex; justify-content: space-between; align-items: center;"><div style="font-family: var(--font-main); color: ${isActive ? 'var(--accent-gold)' : 'var(--text-primary)'}; font-weight: bold; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtmlText(scene.name)} ${isActive ? '<span style="font-size: 0.7rem; margin-left: 0.3rem;">(Активна)</span>' : ''}</div><div style="display: flex; gap: 0.4rem; flex-shrink: 0;">${!isActive ? `<button class="vtt-btn" style="padding: 0.2rem 0.5rem; font-size: 0.8rem;" onclick="activateScene(${scene.id})">▶</button>` : ''}<button class="vtt-btn danger" style="padding: 0.2rem 0.5rem; font-size: 0.8rem;" onclick="deleteScene(${scene.id})">🗑️</button></div></div></div>`; }); container.innerHTML = html; }
async function uploadNewScene(inputElement) { const file = inputElement.files[0]; if (!file) return; const nameInput = document.getElementById('newSceneName'); const name = nameInput.value.trim() || 'Новая сцена'; const btn = inputElement.nextElementSibling; const originalText = btn.innerHTML; btn.innerHTML = '⏳ Обработка...'; btn.disabled = true; const img = new Image(); img.onload = async () => { const formData = new FormData(); formData.append('file', file); formData.append('name', name); formData.append('width', img.naturalWidth); formData.append('height', img.naturalHeight); try { const response = await fetch(`/api/room/${window.roomData.id}/scene/upload`, { method: 'POST', body: formData }); const data = await response.json(); if (data.status === 'ok') { nameInput.value = ''; loadScenes(); } else alert('Ошибка: ' + data.message); } catch (e) { console.error(e); alert('Ошибка при загрузке файла'); } finally { btn.innerHTML = originalText; btn.disabled = false; inputElement.value = ''; } }; img.src = URL.createObjectURL(file); }
async function deleteScene(sceneId) { if (!confirm("Удалить эту сцену? Это действие нельзя отменить.")) return; try { const response = await fetch(`/api/room/${window.roomData.id}/scene/${sceneId}`, { method: 'DELETE' }); const data = await response.json(); if (data.status === 'ok') loadScenes(); } catch (e) { console.error(e); } }


async function sendReward(type) {
    const form = type === 'all' ? document.getElementById('mass-reward-form') : document.getElementById('single-reward-form');
    const formData = new FormData(form);
    const data = {};
    formData.forEach((v, k) => data[k] = v);

    const payload = {
        xp: parseInt(data.xp) || 0,
        coins: { gp: parseInt(data.gp) || 0, sp: parseInt(data.sp) || 0, cp: parseInt(data.cp) || 0, ep: 0, pp: 0 },
        target: type === 'all' ? 'all' : String(data.char_id),
        reason: ''
    };

    try {
        const resp = await fetch(`/master/room/${window.roomData.id}/reward`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await resp.json();
        if (result.status === 'ok') {
            alert('✅ Награда выдана!');
            form.reset();
        } else {
            alert('❌ Ошибка: ' + (result.error || 'неизвестно'));
        }
    } catch (e) {
        alert('❌ Ошибка сети');
    }
    return false;
}
