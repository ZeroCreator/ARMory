let affairsOverview = { projects: [], notes: [], comments: [], events: [] };
let myAffairs = [];
let affairsProjectSortable = null;
let currentAffairReader = null;
let affairContextTarget = null;

document.addEventListener('DOMContentLoaded', async () => {
    document.getElementById('overview-mode').addEventListener('change', renderOverview);
    document.getElementById('overview-project-filter').addEventListener('change', renderOverview);
    if (PERSONAL_NOTES_ENABLED) {
        document.getElementById('affair-project-filter').addEventListener('change', renderMyAffairs);
        document.getElementById('affair-status-filter').addEventListener('change', renderMyAffairs);
        document.getElementById('quick-affair-form').addEventListener('submit', createQuickAffair);
    }
    await Promise.all([loadOverview(), ...(PERSONAL_NOTES_ENABLED ? [loadAffairs()] : [])]);
    initAffairContextMenu();
    applyAffairsUrlState();
});

async function loadOverview() {
    try {
        affairsOverview = await api('/api/affairs/overview');
        populateProjectFilters();
        renderOverview();
        if (PERSONAL_NOTES_ENABLED) renderMyAffairs();
    } catch (error) {
        showAffairsError('affairs-overview-content', error);
    }
}

async function loadAffairs() {
    try {
        myAffairs = await api('/api/affairs');
        renderMyAffairs();
    } catch (error) {
        showAffairsError('affairs-list', error);
    }
}

function populateProjectFilters() {
    const projects = affairsOverview.projects || [];
    const targets = [
        ['overview-project-filter', 'Все проекты'],
        ['affair-project-filter', 'Все проекты'],
        ['quick-affair-project', 'Без проекта'],
    ];
    targets.forEach(([id, firstLabel]) => {
        const select = document.getElementById(id);
        if (!select) return;
        const selected = select.value;
        select.innerHTML = `<option value="">${firstLabel}</option>` + projects.map(project =>
            `<option value="${project.id}">${escapeAffairsHtml(project.name)}</option>`
        ).join('') + (id === 'affair-project-filter' ? '<option value="none">Без проекта</option>' : '');
        select.value = selected;
    });
}

function renderOverview() {
    const container = document.getElementById('affairs-overview-content');
    const mode = document.getElementById('overview-mode').value;
    const projectFilter = document.getElementById('overview-project-filter').value;
    const notes = filterByProject(affairsOverview.notes || [], projectFilter);
    const events = filterByProject(affairsOverview.events || [], projectFilter);

    if (mode === 'date') {
        destroyProjectSortable();
        container.innerHTML = renderColumns(notes, events, '');
        return;
    }

    const projectMap = new Map((affairsOverview.projects || []).map(project => [String(project.id), project]));
    const groups = [];
    getProjectOrder().forEach(id => {
        const project = projectMap.get(String(id));
        if (project) {
            groups.push(project);
            projectMap.delete(String(id));
        }
    });
    groups.push(...projectMap.values());
    const visibleGroups = projectFilter ? groups.filter(project => String(project.id) === projectFilter) : groups;
    const hasUnassigned = !projectFilter && (
        PERSONAL_NOTES_ENABLED || notes.some(note => note.project_id === null) || events.some(event => event.project_id === null)
    );
    container.innerHTML = `<div class="affairs-projects" id="affairs-projects">${visibleGroups.map(project =>
        renderProjectBlock(project, notes, events)
    ).join('')}${hasUnassigned ? renderProjectBlock({ id: '', name: 'Без проекта' }, notes, events) : ''}</div>`;
    initProjectSortable();
}

