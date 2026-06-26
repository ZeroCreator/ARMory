// ═══════════════════════════════════════════════════
// Глоссарий
// ═══════════════════════════════════════════════════

const GLOSSARY_LIMIT = 20;
let glossaryPage = 0;
let glossarySearch = '';
let glossaryTopics = [];
let glossaryExpandedTopics = new Set();
let glossaryFilter = { type: 'all' };
let glossaryContextTarget = null;
let glossaryTotalCount = 0;

// ═══════════════════════════════════════════════════
// Темы и подтемы
// ═══════════════════════════════════════════════════

async function loadGlossaryTopics() {
    try {
        glossaryTopics = await api(`${API_BASE}/glossary/topics`);
        // Раскрываем темы с подтемами по умолчанию
        glossaryTopics.forEach(t => {
            if (t.subtopics && t.subtopics.length) glossaryExpandedTopics.add(t.id);
        });
        renderGlossaryTopics();
        fillTopicSelect();
    } catch (e) {
        document.getElementById('glossary-topics-list').innerHTML =
            `<div class="text-danger small text-center py-3">${e.message}</div>`;
    }
}

function getFilterTopicId() {
    if (glossaryFilter.type === 'topic') return glossaryFilter.id;
    if (glossaryFilter.type === 'subtopic') return glossaryFilter.topicId;
    return null;
}

function isTopicActive(topicId) {
    return glossaryFilter.type === 'topic' && glossaryFilter.id === topicId;
}

function isSubtopicActive(subtopicId) {
    return glossaryFilter.type === 'subtopic' && glossaryFilter.id === subtopicId;
}

function renderGlossaryTopics() {
    const listContainer = document.getElementById('glossary-topics-list');

    const allItem = `
        <div class="glossary-topic-item ${glossaryFilter.type === 'all' ? 'active' : ''}" onclick="setGlossaryFilter('all')">
            <span class="glossary-topic-name">Все термины</span>
        </div>
    `;
    const noTopicItem = `
        <div class="glossary-topic-item ${glossaryFilter.type === 'no-topic' ? 'active' : ''}" onclick="setGlossaryFilter('no-topic')">
            <span class="glossary-topic-name">Без темы</span>
        </div>
    `;

    if (!glossaryTopics.length) {
        listContainer.innerHTML = allItem + noTopicItem + `<div class="text-muted small text-center py-3">Нет тем</div>`;
        return;
    }

    const topicsHtml = glossaryTopics.map(topic => {
        const expanded = glossaryExpandedTopics.has(topic.id);
        const active = isTopicActive(topic.id);
        const subtopicsHtml = (topic.subtopics || []).map(sub => `
            <div class="glossary-subtopic-item ${isSubtopicActive(sub.id) ? 'active' : ''}"
                 data-subtopic-id="${sub.id}"
                 onclick="setGlossaryFilter('subtopic', ${sub.id}, ${topic.id})"
                 oncontextmenu="showGlossarySubtopicContextMenu(event, ${sub.id}, ${topic.id})">
                <span class="glossary-subtopic-name">${escapeHtml(sub.name)}</span>
                <span class="glossary-topic-count">${sub.term_count}</span>
            </div>
        `).join('');

        return `
            <div class="glossary-topic-group ${active ? 'active' : ''}" data-topic-id="${topic.id}">
                <div class="glossary-topic-row"
                     oncontextmenu="showGlossaryTopicContextMenu(event, ${topic.id})">
                    <button class="glossary-topic-toggle ${expanded ? 'expanded' : ''}"
                            onclick="event.stopPropagation(); toggleGlossaryTopic(${topic.id})">
                        <i class="bi bi-chevron-right"></i>
                    </button>
                    <span class="glossary-topic-name" onclick="setGlossaryFilter('topic', ${topic.id})">
                        ${escapeHtml(topic.name)}
                        <span class="glossary-topic-count">${topic.term_count}</span>
                    </span>
                </div>
                <div class="glossary-subtopics-list ${expanded ? '' : 'd-none'}">
                    ${subtopicsHtml}
                </div>
            </div>
        `;
    }).join('');

    listContainer.innerHTML = allItem + noTopicItem + topicsHtml;
}

function toggleGlossaryTopic(topicId) {
    if (glossaryExpandedTopics.has(topicId)) {
        glossaryExpandedTopics.delete(topicId);
    } else {
        glossaryExpandedTopics.add(topicId);
    }
    renderGlossaryTopics();
}

