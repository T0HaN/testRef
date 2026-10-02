(function () {
    'use strict';
    const icons = {
        '🗺️':'map.svg','🗺':'map.svg','🧭':'map.svg','👹':'bestiary.svg','🐉':'bestiary.svg','🎭':'bestiary.svg',
        '📦':'props.svg','🎒':'props.svg','🧰':'props.svg','🧩':'props.svg','🛠':'props.svg','⚒️':'props.svg',
        '🗑️':'trash.svg','🗑':'trash.svg','☁️':'fog.svg','☁':'fog.svg','🎲':'dice.svg','📜':'history.svg',
        '📖':'history.svg','📚':'history.svg','🔄':'history.svg','👥':'users.svg','👑':'users.svg','🟢':'icon.svg',
        '🔴':'icon.svg','⚠️':'icon.svg','⚠':'icon.svg','✅':'icon.svg','❌':'icon.svg','➕':'icon.svg','➖':'icon.svg',
        '⬆️':'icon.svg','⬇️':'icon.svg','▶️':'icon.svg','▶':'icon.svg','◀':'icon.svg','✋':'cursor.svg','📏':'cursor.svg',
        '🖌️':'cursor.svg','🔍':'icon.svg','🔎':'icon.svg','❤️':'icon.svg','💀':'icon.svg','🛡️':'icon.svg',
        '⚔️':'icon.svg','⚔':'icon.svg','🎯':'icon.svg','🔮':'icon.svg','✨':'icon.svg','💰':'icon.svg','🏰':'map.svg',
        '🚪':'icon.svg','🔐':'icon.svg','🚫':'icon.svg','🏠':'map.svg','💾':'icon.svg','🌟':'icon.svg','🏹':'icon.svg',
        '🏋️':'icon.svg','💪':'icon.svg','💡':'icon.svg','🤝':'users.svg','🕸️':'icon.svg','🕊️':'icon.svg','🎵':'icon.svg',
        '📋':'history.svg','📌':'icon.svg','🔑':'icon.svg','💸':'icon.svg','🏃':'icon.svg','🛒':'props.svg','🔷':'icon.svg',
        '🔺':'icon.svg','💯':'icon.svg','🟡':'icon.svg','🔵':'icon.svg','🌋':'icon.svg'
    };
    const escaped = Object.keys(icons).sort((a,b)=>b.length-a.length).map(s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
    const pattern = new RegExp('(' + escaped.join('|') + ')','g');
    const svgPaths = {
        'map.svg':'<path d="M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z"/><path d="M9 3v15M15 6v15"/>',
        'bestiary.svg':'<path d="M6 8V5a2 2 0 0 1 4 0v3M10 8V4a2 2 0 0 1 4 0v5M14 9V6a2 2 0 0 1 4 0v8a6 6 0 0 1-12 0V9a2 2 0 0 1 4 0"/>',
        'props.svg':'<path d="M4 9h16v10H4zM2 9h20M7 5h10l2 4H5z"/>',
        'trash.svg':'<path d="M3 6h18M8 6V4h8v2m-10 0 1 15h10l1-15M10 10v7M14 10v7"/>',
        'fog.svg':'<path d="M5 18a4 4 0 1 1 1-7.87A6 6 0 0 1 18 12a3 3 0 0 1 0 6z"/>',
        'dice.svg':'<path d="m12 2 9 5v10l-9 5-9-5V7zM3 7l9 5 9-5M12 12v10"/>',
        'history.svg':'<path d="M4 6h16M4 12h12M4 18h8"/>',
        'users.svg':'<circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0M16 5a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 6"/>',
        'cursor.svg':'<path d="m5 3 5 17 3-7 7-3z"/>'
    };
    function icon(src, label) {
        const span = document.createElement('span');
        span.className = 'emoji-icon';
        span.setAttribute('aria-hidden','true');
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor'); svg.setAttribute('stroke-width', '1.8');
        svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('stroke-linejoin', 'round');
        svg.innerHTML = svgPaths[src] || '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>';
        span.appendChild(svg);
        return span;
    }
    function process(root) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) {
            const node = walker.currentNode;
            if (node.parentElement.closest('script,style,textarea,pre,code,.no-iconify')) continue;
            if (pattern.test(node.nodeValue)) { nodes.push(node); pattern.lastIndex = 0; }
        }
        nodes.forEach(node => {
            const frag = document.createDocumentFragment(); let last = 0; pattern.lastIndex = 0; let match;
            while ((match = pattern.exec(node.nodeValue))) {
                frag.appendChild(document.createTextNode(node.nodeValue.slice(last, match.index)));
                frag.appendChild(icon(icons[match[0]], match[0])); last = match.index + match[0].length;
            }
            frag.appendChild(document.createTextNode(node.nodeValue.slice(last))); node.replaceWith(frag);
        });
    }
    function init() {
        process(document.body);
        const observer = new MutationObserver(mutations => mutations.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1) process(n); })));
        observer.observe(document.body, { childList: true, subtree: true });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
