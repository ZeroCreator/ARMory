const tagFilterInputState = new WeakMap();

function taskMatchesTagFilter(taskTags, filterValue) {
    const terms = String(filterValue || '')
        .toLocaleLowerCase('ru')
        .split(',')
        .map(tag => tag.trim())
        .filter(Boolean);
    if (!terms.length) return true;

    const tags = String(taskTags || '').toLocaleLowerCase('ru');
    return terms.some(tag => tags.includes(tag));
}

function populateTagFilterOptions(target, values) {
    const element = typeof target === 'string' ? document.getElementById(target) : target;
    if (!element) return;

    const tags = [...new Set((values || [])
        .flatMap(value => String(value ?? '').split(','))
        .map(tag => tag.trim())
        .filter(Boolean))]
        .sort((left, right) => left.localeCompare(right, 'ru'));

    if (element.tagName === 'SELECT') {
        const currentValue = element.value;
        const defaultLabel = element.options[0]?.textContent || 'Все';
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = defaultLabel;
        element.replaceChildren(defaultOption);
        tags.forEach(tag => {
            const option = document.createElement('option');
            option.value = tag;
            option.textContent = tag;
            element.appendChild(option);
        });
        element.value = currentValue;
        return;
    }

    if (element.tagName !== 'INPUT') return;

    const listId = element.getAttribute('list') || `${element.id}-options`;
    let datalist = document.getElementById(listId);
    if (!datalist) {
        datalist = document.createElement('datalist');
        datalist.id = listId;
        element.setAttribute('list', listId);
        element.insertAdjacentElement('afterend', datalist);
    }

    let state = tagFilterInputState.get(element);
    if (!state) {
        state = { tags: [], datalist };
        const updateSuggestions = () => {
            const value = element.value || '';
            const commaIndex = value.lastIndexOf(',');
            const segment = commaIndex === -1 ? value : value.slice(commaIndex + 1);
            const leadingWhitespace = segment.match(/^\s*/)?.[0] || '';
            const prefix = commaIndex === -1
                ? ''
                : `${value.slice(0, commaIndex + 1)}${leadingWhitespace || ' '}`;
            const query = segment.trim().toLocaleLowerCase('ru');
            const options = state.tags
                .filter(tag => !query || tag.toLocaleLowerCase('ru').startsWith(query))
                .map(tag => {
                    const option = document.createElement('option');
                    option.value = `${prefix}${tag}`;
                    return option;
                });
            state.datalist.replaceChildren(...options);
        };
        state.updateSuggestions = updateSuggestions;
        tagFilterInputState.set(element, state);
        element.addEventListener('input', updateSuggestions);
        element.addEventListener('focus', updateSuggestions);
    }
    state.tags = tags;
    state.datalist = datalist;
    state.updateSuggestions();
}