function renderProjectBlock(project, notes, events) {
    const projectNotes = notes.filter(item => String(item.project_id ?? '') === String(project.id));
    const projectEvents = events.filter(item => String(item.project_id ?? '') === String(project.id));
    const collapsed = isProjectCollapsed(project.id, projectNotes.length === 0 && projectEvents.length === 0);
    const projectLinks = project.id === '' ? '' : `<nav class="affairs-project-links" aria-label="Разделы проекта">
        <a href="/projects/${project.id}"><i class="bi bi-folder2-open me-1"></i>Проект</a>
        <a href="/projects/${project.id}/kanban"><i class="bi bi-kanban me-1"></i>Kanban</a>
        <a href="/projects/${project.id}/tasks"><i class="bi bi-list-task me-1"></i>ToDo</a>
    </nav>`;
    return `<article class="affairs-project-block ${collapsed ? 'is-collapsed' : ''}" data-project-id="${project.id}">
        <header class="affairs-project-header">
            <i class="bi bi-grip-vertical affairs-drag-handle"></i>
            <span>${escapeAffairsHtml(project.name)}</span>
            <span class="affairs-project-summary">${projectNotes.length} замет. · ${projectEvents.length} событ.</span>
            ${projectLinks}
            <button class="affairs-project-toggle" type="button" onclick="toggleProjectBlock(this)" aria-expanded="${!collapsed}" title="${collapsed ? 'Показать данные' : 'Скрыть данные'}">
                <i class="bi bi-chevron-${collapsed ? 'down' : 'up'}"></i>
            </button>
        </header>
        ${renderColumns(projectNotes, projectEvents, project.id)}
    </article>`;
}

function toggleProjectBlock(button) {
    const block = button.closest('.affairs-project-block');
    const collapsed = block.classList.toggle('is-collapsed');
    button.setAttribute('aria-expanded', String(!collapsed));
    button.title = collapsed ? 'Показать данные' : 'Скрыть данные';
    button.querySelector('i').className = `bi bi-chevron-${collapsed ? 'down' : 'up'}`;
    const states = getProjectCollapseStates();
    states[block.dataset.projectId || 'unassigned'] = collapsed;
    localStorage.setItem(projectCollapseKey(), JSON.stringify(states));
}

function renderColumns(notes, events, projectId = null) {
    const noteEditor = projectId === null ? '' : `<form class="affairs-inline-note" onsubmit="createInlineAffair(event, '${projectId}')">
        <input name="title" maxlength="255" placeholder="Заголовок (необязательно)" aria-label="Заголовок заметки">
        <textarea name="text" rows="4" required placeholder="Введите заметку…" aria-label="Текст заметки"></textarea>
        <label class="form-check mb-0"><input class="form-check-input" type="checkbox" name="show_in_news"><span class="form-check-label small"><i class="bi bi-newspaper me-1"></i>Показывать в новостной ленте</span></label>
        <button class="affairs-note-submit" type="submit" title="Сохранить заметку" aria-label="Сохранить заметку"><i class="bi bi-plus-lg"></i></button>
    </form>`;
    return `<div class="affairs-columns">
        <section class="affairs-column"><h5><span><i class="bi bi-journal-text me-1"></i> Заметки <span class="badge text-bg-light">${notes.length}</span></span></h5>${noteEditor}<div class="affairs-scroll">${notes.length ? notes.map(renderNote).join('') : emptyAffairs('Нет заметок')}</div></section>
        <section class="affairs-column"><h5><i class="bi bi-calendar-event me-1"></i> События <span class="badge text-bg-light">${events.length}</span></h5><div class="affairs-scroll">${events.length ? events.map(renderEvent).join('') : emptyAffairs('Нет событий')}</div></section>
    </div>`;
}

function renderNote(note) {
    return `<div class="affairs-item affairs-editable-note ${note.is_completed ? 'opacity-50' : ''}" data-affair-id="${note.id}" data-affair-shared="true" onclick="openAffairReader(event, ${note.id}, true)" oncontextmenu="openAffairContextMenu(event, ${note.id}, true)">
        <div class="affairs-item-meta"><span>${escapeAffairsHtml(note.project_name || 'Без проекта')}</span><time>${formatAffairsDate(note.updated_at)}</time></div>
        <div class="affairs-note-view">
            <div class="d-flex align-items-start gap-2"><div class="fw-semibold flex-grow-1">${escapeAffairsHtml(note.title)}</div>${renderAffairActions(note)}</div>
            ${note.description ? `<div class="small text-muted mt-1 affairs-note-text">${linkifyText(note.description)}</div>` : ''}
        </div>
        ${renderAffairEditForm(note)}
    </div>`;
}

function renderComment(comment) {
    return `<a class="affairs-item affairs-comment-item" href="/projects/${comment.project_id}">
        <div class="affairs-item-meta"><span>${escapeAffairsHtml(comment.project_name || 'Проект')}</span><time>${formatAffairsDate(comment.created_at)}</time></div>
        <div>${escapeAffairsHtml(comment.content)}</div>
    </a>`;
}