function setGlossaryFilter(type, id, topicId) {
    if (type === 'all' || type === 'no-topic') {
        glossaryFilter = { type };
    } else {
        glossaryFilter = { type, id, topicId };
    }
    glossaryPage = 0;
    renderGlossaryTopics();
    loadGlossary();
}

function fillTopicSelect(selectedTopicId) {
    const select = document.getElementById('glossary-topic-select');
    if (!select) return;
    const current = selectedTopicId !== undefined ? String(selectedTopicId || 0) : select.value;
    select.innerHTML = `<option value="0">Без темы</option>` +
        glossaryTopics.map(topic => `<option value="${topic.id}">${escapeHtml(topic.name)}</option>`).join('');
    select.value = current;
    fillSubtopicSelect(parseInt(current, 10));
}

function fillSubtopicSelect(topicId, selectedSubtopicId) {
    const select = document.getElementById('glossary-subtopic-select');
    if (!select) return;
    const current = selectedSubtopicId !== undefined ? String(selectedSubtopicId || 0) : select.value;
    const topic = glossaryTopics.find(t => t.id === topicId);
    select.innerHTML = `<option value="0">Без подтемы</option>` +
        ((topic && topic.subtopics) || []).map(sub => `<option value="${sub.id}">${escapeHtml(sub.name)}</option>`).join('');
    select.value = current;
}

function onTermTopicChange() {
    const topicId = parseInt(document.getElementById('glossary-topic-select').value, 10) || 0;
    fillSubtopicSelect(topicId);
}

// ═══════════════════════════════════════════════════
// Контекстные меню
// ═══════════════════════════════════════════════════

function showMenuAt(menuId, event) {
    event.preventDefault();
    event.stopPropagation();
    const menu = document.getElementById(menuId);
    menu.style.display = 'block';
    menu.style.left = `${event.clientX}px`;
    menu.style.top = `${event.clientY}px`;
}

function showGlossarySidebarHeaderContextMenu(event) {
    hideGlossaryContextMenus();
    glossaryContextTarget = { type: 'header' };
    showMenuAt('glossary-sidebar-header-context-menu', event);
}

function showGlossaryTopicContextMenu(event, topicId) {
    hideGlossaryContextMenus();
    glossaryContextTarget = { type: 'topic', id: topicId };
    showMenuAt('glossary-topic-context-menu', event);
}

function showGlossarySubtopicContextMenu(event, subtopicId, topicId) {
    hideGlossaryContextMenus();
    glossaryContextTarget = { type: 'subtopic', id: subtopicId, topicId };
    showMenuAt('glossary-subtopic-context-menu', event);
}

