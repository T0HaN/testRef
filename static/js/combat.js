        const attrMap = {'standard':['STR'], 'finesse':['STR','DEX'], 'thrown':['DEX'], 'ammunition':['DEX']};
        const names = {'STR':'Сила','DEX':'Ловкость'};

        function selectWeapon(idx, name, type) {
            document.querySelectorAll('.w-btn').forEach(b => b.classList.remove('selected'));
            event.currentTarget.classList.add('selected');
            document.querySelector(`input[name="weapon_idx"][value="${idx}"]`).checked = true;

            const group = document.getElementById('attr-group');
            const sel = document.getElementById('attrChoice');
            group.style.display = 'block';
            sel.innerHTML = '';
            attrMap[type].forEach(a => {
                const opt = document.createElement('option');
                opt.value = a; opt.textContent = names[a];
                sel.appendChild(opt);
            });
        }