function renderEvent(event) {
    return `<div class="affairs-item" style="--affair-accent:${event.color || '#a78bfa'}">
        <div class="affairs-item-meta"><span>${escapeAffairsHtml(event.project_name || 'Без проекта')}</span><time>${formatAffairsDate(event.start_date)}</time></div>
        <div class="fw-semibold">${escapeAffairsHtml(event.title)}</div>
        ${event.description ? `<div class="small text-muted mt-1">${escapeAffairsHtml(event.description)}</div>` : ''}
    </div>`;
}

function renderMyAffairs() {
    const container = document.getElementById('affairs-list');
    const project = document.getElementById('affair-project-filter').value;
    const status = document.getElementById('affair-status-filter').value;
    const filtered = myAffairs.filter(item => {
        if (project === 'none' && item.project_id !== null) return false;
        if (project && project !== 'none' && String(item.project_id ?? '') !== project) return false;
        if (status === 'active' && item.is_completed) return false;
        if (status === 'completed' && !item.is_completed) return false;
        return true;
    });
    renderAffairProjectCards(project, filtered);
    container.innerHTML = project === ''
        ? (filtered.length ? filtered.map(renderAffair).join('') : emptyAffairs('Заметок по выбранному фильтру нет'))
        : '';
}

function renderAffairProjectCards(selectedProject, filteredNotes) {
    const container = document.getElementById('affair-project-cards');
    const notes = myAffairs;
    const cards = [
        { id: '', name: 'Все проекты', icon: 'collection', count: notes.length },
        ...(affairsOverview.projects || []).map(project => ({
            ...project,
            icon: 'folder',
            count: notes.filter(item => String(item.project_id ?? '') === String(project.id)).length,
        })),
        { id: 'none', name: 'Без проекта', icon: 'journal-text', count: notes.filter(item => item.project_id === null).length },
    ];
    container.innerHTML = cards.map(card => {
        const filterValue = String(card.id);
        const isActive = selectedProject === filterValue;
        const expandedNotes = isActive && filterValue !== ''
            ? `<div class="affair-project-card-notes">${filteredNotes.length ? filteredNotes.map(renderAffair).join('') : emptyAffairs('Заметок по выбранному фильтру нет')}</div>`
            : '';
        return `<article class="affair-project-card ${isActive ? 'is-active' : ''} ${isActive && filterValue !== '' ? 'is-expanded' : ''}">
            <button class="affair-project-card-button" type="button" onclick="selectAffairProject('${isActive && filterValue !== '' ? '' : filterValue}')" aria-expanded="${isActive && filterValue !== ''}">
                <span class="affair-project-card-topline">
                    <i class="bi bi-${card.icon} affair-project-card-icon"></i>
                    <span class="affair-project-card-count">${card.count} ${affairsNoteWord(card.count)}</span>
                </span>
                <span class="affair-project-card-title">${escapeAffairsHtml(card.name)}${filterValue !== '' ? `<i class="bi bi-chevron-${isActive ? 'up' : 'down'} affair-project-card-chevron"></i>` : ''}</span>
            </button>
            ${expandedNotes}
        </article>`;
    }).join('');
}

function selectAffairProject(projectId) {
    document.getElementById('affair-project-filter').value = projectId;
    document.getElementById('quick-affair-project').value = projectId === 'none' ? '' : projectId;
    renderMyAffairs();
}

function affairsNoteWord(count) {
    const mod100 = count % 100;
    const mod10 = count % 10;
    if (mod100 >= 11 && mod100 <= 14) return 'заметок';
    if (mod10 === 1) return 'заметка';
    if (mod10 >= 2 && mod10 <= 4) return 'заметки';
    return 'заметок';
}

