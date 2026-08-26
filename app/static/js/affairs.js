let affairsOverview = { projects: [], comments: [], events: [] };
let myAffairs = [];
let affairsProjectSortable = null;

document.addEventListener('DOMContentLoaded', async () => {
    document.getElementById('overview-mode').addEventListener('change', renderOverview);
    document.getElementById('overview-project-filter').addEventListener('change', renderOverview);
    document.getElementById('affair-project-filter').addEventListener('change', renderMyAffairs);
    document.getElementById('affair-status-filter').addEventListener('change', renderMyAffairs);
    document.getElementById('affair-form').addEventListener('submit', createAffair);
    await Promise.all([loadOverview(), loadAffairs()]);
});

async function loadOverview() {
    try {
        affairsOverview = await api('/api/affairs/overview');
        populateProjectFilters();
        renderOverview();
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
        ['affair-project', 'Без проекта'],
    ];
    targets.forEach(([id, firstLabel]) => {
        const select = document.getElementById(id);
        const selected = select.value;
        select.innerHTML = `<option value="">${firstLabel}</option>` + projects.map(project =>
            `<option value="${project.id}">${escapeAffairsHtml(project.name)}</option>`
        ).join('');
        select.value = selected;
    });
}

function renderOverview() {
    const container = document.getElementById('affairs-overview-content');
    const mode = document.getElementById('overview-mode').value;
    const projectFilter = document.getElementById('overview-project-filter').value;
    const comments = filterByProject(affairsOverview.comments || [], projectFilter);
    const events = filterByProject(affairsOverview.events || [], projectFilter);

    if (mode === 'date') {
        destroyProjectSortable();
        container.innerHTML = renderTwoColumns(comments, events);
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
    const hasUnassigned = !projectFilter && events.some(event => event.project_id === null);
    container.innerHTML = `<div class="affairs-projects" id="affairs-projects">${visibleGroups.map(project =>
        renderProjectBlock(project, comments, events)
    ).join('')}${hasUnassigned ? renderProjectBlock({ id: '', name: 'Без проекта' }, comments, events) : ''}</div>`;
    initProjectSortable();
}

function renderProjectBlock(project, comments, events) {
    const projectComments = comments.filter(item => String(item.project_id ?? '') === String(project.id));
    const projectEvents = events.filter(item => String(item.project_id ?? '') === String(project.id));
    const collapsed = isProjectCollapsed(project.id, projectComments.length === 0 && projectEvents.length === 0);
    return `<article class="affairs-project-block ${collapsed ? 'is-collapsed' : ''}" data-project-id="${project.id}">
        <header class="affairs-project-header">
            <i class="bi bi-grip-vertical affairs-drag-handle"></i>
            <span>${escapeAffairsHtml(project.name)}</span>
            <span class="affairs-project-summary">${projectComments.length} обсужд. · ${projectEvents.length} событ.</span>
            <button class="affairs-project-toggle" type="button" onclick="toggleProjectBlock(this)" aria-expanded="${!collapsed}" title="${collapsed ? 'Показать данные' : 'Скрыть данные'}">
                <i class="bi bi-chevron-${collapsed ? 'down' : 'up'}"></i>
            </button>
        </header>
        ${renderTwoColumns(projectComments, projectEvents)}
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

function renderTwoColumns(comments, events) {
    return `<div class="affairs-columns">
        <section class="affairs-column"><h5><i class="bi bi-chat-dots me-1"></i> Мои обсуждения <span class="badge text-bg-light">${comments.length}</span></h5><div class="affairs-scroll">${comments.length ? comments.map(renderComment).join('') : emptyAffairs('Нет сообщений')}</div></section>
        <section class="affairs-column"><h5><i class="bi bi-calendar-event me-1"></i> События <span class="badge text-bg-light">${events.length}</span></h5><div class="affairs-scroll">${events.length ? events.map(renderEvent).join('') : emptyAffairs('Нет событий')}</div></section>
    </div>`;
}

function renderComment(comment) {
    return `<a class="affairs-item" href="/projects/${comment.project_id}">
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
        if (project && String(item.project_id ?? '') !== project) return false;
        if (status === 'active' && item.is_completed) return false;
        if (status === 'completed' && !item.is_completed) return false;
        return true;
    });
    container.innerHTML = filtered.length ? filtered.map(renderAffair).join('') : emptyAffairs('Дел по выбранному фильтру нет');
}

function renderAffair(item) {
    return `<article class="affair-card ${item.is_completed ? 'is-completed' : ''}">
        <button class="btn btn-sm ${item.is_completed ? 'btn-success' : 'btn-outline-secondary'} affair-check" onclick="toggleAffair(${item.id}, ${!item.is_completed})" title="${item.is_completed ? 'Вернуть в работу' : 'Выполнить'}"><i class="bi bi-check-lg"></i></button>
        <div class="flex-grow-1 min-width-0"><div class="d-flex flex-wrap justify-content-between gap-2"><h5 class="mb-1">${escapeAffairsHtml(item.title)}</h5><span class="small text-muted">${item.due_date ? `до ${formatAffairsDate(item.due_date)}` : 'без дедлайна'}</span></div>
        <div class="small text-muted mb-1">${escapeAffairsHtml(item.project_name || 'Без проекта')}</div>${item.description ? `<div>${escapeAffairsHtml(item.description)}</div>` : ''}</div>
        <button class="btn btn-sm btn-outline-danger" onclick="deleteAffair(${item.id})" title="Удалить"><i class="bi bi-trash"></i></button>
    </article>`;
}

async function createAffair(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    data.project_id = data.project_id ? Number(data.project_id) : null;
    data.due_date = data.due_date || null;
    try {
        const created = await api('/api/affairs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        myAffairs.unshift(created);
        form.reset();
        bootstrap.Modal.getInstance(document.getElementById('affairModal')).hide();
        renderMyAffairs();
        showToast('Дело добавлено', 'success');
    } catch (error) {
        showToast(error.message || 'Не удалось добавить дело', 'danger');
    }
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
    } catch (error) {
        showToast(error.message || 'Не удалось обновить дело', 'danger');
    }
}

async function deleteAffair(id) {
    if (!await showConfirm('Удалить это дело?', 'Удаление')) return;
    try {
        await api(`/api/affairs/${id}`, { method: 'DELETE' });
        myAffairs = myAffairs.filter(item => item.id !== id);
        renderMyAffairs();
    } catch (error) {
        showToast(error.message || 'Не удалось удалить дело', 'danger');
    }
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