function hideGlossaryContextMenus() {
    ['glossary-sidebar-header-context-menu', 'glossary-topic-context-menu', 'glossary-subtopic-context-menu'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    glossaryContextTarget = null;
}

// ═══════════════════════════════════════════════════
// CRUD тем
// ═══════════════════════════════════════════════════

function showGlossaryTopicModal() {
    document.getElementById('glossary-topic-form').reset();
    new bootstrap.Modal(document.getElementById('glossaryTopicModal')).show();
}

async function saveGlossaryTopic() {
    const name = document.getElementById('glossary-topic-name').value.trim();
    if (!name) return alert('Введите название темы');
    try {
        await api(`${API_BASE}/glossary/topics`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        bootstrap.Modal.getInstance(document.getElementById('glossaryTopicModal')).hide();
        loadGlossaryTopics();
    } catch (e) {
        alert('Ошибка создания темы: ' + e.message);
    }
}

function showEditGlossaryTopicModal(topicId) {
    const topic = glossaryTopics.find(t => t.id === topicId);
    if (!topic) return;
    document.getElementById('edit-glossary-topic-id').value = topic.id;
    document.getElementById('edit-glossary-topic-name').value = topic.name;
    new bootstrap.Modal(document.getElementById('editGlossaryTopicModal')).show();
}

async function updateGlossaryTopic() {
    const topicId = document.getElementById('edit-glossary-topic-id').value;
    const name = document.getElementById('edit-glossary-topic-name').value.trim();
    if (!topicId || !name) return alert('Введите название темы');
    try {
        await api(`${API_BASE}/glossary/topics/${topicId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        bootstrap.Modal.getInstance(document.getElementById('editGlossaryTopicModal')).hide();
        loadGlossaryTopics();
        loadGlossary();
    } catch (e) {
        alert('Ошибка обновления темы: ' + e.message);
    }
}

async function deleteGlossaryTopic(topicId) {
    if (!confirm('Удалить тему и все её подтемы? Термины станут "без темы".')) return;
    try {
        await api(`${API_BASE}/glossary/topics/${topicId}`, { method: 'DELETE' });
        if (glossaryFilter.type === 'topic' && glossaryFilter.id === topicId) {
            glossaryFilter = { type: 'all' };
        }
        loadGlossaryTopics();
        loadGlossary();
    } catch (e) {
        alert('Ошибка удаления темы: ' + e.message);
    }
}

async function deleteGlossaryTopicFromModal() {
    const topicId = document.getElementById('edit-glossary-topic-id').value;
    if (!topicId) return;
    bootstrap.Modal.getInstance(document.getElementById('editGlossaryTopicModal')).hide();
    await deleteGlossaryTopic(topicId);
}

// ═══════════════════════════════════════════════════
// CRUD подтем
// ═══════════════════════════════════════════════════

function showGlossarySubtopicModal(topicId) {
    document.getElementById('glossary-subtopic-form').reset();
    document.getElementById('glossary-subtopic-topic-id').value = topicId;
    new bootstrap.Modal(document.getElementById('glossarySubtopicModal')).show();
}

async function saveGlossarySubtopic() {
    const topicId = parseInt(document.getElementById('glossary-subtopic-topic-id').value, 10);
    const name = document.getElementById('glossary-subtopic-name').value.trim();
    if (!topicId || !name) return alert('Введите название подтемы');
    try {
        await api(`${API_BASE}/glossary/subtopics`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic_id: topicId, name })
        });
        bootstrap.Modal.getInstance(document.getElementById('glossarySubtopicModal')).hide();
        glossaryExpandedTopics.add(topicId);
        loadGlossaryTopics();
    } catch (e) {
        alert('Ошибка создания подтемы: ' + e.message);
    }
}

function showEditGlossarySubtopicModal(subtopicId, topicId) {
    const topic = glossaryTopics.find(t => t.id === topicId);
    const subtopic = topic ? topic.subtopics.find(s => s.id === subtopicId) : null;
    if (!subtopic) return;
    document.getElementById('edit-glossary-subtopic-id').value = subtopic.id;
    document.getElementById('edit-glossary-subtopic-name').value = subtopic.name;
    new bootstrap.Modal(document.getElementById('editGlossarySubtopicModal')).show();
}

async function updateGlossarySubtopic() {
    const subtopicId = document.getElementById('edit-glossary-subtopic-id').value;
    const name = document.getElementById('edit-glossary-subtopic-name').value.trim();
    if (!subtopicId || !name) return alert('Введите название подтемы');
    try {
        await api(`${API_BASE}/glossary/subtopics/${subtopicId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        bootstrap.Modal.getInstance(document.getElementById('editGlossarySubtopicModal')).hide();
        loadGlossaryTopics();
        loadGlossary();
    } catch (e) {
        alert('Ошибка обновления подтемы: ' + e.message);
    }
}

async function deleteGlossarySubtopic(subtopicId) {
    if (!confirm('Удалить подтему? Термины из этой подтемы потеряют привязку к ней.')) return;
    try {
        await api(`${API_BASE}/glossary/subtopics/${subtopicId}`, { method: 'DELETE' });
        if (glossaryFilter.type === 'subtopic' && glossaryFilter.id === subtopicId) {
            glossaryFilter = { type: 'all' };
        }
        loadGlossaryTopics();
        loadGlossary();
    } catch (e) {
        alert('Ошибка удаления подтемы: ' + e.message);
    }
}

async function deleteGlossarySubtopicFromModal() {
    const subtopicId = document.getElementById('edit-glossary-subtopic-id').value;
    if (!subtopicId) return;
    bootstrap.Modal.getInstance(document.getElementById('editGlossarySubtopicModal')).hide();
    await deleteGlossarySubtopic(subtopicId);
}

// ═══════════════════════════════════════════════════
// Термины
// ═══════════════════════════════════════════════════

async function loadGlossary() {
    const container = document.getElementById('glossary-terms');
    glossarySearch = document.getElementById('glossary-search').value.trim();

    const countParams = new URLSearchParams();
    if (glossarySearch) countParams.set('q', glossarySearch);
    if (glossaryFilter.type === 'topic') {
        countParams.set('topic_id', String(glossaryFilter.id));
    } else if (glossaryFilter.type === 'subtopic') {
        countParams.set('subtopic_id', String(glossaryFilter.id));
    } else if (glossaryFilter.type === 'no-topic') {
        countParams.set('topic_id', '0');
    }

    const listParams = new URLSearchParams({ skip: glossaryPage * GLOSSARY_LIMIT, limit: String(GLOSSARY_LIMIT) });
    if (glossarySearch) listParams.set('q', glossarySearch);
    if (glossaryFilter.type === 'topic') {
        listParams.set('topic_id', String(glossaryFilter.id));
    } else if (glossaryFilter.type === 'subtopic') {
        listParams.set('subtopic_id', String(glossaryFilter.id));
    } else if (glossaryFilter.type === 'no-topic') {
        listParams.set('topic_id', '0');
    }

    try {
        const [total, terms] = await Promise.all([
            api(`${API_BASE}/glossary/count?${countParams.toString()}`),
            api(`${API_BASE}/glossary?${listParams.toString()}`)
        ]);
        glossaryTotalCount = total;
        renderGlossaryTerms(terms);
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Ошибка загрузки: ${e.message}</div>`;
        document.getElementById('glossary-pagination').innerHTML = '';
    }
}

function renderGlossaryTerms(terms) {
    const container = document.getElementById('glossary-terms');
    const pagination = document.getElementById('glossary-pagination');
    const totalPages = Math.ceil(glossaryTotalCount / GLOSSARY_LIMIT);

    if (!terms.length) {
        container.innerHTML = `
            <div class="empty-state py-5">
                <i class="bi bi-book"></i>
                <p>Термины не найдены</p>
            </div>`;
        pagination.innerHTML = '';
        return;
    }

    container.innerHTML = terms.map((term, idx) => `
        <div class="glossary-term-card" id="term-${term.id}">
            <div class="glossary-term-header" data-bs-toggle="collapse" data-bs-target="#term-body-${term.id}" aria-expanded="false">
                <div class="d-flex flex-column justify-content-center">
                    <span class="glossary-term-name">${escapeHtml(term.term)}</span>
                    ${term.topic ? `<span class="glossary-term-subtopic">${escapeHtml(term.topic.name)}</span>` : ''}
                    ${term.subtopic ? `<span class="glossary-term-subtopic">${escapeHtml(term.subtopic.name)}</span>` : ''}
                </div>
                <div class="d-flex align-items-center gap-2">
                    <i class="bi bi-chevron-down glossary-term-chevron"></i>
                    <button class="btn btn-sm btn-outline-success" onclick="event.stopPropagation(); editGlossaryTerm(${term.id})" title="Редактировать">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="event.stopPropagation(); deleteGlossaryTermById(${term.id})" title="Удалить">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
            <div class="collapse" id="term-body-${term.id}">
                <div class="glossary-term-body">
                    ${term.topic ? `<div class="glossary-term-topic-badge mb-2">${escapeHtml(term.topic.name)}</div>` : ''}
                    ${term.short_definition ? `
                        <div class="glossary-term-short-section mb-3">
                            ${escapeHtml(term.short_definition)}
                        </div>` : ''}
                    ${term.definition ? `
                        <div class="glossary-term-definition-section">
                            ${escapeHtml(term.definition).replace(/\n/g, '<br>')}
                        </div>` : ''}
                    ${!term.short_definition && !term.definition ? `<p class="text-muted">Описание отсутствует</p>` : ''}
                </div>
            </div>
        </div>
    `).join('');

    renderPagination('glossary-pagination', glossaryPage + 1, totalPages, (page) => {
        glossaryPage = page - 1;
        loadGlossary();
    }, container);
}

function changeGlossaryPage(page) {
    glossaryPage = Math.max(0, page - 1);
    loadGlossary();
}

function showGlossaryModal() {
    document.getElementById('glossary-form').reset();
    document.getElementById('glossary-term-id').value = '';
    document.getElementById('glossary-modal-title').textContent = 'Новый термин';
    document.getElementById('glossary-delete-btn').style.display = 'none';
    fillTopicSelect(0);
    new bootstrap.Modal(document.getElementById('glossaryModal')).show();
}

async function editGlossaryTerm(termId) {
    try {
        const term = await api(`${API_BASE}/glossary/${termId}`);
        document.getElementById('glossary-term-id').value = term.id;
        document.getElementById('glossary-term-input').value = term.term;
        document.getElementById('glossary-short-definition').value = term.short_definition || '';
        document.getElementById('glossary-definition').value = term.definition || '';
        document.getElementById('glossary-modal-title').textContent = 'Редактировать термин';
        document.getElementById('glossary-delete-btn').style.display = 'inline-block';
        fillTopicSelect(term.topic_id);
        fillSubtopicSelect(term.topic_id || 0, term.subtopic_id);
        new bootstrap.Modal(document.getElementById('glossaryModal')).show();
    } catch (e) {
        alert('Ошибка загрузки термина: ' + e.message);
    }
}

async function saveGlossaryTerm() {
    const termId = document.getElementById('glossary-term-id').value;
    const term = document.getElementById('glossary-term-input').value.trim();
    const shortDefinition = document.getElementById('glossary-short-definition').value.trim();
    const definition = document.getElementById('glossary-definition').value.trim();
    const topicId = parseInt(document.getElementById('glossary-topic-select').value, 10) || 0;
    const subtopicId = parseInt(document.getElementById('glossary-subtopic-select').value, 10) || 0;

    if (!term) return alert('Введите термин');

    const payload = { term, short_definition: shortDefinition, definition, topic_id: topicId, subtopic_id: subtopicId };

    try {
        if (termId) {
            await api(`${API_BASE}/glossary/${termId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } else {
            await api(`${API_BASE}/glossary`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        }
        bootstrap.Modal.getInstance(document.getElementById('glossaryModal')).hide();
        loadGlossary();
        loadGlossaryTopics();
    } catch (e) {
        alert('Ошибка сохранения: ' + e.message);
    }
}

async function deleteGlossaryTerm() {
    const termId = document.getElementById('glossary-term-id').value;
    if (!termId) return;
    await deleteGlossaryTermById(termId);
    bootstrap.Modal.getInstance(document.getElementById('glossaryModal')).hide();
}

async function deleteGlossaryTermById(termId) {
    if (!confirm('Удалить этот термин?')) return;
    try {
        await api(`${API_BASE}/glossary/${termId}`, { method: 'DELETE' });
        loadGlossary();
        loadGlossaryTopics();
    } catch (e) {
        alert('Ошибка удаления: ' + e.message);
    }
}

async function exportGlossary() {
    try {
        const res = await fetch(`${API_BASE}/glossary/export`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `glossary_export_${new Date().toISOString().slice(0, 10)}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    } catch (e) {
        alert('Ошибка экспорта: ' + e.message);
    }
}

async function importGlossary(input) {
    const file = input.files[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
        alert('Выберите файл .xlsx');
        input.value = '';
        return;
    }

    const fd = new FormData();
    fd.append('file', file);

    try {
        const res = await fetch(`${API_BASE}/glossary/import`, {
            method: 'POST',
            body: fd,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        alert(`Импорт завершён:\n- тем создано: ${data.created_topics}\n- подтем создано: ${data.created_subtopics}\n- терминов создано: ${data.created_terms}\n- терминов обновлено: ${data.updated_terms}`);
        input.value = '';
        loadGlossary();
        loadGlossaryTopics();
    } catch (e) {
        alert('Ошибка импорта: ' + e.message);
        input.value = '';
    }
}

// ═══════════════════════════════════════════════════
// Инициализация
// ═══════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('glossary-terms')) {
        loadGlossaryTopics();
        loadGlossary();

        const searchInput = document.getElementById('glossary-search');
        searchInput.addEventListener('input', () => {
            glossaryPage = 0;
            loadGlossary();
        });

        const topicSelect = document.getElementById('glossary-topic-select');
        if (topicSelect) topicSelect.addEventListener('change', onTermTopicChange);

        // Глобальные обработчики контекстных меню
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.sidebar-context-menu')) hideGlossaryContextMenus();
        });
        document.addEventListener('scroll', hideGlossaryContextMenus, true);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') hideGlossaryContextMenus();
        });

        ['glossary-sidebar-header-context-menu', 'glossary-topic-context-menu', 'glossary-subtopic-context-menu'].forEach(id => {
            const menu = document.getElementById(id);
            if (!menu) return;
            menu.addEventListener('click', (e) => {
                const item = e.target.closest('.sidebar-context-item');
                if (!item) return;
                const action = item.dataset.action;
                const target = glossaryContextTarget;
                hideGlossaryContextMenus();

                if (action === 'add-topic') {
                    showGlossaryTopicModal();
                } else if (action === 'add-subtopic' && target) {
                    showGlossarySubtopicModal(target.id);
                } else if (action === 'edit-topic' && target) {
                    showEditGlossaryTopicModal(target.id);
                } else if (action === 'delete-topic' && target) {
                    deleteGlossaryTopic(target.id);
                } else if (action === 'edit-subtopic' && target) {
                    showEditGlossarySubtopicModal(target.id, target.topicId);
                } else if (action === 'delete-subtopic' && target) {
                    deleteGlossarySubtopic(target.id);
                }
            });
        });
    }
});