function renderAffair(item) {
    return `<article class="affair-card affairs-editable-note ${item.is_completed ? 'is-completed' : ''}" data-affair-id="${item.id}" data-affair-shared="false" onclick="openAffairReader(event, ${item.id}, false)" oncontextmenu="openAffairContextMenu(event, ${item.id}, false)">
        <button class="btn btn-sm ${item.is_completed ? 'btn-success' : 'btn-outline-secondary'} affair-check" onclick="toggleAffair(${item.id}, ${!item.is_completed})" title="${item.is_completed ? 'Вернуть из архива' : 'В архив'}"><i class="bi bi-check-lg"></i></button>
        <div class="flex-grow-1 min-width-0"><div class="affairs-note-view"><div class="d-flex flex-wrap justify-content-between gap-2"><h5 class="mb-1">${escapeAffairsHtml(item.title)}</h5><span class="small text-muted">${item.due_date ? `до ${formatAffairsDate(item.due_date)}` : 'без дедлайна'}</span></div>
        <div class="small text-muted mb-1">${escapeAffairsHtml(item.project_name || 'Без проекта')}</div>${item.description ? `<div class="affairs-note-text">${linkifyText(item.description)}</div>` : ''}</div>${renderAffairEditForm(item)}</div>
        ${renderAffairActions(item)}
    </article>`;
}

function renderAffairActions(item) {
    return `<span class="affairs-note-actions">
        <button class="affairs-note-task-button" type="button" onclick="${item.project_id ? `addAffairToTasks(${item.id}, ${item.project_id}, ${!!item.is_shared})` : `chooseAffairTaskProject(this, ${item.id}, ${!!item.is_shared})`}" title="Добавить в Kanban и ToDo"><i class="bi bi-kanban me-1"></i>В Kanban и ToDo</button>
        <button class="btn btn-sm btn-outline-secondary" type="button" onclick="startAffairEdit(this)" title="Редактировать" aria-label="Редактировать заметку"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-sm btn-outline-danger" type="button" onclick="deleteAffair(${item.id})" title="Удалить" aria-label="Удалить заметку"><i class="bi bi-trash"></i></button>
    </span>`;
}

function renderAffairEditForm(item) {
    return `<form class="affairs-note-edit-form d-none" onsubmit="saveAffairEdit(event, ${item.id})">
        <input class="form-control form-control-sm" name="title" maxlength="255" value="${escapeAffairsHtml(item.title)}" placeholder="Заголовок (необязательно)" aria-label="Заголовок заметки">
        <textarea class="form-control form-control-sm" name="description" rows="4" aria-label="Текст заметки">${escapeAffairsHtml(item.description || '')}</textarea>
        <label class="form-check"><input class="form-check-input" type="checkbox" name="show_in_news" ${item.show_in_news ? 'checked' : ''}><span class="form-check-label small"><i class="bi bi-newspaper me-1"></i>Показывать в новостной ленте</span></label>
        <div class="d-flex justify-content-end gap-2">
            <button class="btn btn-sm btn-outline-secondary" type="button" onclick="cancelAffairEdit(this)">Отмена</button>
            <button class="btn btn-sm btn-success" type="submit">Сохранить</button>
        </div>
    </form>`;
}

function startAffairEdit(button) {
    const card = button.closest('.affairs-editable-note');
    card.querySelector('.affairs-note-view').classList.add('d-none');
    card.querySelector('.affairs-note-actions').classList.add('d-none');
    const form = card.querySelector('.affairs-note-edit-form');
    form.classList.remove('d-none');
    form.querySelector('input[name="title"]').focus();
}

function cancelAffairEdit(button) {
    const card = button.closest('.affairs-editable-note');
    card.querySelector('.affairs-note-edit-form').classList.add('d-none');
    card.querySelector('.affairs-note-view').classList.remove('d-none');
    card.querySelector('.affairs-note-actions').classList.remove('d-none');
}

