const multiFilterStates = new WeakMap();

function getFilterElement(target) {
    return typeof target === 'string' ? document.getElementById(target) : target;
}

function getFilterValues(target) {
    const select = getFilterElement(target);
    if (!select) return [];

    const state = multiFilterStates.get(select);
    if (state) {
        return Array.from(state.menu.querySelectorAll('input:checked')).map(input => input.value);
    }

    if (select.tagName !== 'SELECT') return select.value ? [select.value] : [];
    return Array.from(select.selectedOptions || [])
        .map(option => option.value)
        .filter(Boolean);
}

function setFilterValues(target, values) {
    const select = getFilterElement(target);
    if (!select) return;

    const selected = new Set((Array.isArray(values) ? values : [values])
        .filter(value => value !== null && value !== undefined && String(value) !== '')
        .map(String));
    if (select.tagName !== 'SELECT') {
        select.value = selected.values().next().value || '';
        return;
    }

    Array.from(select.options).forEach(option => {
        option.selected = selected.has(option.value);
    });

    const state = multiFilterStates.get(select);
    if (state) {
        state.menu.querySelectorAll('input[type="checkbox"]').forEach(input => {
            input.checked = selected.has(input.value);
        });
        updateMultiFilterButton(state);
    }
}

function clearFilterValues(target) {
    setFilterValues(target, []);
    const element = getFilterElement(target);
    if (element && element.tagName !== 'SELECT') element.value = '';
}

function appendFilterValues(params, key, target) {
    getFilterValues(target).forEach(value => params.append(key, value));
}

function setFilterOptions(target, items, defaultLabel = 'Все') {
    const select = getFilterElement(target);
    if (!select) return;

    const previousValues = getFilterValues(select);
    const normalizedItems = (items || []).map(item => ({
        value: String(item.value ?? ''),
        label: String(item.label ?? item.value ?? ''),
    }));
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = defaultLabel;
    select.replaceChildren(defaultOption);
    normalizedItems.forEach(item => {
        const option = document.createElement('option');
        option.value = item.value;
        option.textContent = item.label;
        select.appendChild(option);
    });

    const availableValues = new Set(normalizedItems.map(item => item.value));
    setFilterValues(select, previousValues.filter(value => availableValues.has(String(value))));
    if (select.hasAttribute('data-multi-filter')) {
        initMultiFilter(select);
        const state = multiFilterStates.get(select);
        state.defaultLabel = defaultLabel;
        renderMultiFilterOptions(state);
    } else {
        select.value = previousValues.find(value => availableValues.has(String(value))) || '';
    }
}

function initMultiFilter(target) {
    const select = getFilterElement(target);
    if (!select || select.tagName !== 'SELECT' || !select.hasAttribute('data-multi-filter')) return;

    let state = multiFilterStates.get(select);
    if (state) {
        renderMultiFilterOptions(state);
        return state;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'multi-filter-control';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `form-select multi-filter-button${select.classList.contains('form-select-sm') ? ' form-select-sm' : ''}`;
    button.id = `${select.id}-button`;
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');
    const menu = document.createElement('div');
    menu.className = 'multi-filter-menu';
    menu.hidden = true;
    menu.setAttribute('role', 'listbox');
    menu.setAttribute('aria-multiselectable', 'true');

    select.classList.add('multi-filter-source');
    select.multiple = true;
    select.setAttribute('aria-hidden', 'true');
    select.tabIndex = -1;
    select.parentNode.insertBefore(wrapper, select);
    wrapper.append(select, button, menu);

    const label = document.querySelector(`label[for="${CSS.escape(select.id)}"]`);
    if (label) label.htmlFor = button.id;

    state = {
        select,
        wrapper,
        button,
        menu,
        defaultLabel: select.options[0]?.textContent || select.dataset.multiFilterDefault || 'Все',
    };
    multiFilterStates.set(select, state);

    button.addEventListener('click', event => {
        event.stopPropagation();
        const isHidden = menu.hidden;
        document.querySelectorAll('.multi-filter-menu:not([hidden])').forEach(openMenu => {
            openMenu.hidden = true;
            openMenu.previousElementSibling?.setAttribute('aria-expanded', 'false');
        });
        menu.hidden = !isHidden;
        button.setAttribute('aria-expanded', String(isHidden));
    });
    menu.addEventListener('click', event => event.stopPropagation());
    renderMultiFilterOptions(state);
    updateMultiFilterButton(state);
    return state;
}

function renderMultiFilterOptions(state) {
    const selected = new Set(getFilterValues(state.select));
    state.menu.replaceChildren();
    Array.from(state.select.options)
        .filter(option => option.value !== '')
        .forEach((option, index) => {
            const id = `${state.select.id}-option-${index}`;
            const label = document.createElement('label');
            label.className = 'form-check multi-filter-option';
            label.htmlFor = id;
            const input = document.createElement('input');
            input.type = 'checkbox';
            input.className = 'form-check-input';
            input.id = id;
            input.value = option.value;
            input.checked = selected.has(option.value);
            input.addEventListener('change', () => {
                option.selected = input.checked;
                updateMultiFilterButton(state);
                state.select.dispatchEvent(new Event('change', { bubbles: true }));
            });
            const text = document.createElement('span');
            text.className = 'multi-filter-option-label';
            text.textContent = option.textContent;
            label.append(input, text);
            state.menu.appendChild(label);
        });
    updateMultiFilterButton(state);
}

function updateMultiFilterButton(state) {
    const labels = Array.from(state.select.selectedOptions || [])
        .filter(option => option.value !== '')
        .map(option => option.textContent);
    state.button.textContent = labels.length ? labels.join(', ') : state.defaultLabel;
    state.button.title = state.button.textContent;
}

document.addEventListener('click', () => {
    document.querySelectorAll('.multi-filter-menu:not([hidden])').forEach(menu => {
        menu.hidden = true;
        menu.previousElementSibling?.setAttribute('aria-expanded', 'false');
    });
});

document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    document.querySelectorAll('.multi-filter-menu:not([hidden])').forEach(menu => {
        menu.hidden = true;
        menu.previousElementSibling?.setAttribute('aria-expanded', 'false');
    });
});

document.querySelectorAll('[data-multi-filter]').forEach(initMultiFilter);
