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
    function icon(src, label) {
        const span = document.createElement('span');
        span.className = 'emoji-icon';
        span.setAttribute('aria-hidden','true');
        const img = document.createElement('img');
        img.src = '/static/images/' + src;
        img.alt = label || '';
        span.appendChild(img);
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