async function saveAffairEdit(event, id) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    const note = affairFieldsFromText(data.description, data.title);
    if (!note) {
        showToast('Введите заголовок или текст заметки', 'warning');
        return;
    }
    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
        await api(`/api/affairs/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...note, show_in_news: data.show_in_news === 'on' }),
        });
        await refreshAffairsViews();
        showToast('Заметка обновлена', 'success');
    } catch (error) {
        showToast(error.message || 'Не удалось обновить заметку', 'danger');
        submitButton.disabled = false;
    }
}

async function createQuickAffair(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    const note = affairFieldsFromText(data.text, data.title);
    if (!note) return;
    const projectId = data.project_id ? Number(data.project_id) : null;
    const addToTasks = data.add_to_tasks === 'on';
    const showInNews = data.show_in_news === 'on';
    if (addToTasks && !projectId) {
        showToast('Для добавления в Kanban и ToDo выберите проект', 'warning');
        return;
    }
    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
        const created = await api('/api/affairs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...note, project_id: projectId, due_date: data.due_date || null, is_shared: false, show_in_news: showInNews }),
        });
        myAffairs.unshift(created);
        form.reset();
        renderMyAffairs();
        if (addToTasks) {
            openAffairDraftInKanban(created, projectId);
            return;
        }
        await loadOverview();
        showToast('Заметка добавлена', 'success');
    } catch (error) {
        showToast(error.message || 'Не удалось добавить заметку', 'danger');
    } finally {
        submitButton.disabled = false;
    }
}

async function createInlineAffair(event, projectId) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const note = affairFieldsFromText(formData.get('text'), formData.get('title'));
    if (!note) return;
    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
        const created = await api('/api/affairs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...note, project_id: projectId ? Number(projectId) : null, is_shared: true, show_in_news: formData.get('show_in_news') === 'on' }),
        });
        form.reset();
        await loadOverview();
        showToast('Заметка сохранена', 'success');
    } catch (error) {
        showToast(error.message || 'Не удалось сохранить заметку', 'danger');
    } finally {
        submitButton.disabled = false;
    }
}

function affairFieldsFromText(value, customTitle = '') {
    const text = String(value || '').trim();
    const title = String(customTitle || '').trim();
    if (!text && !title) return null;
    if (!text) return { title: title.slice(0, 255), description: null };
    if (title) return { title: title.slice(0, 255), description: text };
    const [firstLine, ...rest] = text.split(/\r?\n/);
    if (firstLine.length <= 255) {
        return { title: firstLine, description: rest.join('\n').trim() || null };
    }
    return { title: `${firstLine.slice(0, 252)}…`, description: text };
}

async function toggleAffair(id, isCompleted) {
    try {
        const updated = await api(`/api/affairs/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_completed: isCompleted }),
        });
        const index = myAffairs.findIndex(item => item.id === id);
        if (index !== -1) myAffairs[index] = updated;
        renderMyAffairs();
        await loadOverview();
    } catch (error) {
        showToast(error.message || 'Не удалось обновить заметку', 'danger');
    }
}

async function deleteAffair(id) {
    if (!await showConfirm('Удалить эту заметку?', 'Удаление')) return;
    try {
        await api(`/api/affairs/${id}`, { method: 'DELETE' });
        await refreshAffairsViews();
    } catch (error) {
        showToast(error.message || 'Не удалось удалить заметку', 'danger');
    }
}

function addAffairToTasks(id, projectId, isShared) {
    const notes = isShared ? (affairsOverview.notes || []) : myAffairs;
    const note = notes.find(item => item.id === id);
    if (!note) return;
    openAffairDraftInKanban(note, projectId);
}

function openAffairDraftInKanban(note, projectId) {
    sessionStorage.setItem('affairs-kanban-task-draft', JSON.stringify({
        project_id: Number(projectId),
        title: note.title,
        description: note.description || '',
        due_date: note.due_date || null,
    }));
    window.location.href = `/projects/${projectId}/kanban?newTask=affair`;
}

function chooseAffairTaskProject(button, id, isShared) {
    const actions = button.closest('.affairs-note-actions');
    const options = (affairsOverview.projects || []).map(project =>
        `<option value="${project.id}">${escapeAffairsHtml(project.name)}</option>`
    ).join('');
    if (!options) {
        showToast('Сначала создайте проект', 'warning');
        return;
    }
    button.classList.add('d-none');
    actions.insertAdjacentHTML('afterbegin', `<select class="form-select form-select-sm affairs-note-task-project" onchange="if (this.value) addAffairToTasks(${id}, Number(this.value), ${isShared})">
        <option value="">Выберите проект…</option>${options}
    </select>`);
    actions.querySelector('.affairs-note-task-project').focus();
}

async function refreshAffairsViews() {
    await Promise.all([loadOverview(), ...(PERSONAL_NOTES_ENABLED ? [loadAffairs()] : [])]);
}

function initProjectSortable() {
    destroyProjectSortable();
    const board = document.getElementById('affairs-projects');
    if (!board || document.getElementById('overview-project-filter').value) return;
    affairsProjectSortable = Sortable.create(board, {
        animation: 160,
        handle: '.affairs-drag-handle',
        draggable: '.affairs-project-block[data-project-id]:not([data-project-id=""])',
        onEnd: () => {
            const ids = [...board.querySelectorAll('.affairs-project-block[data-project-id]:not([data-project-id=""])')].map(el => el.dataset.projectId);
            localStorage.setItem(projectOrderKey(), JSON.stringify(ids));
        },
    });
}

