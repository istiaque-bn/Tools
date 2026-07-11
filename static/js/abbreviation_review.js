(() => {
    const config = window.reviewConfig;
    const cards = [...document.querySelectorAll('.suggestion-card')];
    const search = document.getElementById('suggestion-search');
    const status = document.getElementById('status-filter');
    const category = document.getElementById('category-filter');
    const ambiguity = document.getElementById('ambiguity-filter');

    async function request(url, data, method = 'POST') {
        const response = await fetch(url, {
            method,
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': config.csrf},
            body: JSON.stringify(data),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'The review action failed.');
        return payload;
    }

    function applyFilters() {
        const query = search.value.toLowerCase();
        cards.forEach(card => card.hidden = !(
            card.dataset.search.toLowerCase().includes(query) &&
            (!status.value || card.classList.contains(status.value)) &&
            (!category.value || card.dataset.category === category.value) &&
            (!ambiguity.value || card.dataset.ambiguity === ambiguity.value)
        ));
    }

    search.oninput = applyFilters;
    status.onchange = applyFilters;
    category.onchange = applyFilters;
    ambiguity.onchange = applyFilters;

    cards.forEach(card => {
        card.onclick = event => {
            if (!event.target.closest('button,select,input')) {
                document.getElementById('preview-' + card.dataset.id)?.scrollIntoView({behavior: 'smooth', block: 'center'});
            }
        };
        card.querySelectorAll('[data-action]').forEach(button => button.onclick = async () => {
            let replacement = '';
            const selected = card.querySelector('.meaning-select')?.value || null;
            if (button.dataset.action === 'edit') {
                replacement = prompt('Replacement text', card.querySelector('.proposed').textContent);
                if (replacement === null) return;
            }
            try {
                await request(config.suggestionUrl.replace('00000000-0000-0000-0000-000000000000', card.dataset.id), {
                    action: button.dataset.action,
                    replacement,
                    selected_meaning_id: selected,
                }, 'PATCH');
                location.reload();
            } catch (error) { alert(error.message); }
        });
    });

    document.querySelectorAll('[data-bulk]').forEach(button => button.onclick = async () => {
        const value = button.dataset.bulk;
        const visibleIds = cards.filter(card => !card.hidden).map(card => card.dataset.id);
        if (!visibleIds.length) return;
        try {
            await request(config.bulkUrl, {
                action: value === 'high' ? 'accept' : value,
                high_confidence: value === 'high',
                suggestion_ids: visibleIds,
            });
            location.reload();
        } catch (error) { alert(error.message); }
    });

    document.querySelectorAll('[data-history]').forEach(button => button.onclick = async () => {
        try {
            await request(config.historyUrl, {direction: button.dataset.history});
            location.reload();
        } catch (error) { alert(error.message); }
    });
})();