function destroyProjectSortable() {
    if (affairsProjectSortable) affairsProjectSortable.destroy();
    affairsProjectSortable = null;
}

function getProjectOrder() {
    try { return JSON.parse(localStorage.getItem(projectOrderKey())) || []; } catch (_) { return []; }
}

function getProjectCollapseStates() {
    try { return JSON.parse(localStorage.getItem(projectCollapseKey())) || {}; } catch (_) { return {}; }
}

function isProjectCollapsed(projectId, collapsedByDefault) {
    const states = getProjectCollapseStates();
    const key = String(projectId || 'unassigned');
    return Object.prototype.hasOwnProperty.call(states, key) ? states[key] : collapsedByDefault;
}

function projectOrderKey() { return `affairs-project-order:${affairsOverview.user_email || 'local.user'}`; }
function projectCollapseKey() { return `affairs-project-collapse:${affairsOverview.user_email || 'local.user'}`; }
function filterByProject(items, project) { return project ? items.filter(item => String(item.project_id ?? '') === project) : items; }
function emptyAffairs(text) { return `<div class="text-center text-muted py-4">${text}</div>`; }
function formatAffairsDate(value) { return value ? new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) : ''; }
function escapeAffairsHtml(value) { const el = document.createElement('div'); el.textContent = value ?? ''; return el.innerHTML; }
function showAffairsError(id, error) { document.getElementById(id).innerHTML = `<div class="alert alert-danger">${escapeAffairsHtml(error.message || 'Ошибка загрузки')}</div>`; }

function findAffair(id, isShared) {
    const source = isShared ? (affairsOverview.notes || []) : myAffairs;
    return source.find(item => item.id === Number(id)) || null;
}

function openAffairReader(event, id, isShared) {
    if (event?.target?.closest('button, a, form, input, textarea, select')) return;
    const note = findAffair(id, isShared);
    if (!note) return;
    currentAffairReader = { note, isShared };
    document.getElementById('affair-reader-project').textContent = note.project_name || 'Без проекта';
    document.getElementById('affair-reader-title').textContent = note.title || 'Заметка';
    const content = document.getElementById('affair-reader-content');
    content.innerHTML = note.description ? linkifyText(note.description) : '';
    content.classList.toggle('is-empty', !note.description);
    if (!note.description) content.textContent = 'У заметки нет дополнительного текста.';
    cancelCurrentAffairEdit();
    bootstrap.Modal.getOrCreateInstance(document.getElementById('affairReaderModal')).show();
}

async function saveCurrentAffair(event) {
    event.preventDefault();
    if (!currentAffairReader) return;
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    const note = affairFieldsFromText(data.description, data.title);
    if (!note) {
        showToast('Введите заголовок или текст заметки', 'warning');
        return;
    }
    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
        const updated = await api(`/api/affairs/${currentAffairReader.note.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...note, show_in_news: data.show_in_news === 'on' }),
        });
        currentAffairReader.note = updated;
        document.getElementById('affair-reader-title').textContent = updated.title;
        const content = document.getElementById('affair-reader-content');
        content.innerHTML = updated.description ? linkifyText(updated.description) : 'У заметки нет дополнительного текста.';
        content.classList.toggle('is-empty', !updated.description);
        cancelCurrentAffairEdit();
        await refreshAffairsViews();
        showToast('Заметка обновлена', 'success');
    } catch (error) {
        showToast(error.message || 'Не удалось обновить заметку', 'danger');
    } finally {
        submitButton.disabled = false;
    }
}

function openAffairContextMenu(event, id, isShared) {
    event.preventDefault();
    event.stopPropagation();
    const note = findAffair(id, isShared);
    const menu = document.getElementById('affair-context-menu');
    if (!note || !menu) return;
    affairContextTarget = { note, isShared, element: event.currentTarget };
    menu.style.display = 'block';
    menu.style.left = `${Math.min(event.clientX, window.innerWidth - 230)}px`;
    menu.style.top = `${Math.min(event.clientY, window.innerHeight - 230)}px`;
}

function hideAffairContextMenu() {
    const menu = document.getElementById('affair-context-menu');
    if (menu) menu.style.display = 'none';
}

function copyAffairLink(note) {
    const url = new URL('/affairs', window.location.origin);
    if (note.project_id != null) url.searchParams.set('project', note.project_id);
    url.searchParams.set('note', note.id);
    copyTextToClipboard(url.toString());
    showToast('Ссылка на заметку скопирована', 'success');
}

function editAffairTarget(target) {
    if (!target) return;
    bootstrap.Modal.getInstance(document.getElementById('affairReaderModal'))?.hide();
    const selector = `.affairs-editable-note[data-affair-id="${target.note.id}"][data-affair-shared="${target.isShared}"]`;
    const card = target.element?.isConnected ? target.element : document.querySelector(selector);
    const button = card?.querySelector('.affairs-note-actions .btn-outline-secondary');
    if (button) startAffairEdit(button);
}

function sendAffairTargetToKanban(target) {
    if (!target) return;
    if (!target.note.project_id) {
        showToast('Сначала назначьте заметке проект', 'warning');
        return;
    }
    addAffairToTasks(target.note.id, target.note.project_id, target.isShared);
}

function editCurrentAffair() {
    if (!currentAffairReader) return;
    const note = currentAffairReader.note;
    document.getElementById('affair-reader-title-input').value = note.title || '';
    document.getElementById('affair-reader-description').value = note.description || '';
    document.getElementById('affair-reader-show-in-news').checked = !!note.show_in_news;
    document.getElementById('affair-reader-content').classList.add('d-none');
    document.getElementById('affair-reader-footer').classList.add('d-none');
    document.getElementById('affair-reader-form').classList.remove('d-none');
    document.getElementById('affair-reader-title-input').focus();
}

function cancelCurrentAffairEdit() {
    document.getElementById('affair-reader-form').classList.add('d-none');
    document.getElementById('affair-reader-content').classList.remove('d-none');
    document.getElementById('affair-reader-footer').classList.remove('d-none');
}

async function deleteCurrentAffair() {
    if (!currentAffairReader) return;
    const id = currentAffairReader.note.id;
    bootstrap.Modal.getInstance(document.getElementById('affairReaderModal'))?.hide();
    currentAffairReader = null;
    await deleteAffair(id);
}

function sendCurrentAffairToKanban() {
    sendAffairTargetToKanban(currentAffairReader ? { ...currentAffairReader, element: null } : null);
}

function initAffairContextMenu() {
    const menu = document.getElementById('affair-context-menu');
    if (!menu || menu.dataset.initialized === 'true') return;
    menu.dataset.initialized = 'true';
    menu.addEventListener('click', async event => {
        const item = event.target.closest('.affair-context-item');
        if (!item || !affairContextTarget) return;
        const target = affairContextTarget;
        hideAffairContextMenu();
        if (item.dataset.action === 'copy-link') copyAffairLink(target.note);
        if (item.dataset.action === 'open') openAffairReader(null, target.note.id, target.isShared);
        if (item.dataset.action === 'edit') editAffairTarget(target);
        if (item.dataset.action === 'kanban') sendAffairTargetToKanban(target);
        if (item.dataset.action === 'delete') await deleteAffair(target.note.id);
    });
    document.addEventListener('click', event => {
        if (!event.target.closest('#affair-context-menu')) hideAffairContextMenu();
    });
}

function applyAffairsUrlState() {
    const params = new URLSearchParams(window.location.search);
    const projectId = params.get('project');
    if (projectId) {
        const projectFilter = document.getElementById('overview-project-filter');
        if (projectFilter && [...projectFilter.options].some(option => option.value === projectId)) {
            projectFilter.value = projectId;
            document.getElementById('overview-mode').value = 'projects';
            renderOverview();
        }
        const overviewTab = document.querySelector('[data-bs-target="#affairs-overview"]');
        if (overviewTab) bootstrap.Tab.getOrCreateInstance(overviewTab).show();
    }
    const noteId = Number(params.get('note'));
    if (!noteId) return;
    const sharedNote = (affairsOverview.notes || []).find(item => item.id === noteId);
    const personalNote = myAffairs.find(item => item.id === noteId);
    if (sharedNote) openAffairReader(null, noteId, true);
    else if (personalNote) openAffairReader(null, noteId, false);
}
