// ═══════════════════════════════════════════════════
// СПИСОК ЗАДАЧ (ТАБЛИЦА)
// ═══════════════════════════════════════════════════

let allTasks = [];
let filteredTasks = [];
let filterOptions = { projects: [], priorities: [], assignees: [], tags: [], list_names: [] };
let assigneesMap = {};
let projectsMap = {};
let lastStatusIds = {};
let sortColumn = 'created_at';
let sortDirection = 'desc';
let selectedTaskIds = new Set();
let highlightedTaskId = null;
let currentTaskId = null;
let currentTaskProjectId = null;
let editingTaskAttachmentId = null;
let taskAttachments = {};
window.kanbanAttachments = window.kanbanAttachments || {};
let taskStatusCache = {};
let ganttKanbanStatusMap = {};
let ganttView = false;
let ganttHideNoDeadline = false;
let ganttStatusOverlayEnabled = true;
let taskStatusHistory = {};
let loadedTaskStatusHistoryIds = new Set();
let ganttMinDate = null;
let ganttMaxDate = null;
let ganttTotalDays = 0;
let ganttTimelineWidth = 0;
let currentUserEmail = null;

// ── Массовое добавление вложений к выбранным задачам ──
let groupProcessAttachments = [];
let groupProcessSelectedProjectId = null;

const SAVE_LIST_COLUMNS = [
    { key: 'id', label: '#', default: true },
    { key: 'project_name', label: 'Проект', default: true, globalOnly: true },
    { key: 'title', label: 'Название', default: true },
    { key: 'description', label: 'Описание', default: true },
    { key: 'status_name', label: 'Статус', default: true },
    { key: 'priority', label: 'Приоритет', default: true },
    { key: 'assignee_name', label: 'Ответственный', default: true },
    { key: 'start_date', label: 'Начало', default: true },
    { key: 'due_date', label: 'Дедлайн', default: true },
    { key: 'tags', label: 'Теги', default: true },
    { key: 'list_name', label: 'Список', default: true },
    { key: 'created_at', label: 'Создано', default: true },
    { key: 'is_closed', label: 'Закрыто', default: true },
];

// ── Импорт состояние ──
let importTasksState = [];
let importBulkAttachments = [];
let importNextTempId = 1;

document.addEventListener('DOMContentLoaded', async () => {
    loadCurrentUser();
    if (!IS_GLOBAL) {
        await loadProjectHeader(PROJECT_ID);
    } else {
        document.getElementById('tasks-list-title').innerHTML = '<i class="bi bi-list-task"></i> Все задачи';
    }
    await loadFilters();
    await loadTasks();

    const tableBody = document.getElementById('tasks-table-body');
    if (tableBody) {
        tableBody.addEventListener('click', (e) => {
            const checkbox = e.target.closest('[data-action="select-task"]');
            if (checkbox) {
                e.preventDefault();
                e.stopPropagation();
                toggleTaskSelected(parseInt(checkbox.dataset.taskId, 10));
                return;
            }

            if (e.target.closest('a, button, input, textarea, select, .actions-cell')) return;

            const row = e.target.closest('tr[data-task-id]');
            if (!row) return;

            const taskId = parseInt(row.dataset.taskId, 10);
            highlightedTaskId = taskId;
            toggleTaskSelected(taskId);
        });
    }

    document.addEventListener('keydown', handleTasksListKeydown);

    const importProjectSelect = document.getElementById('import-bulk-project');
    if (importProjectSelect) {
        importProjectSelect.addEventListener('change', loadImportStatuses);
    }
});

function handleTasksListKeydown(e) {
    const modalEl = document.getElementById('taskViewModal');
    const modalOpen = modalEl && modalEl.classList.contains('show');

    if (modalOpen) {
        if (e.key === 'Escape') {
            bootstrap.Modal.getInstance(modalEl)?.hide();
        }
        return;
    }

    const active = document.activeElement;
    if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.tagName === 'SELECT')) return;

    if (filteredTasks.length === 0) return;

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        let idx = filteredTasks.findIndex(t => t.id === highlightedTaskId);
        if (e.key === 'ArrowDown') {
            idx = (idx >= filteredTasks.length - 1 || idx === -1) ? 0 : idx + 1;
        } else {
            idx = (idx <= 0 || idx === -1) ? filteredTasks.length - 1 : idx - 1;
        }
        highlightedTaskId = filteredTasks[idx].id;
        renderTable();
        scrollHighlightedTaskIntoView();
    } else if (e.key === 'Enter' && highlightedTaskId !== null) {
        e.preventDefault();
        openTaskViewModal(highlightedTaskId);
    }
}

function scrollHighlightedTaskIntoView() {
    const row = document.querySelector(`#tasks-table-body tr[data-task-id="${highlightedTaskId}"]`);
    if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

async function loadCurrentUser() {
    try {
        const me = await api(`${API_BASE}/me`);
        currentUserEmail = me.email || null;
    } catch (e) {
        currentUserEmail = null;
    }
    updateAssignMeButtonVisibility();
}

function updateAssignMeButtonVisibility() {
    const btn = document.getElementById('task-assign-me-btn');
    if (btn) btn.style.display = currentUserEmail ? 'inline-block' : 'none';
}

async function loadProjectHeader(projectId) {
    try {
        const project = await api(`${API_BASE}/projects/${projectId}`);
        document.getElementById('tasks-list-title').innerHTML = `<i class="bi bi-list-task"></i> Задачи проекта «${escapeHtml(project.name)}»`;
    } catch (e) {
        console.error('Failed to load project header:', e);
    }
}

async function loadFilters() {
    try {
        const url = IS_GLOBAL ? `${API_BASE}/kanban/filters` : `${API_BASE}/projects/${PROJECT_ID}/kanban/filters`;
        filterOptions = await api(url);

        assigneesMap = {};
        (filterOptions.assignees || []).forEach(a => { assigneesMap[a.email] = a.name; });

        projectsMap = {};
        (filterOptions.projects || []).forEach(p => { projectsMap[p.id] = p.name; });

        populateSelect('filter-priority', (filterOptions.priorities || []).map(p => ({ value: p, label: priorityLabel(p) })));
        populateSelect('filter-assignee', (filterOptions.assignees || []).map(a => ({ value: a.email, label: a.name })));
        populateSelect('filter-list', (filterOptions.list_names || []).map(l => ({ value: l, label: l })));

        if (IS_GLOBAL) {
            populateSelect('filter-project', (filterOptions.projects || []).map(p => ({ value: p.id, label: p.name })));
            populateSelect('import-bulk-project', (filterOptions.projects || []).map(p => ({ value: p.id, label: p.name })));
        }
        initBulkAssigneeList('import-bulk');
    } catch (e) {
        console.error('Failed to load filters:', e);
    }
}

function populateSelect(id, items, defaultLabel = 'Все') {
    const select = document.getElementById(id);
    if (!select) return;
    const currentValue = select.value;
    const defaultText = select.options[0]?.text || defaultLabel;
    select.innerHTML = `<option value="">${defaultText}</option>` +
        items.map(item => `<option value="${escapeHtml(String(item.value))}">${escapeHtml(String(item.label))}</option>`).join('');
    select.value = currentValue;
}

async function loadTasks() {
    const tbody = document.getElementById('tasks-table-body');
    tbody.innerHTML = '<tr><td colspan="14" class="text-center text-muted py-4">Загрузка...</td></tr>';
    taskStatusHistory = {};
    loadedTaskStatusHistoryIds.clear();
    try {
        const url = IS_GLOBAL ? `${API_BASE}/tasks` : `${API_BASE}/projects/${PROJECT_ID}/tasks`;
        allTasks = await api(url);
        await loadLastStatuses();
        rebuildStatusFilter();
        applyFilters();
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="14" class="text-center text-danger py-4">Ошибка загрузки: ${escapeHtml(e.message)}</td></tr>`;
    }
}

async function loadLastStatuses() {
    lastStatusIds = {};
    ganttKanbanStatusMap = {};
    try {
        if (IS_GLOBAL) {
            const projectIds = [...new Set((allTasks || []).map(t => t.project_id).filter(Boolean))];
            await Promise.all(projectIds.map(async (projectId) => {
                const statuses = await api(`${API_BASE}/projects/${projectId}/task-statuses`);
                const sorted = (statuses || []).slice().sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
                const last = sorted.length ? sorted[sorted.length - 1] : null;
                if (last) lastStatusIds[projectId] = last.id;
                ganttKanbanStatusMap[projectId] = {
                    testingStatusId: sorted[2]?.id,
                    deployStatusId: sorted[3]?.id,
                };
            }));
        } else {
            const statuses = await api(`${API_BASE}/projects/${PROJECT_ID}/task-statuses`);
            const sorted = (statuses || []).slice().sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
            const last = sorted.length ? sorted[sorted.length - 1] : null;
            if (last) lastStatusIds[PROJECT_ID] = last.id;
            ganttKanbanStatusMap[PROJECT_ID] = {
                testingStatusId: sorted[2]?.id,
                deployStatusId: sorted[3]?.id,
            };
        }
    } catch (e) {
        console.error('Failed to load last statuses:', e);
    }
}

async function loadTaskStatusHistory(taskIds) {
    if (!taskIds || !taskIds.length) return;
    const url = `${API_BASE}/task-status-history?task_ids=${taskIds.join(',')}`;
    try {
        const data = await api(url);
        (data.items || []).forEach(item => {
            if (!taskStatusHistory[item.task_id]) taskStatusHistory[item.task_id] = [];
            taskStatusHistory[item.task_id].push(item);
        });
        taskIds.forEach(id => loadedTaskStatusHistoryIds.add(id));
    } catch (e) {
        console.error('Failed to load task status history:', e);
    }
}

async function ensureGanttStatusHistoryLoaded() {
    const tasksToRender = ganttHideNoDeadline
        ? filteredTasks.filter(t => t.due_date)
        : filteredTasks;
    const missing = tasksToRender
        .map(t => t.id)
        .filter(id => !loadedTaskStatusHistoryIds.has(id));
    if (missing.length) {
        await loadTaskStatusHistory(missing);
    }
}

function rebuildStatusFilter() {
    const statuses = [...new Set((allTasks || []).map(t => t.status?.name).filter(Boolean))];
    populateSelect('filter-status', statuses.map(s => ({ value: s, label: s })));
}

function applyFilters() {
    const search = document.getElementById('filter-search')?.value.toLowerCase().trim() || '';
    const projectId = document.getElementById('filter-project')?.value || '';
    const status = document.getElementById('filter-status')?.value || '';
    const priority = document.getElementById('filter-priority')?.value || '';
    const assignee = document.getElementById('filter-assignee')?.value || '';
    const listName = document.getElementById('filter-list')?.value || '';
    const closed = document.getElementById('filter-closed')?.value;
    const tags = document.getElementById('filter-tags')?.value.toLowerCase().trim() || '';

    filteredTasks = allTasks.filter(t => {
        if (search) {
            const hay = `${t.title || ''} ${t.description || ''}`.toLowerCase();
            if (!hay.includes(search)) return false;
        }
        if (projectId && String(t.project_id) !== projectId) return false;
        if (status && t.status?.name !== status) return false;
        if (priority && t.priority !== priority) return false;
        if (assignee && !(t.assignee_emails || [t.assignee_email]).includes(assignee)) return false;
        if (listName && t.list_name !== listName) return false;
        if (closed !== '' && closed !== null && String(Number(t.is_closed)) !== closed) return false;
        if (tags) {
            const taskTags = (t.tags || '').toLowerCase();
            const need = tags.split(',').map(s => s.trim()).filter(Boolean);
            if (need.some(tag => !taskTags.includes(tag))) return false;
        }
        return true;
    });

    sortTasks(null);
    if (ganttView) renderGantt();
}

function resetFilters() {
    document.getElementById('filter-search').value = '';
    if (document.getElementById('filter-project')) document.getElementById('filter-project').value = '';
    document.getElementById('filter-status').value = '';
    document.getElementById('filter-priority').value = '';
    document.getElementById('filter-assignee').value = '';
    document.getElementById('filter-list').value = '';
    document.getElementById('filter-closed').value = '';
    document.getElementById('filter-tags').value = '';
    applyFilters();
}

function sortTasks(column) {
    if (column) {
        if (sortColumn === column) {
            sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            sortColumn = column;
            sortDirection = 'asc';
        }
    }

    filteredTasks.sort((a, b) => {
        let va = getSortValue(a, sortColumn);
        let vb = getSortValue(b, sortColumn);
        if (va === null || va === undefined) va = '';
        if (vb === null || vb === undefined) vb = '';

        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();

        if (va < vb) return sortDirection === 'asc' ? -1 : 1;
        if (va > vb) return sortDirection === 'asc' ? 1 : -1;
        return 0;
    });

    renderTable();
}

function getSortValue(task, column) {
    switch (column) {
        case 'id': return task.id;
        case 'project_name': return projectsMap[task.project_id] || '';
        case 'title': return task.title || '';
        case 'status_name': return task.status?.name || '';
        case 'priority': return task.priority || '';
        case 'assignee_name': return formatAssignees(task, false);
        case 'start_date': return task.start_date || '';
        case 'due_date': return task.due_date || '';
        case 'list_name': return task.list_name || '';
        case 'created_at': return task.created_at || '';
        case 'is_closed': return task.is_closed ? 1 : 0;
        default: return '';
    }
}

function renderTable() {
    const tbody = document.getElementById('tasks-table-body');
    if (filteredTasks.length === 0) {
        const colspan = IS_GLOBAL ? 15 : 14;
        tbody.innerHTML = `<tr><td colspan="${colspan}" class="text-center text-muted py-4">Нет задач</td></tr>`;
        return;
    }

    tbody.innerHTML = filteredTasks.map(task => {
        const priorityClass = {
            low: 'bg-success',
            medium: 'bg-warning text-dark',
            high: 'bg-danger',
        }[task.priority] || 'bg-secondary';

        const projectCell = IS_GLOBAL
            ? `<td class="d-none d-sm-table-cell">${escapeHtml(projectsMap[task.project_id] || `Проект #${task.project_id}`)}</td>`
            : '';

        const tags = (task.tags || '').split(',').map(t => t.trim()).filter(Boolean).map(t =>
            `<span class="badge bg-light text-dark border me-1">${escapeHtml(t)}</span>`
        ).join('');

        const kanbanUrl = `/projects/${task.project_id}/kanban?task=${task.id}`;

        return `
            <tr class="${task.is_closed ? 'table-secondary' : ''}${highlightedTaskId === task.id ? ' task-row-highlighted' : ''}" data-task-id="${task.id}" style="cursor:pointer;">
                <td class="text-center">
                    <input class="form-check-input" type="checkbox" ${selectedTaskIds.has(task.id) ? 'checked' : ''} data-action="select-task" data-task-id="${task.id}" title="Выбрать задачу">
                </td>
                <td>${task.id}</td>
                ${projectCell}
                <td title="${escapeHtml(task.title || '')}">${escapeHtml(task.title || '')}</td>
                <td class="d-none d-md-table-cell description-cell" title="${escapeHtml(task.description || '')}">${escapeHtml(task.description || '')}</td>
                <td>${escapeHtml(task.status?.name || '')}</td>
                <td><span class="badge ${priorityClass}">${priorityLabel(task.priority)}</span></td>
                <td class="d-none d-sm-table-cell">${formatAssignees(task)}</td>
                <td class="d-none d-sm-table-cell">${task.start_date ? formatDateTime(task.start_date) : '—'}</td>
                <td class="d-none d-sm-table-cell">${task.due_date ? formatDateTime(task.due_date) : '—'}</td>
                <td class="d-none d-lg-table-cell">${tags || '—'}</td>
                <td class="d-none d-sm-table-cell">${escapeHtml(task.list_name || '—')}</td>
                <td class="d-none d-lg-table-cell">${formatDateTime(task.created_at)}</td>
                <td class="d-none d-sm-table-cell">${task.is_closed ? '<i class="bi bi-check-circle text-success"></i>' : '—'}</td>
                <td class="actions-cell">
                    <a href="${kanbanUrl}" class="btn btn-sm btn-outline-brown" title="Открыть в kanban"><i class="bi bi-kanban"></i></a>
                    <button class="btn btn-sm btn-outline-secondary" onclick="copyTaskLink(${task.project_id}, ${task.id})" title="Копировать ссылку"><i class="bi bi-link-45deg"></i></button>
                    <button class="btn btn-sm btn-outline-success" onclick="exportSingleTask(${task.project_id}, ${task.id})" title="Экспорт задачи"><i class="bi bi-download"></i></button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteTask(${task.id}, ${task.project_id})" title="Удалить задачу"><i class="bi bi-trash"></i></button>
                </td>
            </tr>
        `;
    }).join('');

    setupTopScroll();
    updateSelectionToolbar();
}

// ═══════════════════════════════════════════════════
// ПРОСМОТР/РЕДАКТИРОВАНИЕ ЗАДАЧИ В СПИСКЕ
// ═══════════════════════════════════════════════════

async function openTaskViewModal(taskId) {
    try {
        const task = await api(`${API_BASE}/tasks/${taskId}`);
        currentTaskId = task.id;
        currentTaskProjectId = task.project_id;
        taskAttachments = {};

        document.getElementById('task-id').value = task.id;
        document.getElementById('task-project-id').value = task.project_id;
        document.getElementById('task-id-display').textContent = task.id;
        document.getElementById('task-project-display').textContent = escapeHtml(projectsMap[task.project_id] || `Проект #${task.project_id}`);

        document.getElementById('task-title').value = task.title || '';
        document.getElementById('task-description').value = task.description || '';
        document.getElementById('task-priority').value = task.priority || 'medium';
        document.getElementById('task-is-closed').checked = !!task.is_closed;
        const startDateInput = document.getElementById('task-start-date');
        startDateInput.value = isoToDatetimeLocal(task.start_date);
        startDateInput.dispatchEvent(new Event('change'));
        const dueDateInput = document.getElementById('task-due-date');
        dueDateInput.value = isoToDatetimeLocal(task.due_date);
        dueDateInput.dispatchEvent(new Event('change'));
        document.getElementById('task-tags').value = task.tags || '';
        document.getElementById('task-list-name').value = task.list_name || '';
        document.getElementById('task-result').value = task.result || '';
        setTaskResultVisible(false);

        populateAssigneeSelect();
        setSelectedAssigneeEmails(task.assignee_emails || [task.assignee_email].filter(Boolean));

        const statuses = await loadTaskStatuses(task.project_id);
        populateSelect('task-status-id', statuses.map(s => ({ value: s.id, label: s.name })), 'Выберите статус');
        document.getElementById('task-status-id').value = task.status_id;

        document.getElementById('task-delete-btn').style.display = 'inline-block';
        document.getElementById('task-export-btn').style.display = 'inline-block';
        document.getElementById('task-add-attachment-btn').disabled = false;
        hideAttachmentForm();
        renderTaskAttachments(task.attachments || []);

        bootstrap.Modal.getOrCreateInstance(document.getElementById('taskViewModal')).show();
    } catch (e) {
        showToast('Ошибка открытия задачи: ' + e.message, 'danger');
    }
}

async function loadTaskStatuses(projectId) {
    if (taskStatusCache[projectId]) return taskStatusCache[projectId];
    try {
        const statuses = await api(`${API_BASE}/projects/${projectId}/task-statuses`);
        taskStatusCache[projectId] = statuses || [];
        return taskStatusCache[projectId];
    } catch (e) {
        console.error('Failed to load statuses:', e);
        return [];
    }
}

function populateAssigneeSelect() {
    const list = document.getElementById('task-assignee-dropdown-list');
    if (!list) return;
    const assignees = filterOptions.assignees || [];
    if (assignees.length === 0) {
        list.innerHTML = '<li><span class="dropdown-item-text text-muted">Нет ответственных</span></li>';
        return;
    }
    list.innerHTML = assignees.map(a => `
        <li>
            <div class="dropdown-item">
                <div class="form-check">
                    <input class="form-check-input task-assignee-checkbox" type="checkbox" value="${escapeHtml(a.email)}" id="task-assignee-${escapeHtml(a.email)}" onchange="updateAssigneeDropdownButton()">
                    <label class="form-check-label" for="task-assignee-${escapeHtml(a.email)}">${escapeHtml(a.name)}</label>
                </div>
            </div>
        </li>
    `).join('');
}

function getSelectedAssigneeEmails() {
    const checkboxes = document.querySelectorAll('.task-assignee-checkbox:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

function setSelectedAssigneeEmails(emails) {
    const set = new Set(emails || []);
    document.querySelectorAll('.task-assignee-checkbox').forEach(cb => {
        cb.checked = set.has(cb.value);
    });
    updateAssigneeDropdownButton();
}

function updateAssigneeDropdownButton() {
    const btn = document.getElementById('task-assignee-dropdown-btn');
    if (!btn) return;
    const selected = getSelectedAssigneeEmails();
    if (selected.length === 0) {
        btn.textContent = 'Не назначены';
        return;
    }
    const labels = selected.map(email => assigneesMap[email] || email);
    btn.textContent = labels.join(', ');
}

function assignMeToTask() {
    if (!currentUserEmail) return;
    const existing = getSelectedAssigneeEmails();
    if (!existing.includes(currentUserEmail)) {
        setSelectedAssigneeEmails([...existing, currentUserEmail]);
    }
}

function formatAssignees(task, escape = true) {
    const emails = task.assignee_emails || [task.assignee_email].filter(Boolean);
    if (emails.length === 0) return '—';
    const names = emails.map(email => assigneesMap[email] || email);
    return escape ? escapeHtml(names.join(', ')) : names.join(', ');
}

function setTaskResultVisible(visible) {
    const wrap = document.getElementById('task-result-wrap');
    const btn = document.getElementById('task-result-toggle');
    if (!wrap) return;
    wrap.style.display = visible ? 'block' : 'none';
    if (btn) btn.classList.toggle('active', visible);
    const ta = wrap.querySelector('textarea.expandable-textarea');
    if (visible) {
        requestAnimationFrame(() => autoExpandTextarea(ta));
    } else {
        collapseTextarea(ta);
    }
}

function toggleTaskResultField() {
    const wrap = document.getElementById('task-result-wrap');
    if (!wrap) return;
    setTaskResultVisible(wrap.style.display === 'none');
}

async function saveTaskFromModal() {
    if (!currentTaskId || !currentTaskProjectId) return;

    const statusSelect = document.getElementById('task-status-id');
    const statusId = statusSelect.value ? parseInt(statusSelect.value, 10) : null;
    if (!statusId) {
        showToast('Выберите статус', 'warning');
        return;
    }

    const dueInput = document.getElementById('task-due-date').value;
    const startInput = document.getElementById('task-start-date').value;
    const payload = {
        title: document.getElementById('task-title').value.trim() || null,
        description: document.getElementById('task-description').value.trim() || null,
        status_id: statusId,
        priority: document.getElementById('task-priority').value,
        is_closed: document.getElementById('task-is-closed').checked,
        start_date: startInput ? new Date(startInput).toISOString() : null,
        due_date: dueInput ? new Date(dueInput).toISOString() : null,
        assignee_emails: getSelectedAssigneeEmails(),
        tags: document.getElementById('task-tags').value.trim() || null,
        list_name: document.getElementById('task-list-name').value.trim() || null,
        result: document.getElementById('task-result').value.trim() || null,
    };

    try {
        const updated = await api(`${API_BASE}/projects/${currentTaskProjectId}/tasks/${currentTaskId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        const idx = allTasks.findIndex(t => t.id === updated.id);
        if (idx !== -1) {
            allTasks[idx] = updated;
        }
        applyFilters();
        bootstrap.Modal.getInstance(document.getElementById('taskViewModal'))?.hide();
        showToast('Задача сохранена', 'success');
    } catch (e) {
        showToast('Ошибка сохранения: ' + e.message, 'danger');
    }
}

async function exportCurrentTask() {
    if (!currentTaskId || !currentTaskProjectId) return;
    try {
        const task = await api(`${API_BASE}/projects/${currentTaskProjectId}/tasks/${currentTaskId}/export`);
        const blob = new Blob([JSON.stringify(task, null, 2)], { type: 'application/json' });
        const filename = `task_${currentTaskId}_${formatNowMoscowForFilename()}.json`;
        downloadBlob(blob, filename);
        showToast('Задача экспортирована', 'success');
    } catch (e) {
        showToast('Ошибка экспорта: ' + e.message, 'danger');
    }
}

async function deleteTaskFromModal() {
    if (!currentTaskId || !currentTaskProjectId) return;
    if (!(await showConfirm('Удалить задачу?'))) return;

    try {
        await api(`${API_BASE}/projects/${currentTaskProjectId}/tasks/${currentTaskId}`, { method: 'DELETE' });
        allTasks = allTasks.filter(t => t.id !== currentTaskId);
        selectedTaskIds.delete(currentTaskId);
        applyFilters();
        bootstrap.Modal.getInstance(document.getElementById('taskViewModal'))?.hide();
        showToast('Задача удалена', 'success');
    } catch (e) {
        showToast('Ошибка удаления: ' + e.message, 'danger');
    }
}

// ── Ответственные ──

function openAssigneeModal() {
    const modalEl = document.getElementById('assigneeModal');
    const form = document.getElementById('assignee-form');
    if (form) form.reset();
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

async function saveAssignee() {
    const form = document.getElementById('assignee-form');
    if (!form.name.value.trim() || !form.email.value.trim()) {
        showToast('Введите имя и email', 'warning');
        return;
    }

    try {
        await api(`${API_BASE}/assignees`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: form.name.value.trim(), email: form.email.value.trim() }),
        });
        bootstrap.Modal.getInstance(document.getElementById('assigneeModal'))?.hide();
        showToast('Ответственный добавлен', 'success');
        await loadFilters();
        populateAssigneeSelect();
    } catch (e) {
        showToast('Ошибка добавления ответственного: ' + e.message, 'danger');
    }
}

// ── Вложения ──

function showAttachmentForm(type) {
    if (!currentTaskId || !currentTaskProjectId) {
        showToast('Сначала сохраните задачу', 'warning');
        return;
    }
    const form = document.getElementById('task-attachment-form');
    const typeInput = document.getElementById('attachment-form-type');
    const titleInput = document.getElementById('attachment-form-title');
    const urlWrap = document.getElementById('attachment-form-url-wrap');
    const urlInput = document.getElementById('attachment-form-url');
    const fileWrap = document.getElementById('attachment-form-file-wrap');
    const fileInput = document.getElementById('attachment-form-file');

    if (!form || !typeInput) return;

    typeInput.value = type;
    titleInput.value = '';
    urlInput.value = '';
    fileInput.value = '';

    if (type === 'file') {
        urlWrap.style.display = 'none';
        fileWrap.style.display = 'block';
    } else {
        urlWrap.style.display = 'block';
        fileWrap.style.display = 'none';
        urlInput.placeholder = type === 'git' ? 'URL репозитория' : 'URL';
    }
    form.style.display = 'block';
}

function hideAttachmentForm() {
    const form = document.getElementById('task-attachment-form');
    if (form) form.style.display = 'none';
}

async function submitAttachmentForm() {
    if (!currentTaskId || !currentTaskProjectId) return;

    const type = document.getElementById('attachment-form-type').value;
    const title = document.getElementById('attachment-form-title').value.trim() || null;
    const url = document.getElementById('attachment-form-url').value.trim();

    if (type !== 'file' && !url) {
        showToast('Введите URL', 'warning');
        return;
    }

    try {
        await api(`${API_BASE}/projects/${currentTaskProjectId}/tasks/${currentTaskId}/attachments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ attachment_type: type, title, url }),
        });
        hideAttachmentForm();
        await reloadCurrentTask();
    } catch (e) {
        showToast('Ошибка добавления вложения: ' + e.message, 'danger');
    }
}

async function submitAttachmentFile(input) {
    if (!currentTaskId || !currentTaskProjectId) {
        showToast('Сначала сохраните задачу', 'warning');
        input.value = '';
        return;
    }
    const file = input.files[0];
    if (!file) return;
    input.value = '';

    const formData = new FormData();
    formData.append('file', file);

    try {
        await api(`${API_BASE}/projects/${currentTaskProjectId}/tasks/${currentTaskId}/attachments/upload`, {
            method: 'POST',
            body: formData,
        });
        hideAttachmentForm();
        await reloadCurrentTask();
    } catch (e) {
        showToast('Ошибка загрузки файла: ' + e.message, 'danger');
    }
}

function renderTaskAttachments(attachments) {
    const container = document.getElementById('task-attachments-list');
    if (!container) return;

    if (!currentTaskId || !currentTaskProjectId) {
        container.innerHTML = '<span class="text-muted small">Сохраните задачу, чтобы добавить вложения</span>';
        return;
    }

    if (!attachments || attachments.length === 0) {
        container.innerHTML = '<span class="text-muted small">Нет вложений</span>';
        return;
    }

    attachments.forEach(a => {
        taskAttachments[a.id] = { ...a, project_id: currentTaskProjectId, task_id: currentTaskId };
        window.kanbanAttachments[a.id] = taskAttachments[a.id];
    });

    container.innerHTML = attachments.map(a => {
        const cat = detectCategoryFromAttachment(a);
        const icon = getCategoryIcon(cat);
        const display = escapeHtml(a.title || a.url || a.file_path || 'Вложение');
        let link = '';
        let actionBtn = '';
        if (a.attachment_type === 'link' || a.attachment_type === 'git') {
            link = `<a href="${escapeHtml(a.url || '#')}" target="_blank" rel="noopener" class="text-decoration-none">${display}</a>`;
            actionBtn = `
                <a href="${escapeHtml(a.url || '#')}" target="_blank" class="btn btn-sm btn-outline-brown" title="Открыть" onclick="event.stopPropagation()"><i class="bi bi-box-arrow-up-right"></i></a>
                <button type="button" class="btn btn-sm btn-success" onclick="event.stopPropagation(); copyTaskAttachmentById(${a.id})" title="Копировать ссылку"><i class="bi bi-link-45deg"></i></button>
            `;
        } else if (a.attachment_type === 'file') {
            link = `<span class="text-decoration-none" style="cursor:pointer" onclick="event.stopPropagation(); openTaskAttachmentPreview(${a.id})">${display}</span>`;
            actionBtn = `
                <button type="button" class="btn btn-sm btn-outline-primary" onclick="event.stopPropagation(); openTaskAttachmentInAlexandrite(${a.id})" title="Открыть в Alexandrite"><i class="bi bi-gem"></i></button>
                <button type="button" class="btn btn-sm btn-outline-brown" onclick="event.stopPropagation(); openTaskAttachmentPreview(${a.id})" title="Предпросмотр"><i class="bi bi-eye"></i></button>
                <a href="/uploads/${encodeURIComponent(a.file_path || '')}" class="btn btn-sm btn-outline-success" title="Скачать" download onclick="event.stopPropagation()"><i class="bi bi-download"></i></a>
            `;
        } else {
            link = `<span>${display}</span>`;
        }
        return `
            <div class="d-flex align-items-center justify-content-between gap-2 p-2 border rounded mb-1">
                <div class="text-truncate">
                    <i class="bi ${icon} me-1"></i> ${link}
                </div>
                <div class="d-flex gap-1 align-items-center">
                    ${actionBtn}
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="event.stopPropagation(); editTaskAttachment(${a.id})" title="Изменить"><i class="bi bi-pencil"></i></button>
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="event.stopPropagation(); deleteTaskAttachment(${a.id})" title="Удалить"><i class="bi bi-trash"></i></button>
                </div>
            </div>
        `;
    }).join('');
}

function editTaskAttachment(attachmentId) {
    const attachment = taskAttachments[attachmentId];
    if (!attachment) return;
    editingTaskAttachmentId = attachmentId;
    const modalEl = document.getElementById('editTaskAttachmentModal');
    const modalTitle = document.getElementById('edit-task-attachment-modal-title');
    const titleInput = document.getElementById('edit-task-attachment-title');
    const urlWrap = document.getElementById('edit-task-attachment-url-wrap');
    const urlInput = document.getElementById('edit-task-attachment-url');
    const fileWrap = document.getElementById('edit-task-attachment-file-wrap');
    const fileInput = document.getElementById('edit-task-attachment-file');

    titleInput.value = attachment.title || '';
    fileInput.value = '';
    if (attachment.attachment_type === 'link' || attachment.attachment_type === 'git') {
        modalTitle.textContent = attachment.attachment_type === 'git' ? 'Редактировать git-репозиторий' : 'Редактировать ссылку';
        urlWrap.style.display = 'block';
        urlInput.value = attachment.url || '';
        fileWrap.style.display = 'none';
    } else {
        modalTitle.textContent = 'Редактировать файл';
        urlWrap.style.display = 'none';
        urlInput.value = '';
        fileWrap.style.display = 'block';
    }
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

async function saveTaskAttachmentEdit() {
    if (!editingTaskAttachmentId || !currentTaskId || !currentTaskProjectId) return;
    const attachment = taskAttachments[editingTaskAttachmentId];
    if (!attachment) return;

    const titleInput = document.getElementById('edit-task-attachment-title');
    const fileInput = document.getElementById('edit-task-attachment-file');
    const formData = new FormData();
    const title = titleInput.value.trim();
    if (title) formData.append('title', title);
    if (attachment.attachment_type === 'link' || attachment.attachment_type === 'git') {
        const url = document.getElementById('edit-task-attachment-url').value.trim();
        if (url) formData.append('url', url);
    } else if (fileInput.files && fileInput.files[0]) {
        formData.append('file', fileInput.files[0]);
    }

    try {
        await api(`${API_BASE}/projects/${currentTaskProjectId}/tasks/${currentTaskId}/attachments/${editingTaskAttachmentId}`, {
            method: 'PATCH',
            body: formData,
        });
        bootstrap.Modal.getInstance(document.getElementById('editTaskAttachmentModal'))?.hide();
        await reloadCurrentTask();
    } catch (e) {
        showToast('Ошибка изменения вложения: ' + e.message, 'danger');
    }
}

async function deleteTaskAttachment(attachmentId) {
    if (!currentTaskId || !currentTaskProjectId) return;
    if (!(await showConfirm('Удалить вложение?'))) return;

    try {
        await api(`${API_BASE}/projects/${currentTaskProjectId}/tasks/${currentTaskId}/attachments/${attachmentId}`, {
            method: 'DELETE',
        });
        await reloadCurrentTask();
    } catch (e) {
        showToast('Ошибка удаления вложения: ' + e.message, 'danger');
    }
}

async function reloadCurrentTask() {
    if (!currentTaskId) return;
    try {
        const task = await api(`${API_BASE}/tasks/${currentTaskId}`);
        renderTaskAttachments(task.attachments || []);
        const idx = allTasks.findIndex(t => t.id === currentTaskId);
        if (idx !== -1) {
            allTasks[idx] = task;
        }
        applyFilters();
    } catch (e) {
        console.error('Failed to reload task:', e);
    }
}

function copyTaskAttachmentById(attachmentId) {
    const attachment = taskAttachments[attachmentId];
    if (!attachment || !attachment.url) return showToast('Ссылка пуста', 'warning');
    copyTextToClipboard(attachment.url);
    showToast('Ссылка скопирована в буфер обмена', 'success');
}

function isoToDatetimeLocal(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return '';
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 16);
}

function copyTaskLink(projectId, taskId) {
    const url = `${window.location.origin}/projects/${projectId}/kanban?task=${taskId}`;
    copyTextToClipboard(url);
    showToast('Ссылка скопирована', 'success');
}

async function exportSingleTask(projectId, taskId) {
    try {
        const task = await api(`${API_BASE}/projects/${projectId}/tasks/${taskId}/export`);
        const blob = new Blob([JSON.stringify(task, null, 2)], { type: 'application/json' });
        const filename = `task_${taskId}_${formatNowMoscowForFilename()}.json`;
        downloadBlob(blob, filename);
        showToast('Задача экспортирована', 'success');
    } catch (e) {
        showToast('Ошибка экспорта: ' + e.message, 'danger');
    }
}

async function importSingleTask() {
    const input = document.getElementById('import-single-file');
    const file = input?.files[0];
    if (!file) {
        showToast('Выберите JSON-файл задачи', 'warning');
        return;
    }

    let task;
    try {
        const text = await file.text();
        task = JSON.parse(text);
    } catch (e) {
        showToast('Некорректный JSON-файл: ' + e.message, 'danger');
        return;
    }

    const projectId = task.project_id || getImportProjectId() || PROJECT_ID;
    if (!projectId) {
        showToast('Не удалось определить проект для импорта', 'warning');
        return;
    }
    try {
        const result = await api(`${API_BASE}/projects/${projectId}/tasks/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(task),
        });
        resetImportSingleFile();
        bootstrap.Modal.getOrCreateInstance(document.getElementById('taskImportModal')).hide();
        showToast(`Задача импортирована #${result.id}`, 'success');
        await loadTasks();
        await loadFilters();
    } catch (e) {
        showToast('Ошибка импорта: ' + e.message, 'danger');
    }
}

function resetImportSingleFile() {
    const input = document.getElementById('import-single-file');
    if (input) {
        const wrapper = input.parentElement;
        const newInput = document.createElement('input');
        newInput.type = 'file';
        newInput.id = 'import-single-file';
        newInput.className = input.className;
        newInput.accept = input.accept;
        wrapper.replaceChild(newInput, input);
    }
}

async function deleteTask(taskId, projectId) {
    try {
        await api(`${API_BASE}/projects/${projectId}/tasks/${taskId}`, { method: 'DELETE' });
        allTasks = allTasks.filter(t => t.id !== taskId);
        selectedTaskIds.delete(taskId);
        applyFilters();
        showToast('Задача удалена', 'success');
    } catch (e) {
        showToast('Ошибка удаления задачи: ' + e.message, 'danger');
    }
}

function toggleTaskSelected(taskId) {
    if (selectedTaskIds.has(taskId)) {
        selectedTaskIds.delete(taskId);
    } else {
        selectedTaskIds.add(taskId);
    }
    applyFilters();
}

function toggleSelectAll(selectAll) {
    if (selectAll) {
        filteredTasks.forEach(t => selectedTaskIds.add(t.id));
    } else {
        filteredTasks.forEach(t => selectedTaskIds.delete(t.id));
    }
    applyFilters();
}

async function deleteSelectedTasks() {
    if (selectedTaskIds.size === 0) return;
    if (!(await showConfirm(`Удалить ${selectedTaskIds.size} выбранных задач?`))) return;

    const ids = Array.from(selectedTaskIds);
    const toDelete = allTasks.filter(t => selectedTaskIds.has(t.id));
    let deleted = 0;
    let failed = 0;

    for (const task of toDelete) {
        try {
            await api(`${API_BASE}/projects/${task.project_id}/tasks/${task.id}`, { method: 'DELETE' });
            allTasks = allTasks.filter(t => t.id !== task.id);
            selectedTaskIds.delete(task.id);
            deleted++;
        } catch (e) {
            console.error(`Failed to delete task ${task.id}:`, e);
            failed++;
        }
    }

    applyFilters();
    if (failed === 0) {
        showToast(`Удалено задач: ${deleted}`, 'success');
    } else {
        showToast(`Удалено: ${deleted}, не удалось: ${failed}`, 'danger');
    }
}

function updateSelectionToolbar() {
    const countEl = document.getElementById('selected-tasks-count');
    const groupBtn = document.getElementById('group-process-btn');
    const selectAllCheckbox = document.getElementById('select-all-tasks');
    if (!countEl || !groupBtn || !selectAllCheckbox) return;

    const visibleIds = filteredTasks.map(t => t.id);
    const selectedVisible = visibleIds.filter(id => selectedTaskIds.has(id));
    const allVisibleSelected = visibleIds.length > 0 && selectedVisible.length === visibleIds.length;

    countEl.textContent = selectedTaskIds.size > 0 ? `Выбрано: ${selectedTaskIds.size}` : '';
    selectAllCheckbox.checked = allVisibleSelected;
}


function getBulkAttachmentArray(prefix) {
    return prefix === 'import-bulk' ? importBulkAttachments : groupProcessAttachments;
}

function initBulkAssigneeList(prefix) {
    const list = document.getElementById(`${prefix}-assignee-list`);
    const btn = document.getElementById(`${prefix}-assignee-btn`);
    if (!list) return;
    const assignees = filterOptions.assignees || [];
    if (assignees.length === 0) {
        list.innerHTML = '<li><span class="dropdown-item-text text-muted">Нет ответственных</span></li>';
    } else {
        list.innerHTML = assignees.map(a => `
            <li>
                <div class="dropdown-item">
                    <div class="form-check">
                        <input class="form-check-input group-assignee-checkbox" type="checkbox" value="${escapeHtml(a.email)}" id="${prefix}-assignee-${escapeHtml(a.email)}" data-prefix="${prefix}" onchange="updateBulkAssigneeButton('${prefix}')">
                        <label class="form-check-label" for="${prefix}-assignee-${escapeHtml(a.email)}">${escapeHtml(a.name)}</label>
                    </div>
                </div>
            </li>
        `).join('');
    }
    if (btn) btn.textContent = '— не менять —';
}

function getBulkAssigneeEmails(prefix) {
    return Array.from(document.querySelectorAll(`#${prefix}-assignee-list .group-assignee-checkbox:checked`)).map(cb => cb.value);
}

function setBulkAssigneeEmails(prefix, emails) {
    const set = new Set(emails || []);
    document.querySelectorAll(`#${prefix}-assignee-list .group-assignee-checkbox`).forEach(cb => { cb.checked = set.has(cb.value); });
    updateBulkAssigneeButton(prefix);
}

function updateBulkAssigneeButton(prefix) {
    const btn = document.getElementById(`${prefix}-assignee-btn`);
    if (!btn) return;
    const emails = getBulkAssigneeEmails(prefix);
    if (emails.length === 0) {
        btn.textContent = '— не менять —';
        return;
    }
    const labels = emails.map(email => assigneesMap[email] || email);
    btn.textContent = labels.join(', ');
}

function resetBulkForm(prefix) {
    const priority = document.getElementById(`${prefix}-priority`);
    if (priority) priority.value = '';

    const startDate = document.getElementById(`${prefix}-start-date`);
    if (startDate) {
        startDate.value = '';
        startDate.dispatchEvent(new Event('change'));
    }
    const startDateDisplay = document.getElementById(`${prefix}-start-date-display`);
    if (startDateDisplay) startDateDisplay.value = '';

    const dueDate = document.getElementById(`${prefix}-due-date`);
    if (dueDate) {
        dueDate.value = '';
        dueDate.dispatchEvent(new Event('change'));
    }
    const dueDateDisplay = document.getElementById(`${prefix}-due-date-display`);
    if (dueDateDisplay) dueDateDisplay.value = '';

    const tags = document.getElementById(`${prefix}-tags`);
    if (tags) tags.value = '';

    const listName = document.getElementById(`${prefix}-list-name`);
    if (listName) listName.value = '';

    const isClosed = document.getElementById(`${prefix}-is-closed`);
    if (isClosed) isClosed.checked = false;

    const status = document.getElementById(`${prefix}-status`);
    if (status) status.value = '';

    setBulkAssigneeEmails(prefix, []);

    const arr = getBulkAttachmentArray(prefix);
    arr.length = 0;
    hideGroupAttachmentForm(prefix);
    renderGroupAttachmentsList(prefix);
}

function openGroupProcessModal() {
    if (selectedTaskIds.size === 0) {
        showToast('Выберите задачи', 'warning');
        return;
    }

    groupProcessAttachments = [];
    groupProcessSelectedProjectId = null;
    resetBulkForm('group-process');
    document.getElementById('group-process-task-count').textContent = selectedTaskIds.size;

    const statusSelect = document.getElementById('group-process-status');
    const statusWrap = statusSelect?.closest('.col-md-4');
    if (statusWrap) statusWrap.style.display = 'none';

    const selectedTasks = allTasks.filter(t => selectedTaskIds.has(t.id));
    const projectIds = new Set(selectedTasks.map(t => t.project_id));

    if (!IS_GLOBAL) {
        groupProcessSelectedProjectId = PROJECT_ID;
        if (statusWrap) statusWrap.style.display = 'block';
        loadTaskStatuses(PROJECT_ID).then(statuses => {
            populateSelect('group-process-status', statuses.map(s => ({ value: s.id, label: s.name })), '— не менять —');
        });
    } else if (projectIds.size === 1) {
        const pid = Array.from(projectIds)[0];
        groupProcessSelectedProjectId = pid;
        if (statusWrap) statusWrap.style.display = 'block';
        loadTaskStatuses(pid).then(statuses => {
            populateSelect('group-process-status', statuses.map(s => ({ value: s.id, label: s.name })), '— не менять —');
        });
    }

    initBulkAssigneeList('group-process');
    bootstrap.Modal.getOrCreateInstance(document.getElementById('groupProcessModal')).show();
}

async function applyGroupProcess() {
    if (selectedTaskIds.size === 0) return;

    const taskIds = Array.from(selectedTaskIds);
    const update = {};

    const statusSelect = document.getElementById('group-process-status');
    if (statusSelect && statusSelect.value) {
        update.status_id = parseInt(statusSelect.value, 10);
    }

    const priority = document.getElementById('group-process-priority').value;
    if (priority) update.priority = priority;

    const dueDate = document.getElementById('group-process-due-date').value;
    if (dueDate) update.due_date = new Date(dueDate).toISOString();

    const startDate = document.getElementById('group-process-start-date').value;
    if (startDate) update.start_date = new Date(startDate).toISOString();

    const assigneeEmails = getBulkAssigneeEmails('group-process');
    if (assigneeEmails.length > 0) update.assignee_emails = assigneeEmails;

    const tags = document.getElementById('group-process-tags').value.trim();
    if (tags) update.tags = tags;

    const listName = document.getElementById('group-process-list-name').value.trim();
    if (listName) update.list_name = listName;

    const isClosed = document.getElementById('group-process-is-closed');
    if (isClosed && isClosed.checked) update.is_closed = true;

    const url = IS_GLOBAL
        ? `${API_BASE}/tasks/bulk`
        : `${API_BASE}/projects/${PROJECT_ID}/tasks/bulk`;

    try {
        await api(url, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_ids: taskIds, update }),
        });

        if (groupProcessAttachments.length > 0) {
            const attachUrl = IS_GLOBAL
                ? `${API_BASE}/tasks/attachments/bulk`
                : `${API_BASE}/projects/${PROJECT_ID}/tasks/attachments/bulk`;
            await api(attachUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_ids: taskIds, attachments: groupProcessAttachments }),
            });
        }

        bootstrap.Modal.getOrCreateInstance(document.getElementById('groupProcessModal')).hide();
        showToast('Групповая обработка выполнена', 'success');
        await loadTasks();
        await loadFilters();
    } catch (e) {
        showToast('Ошибка групповой обработки: ' + e.message, 'danger');
    }
}

async function deleteGroupTasks() {
    if (selectedTaskIds.size === 0) return;
    await deleteSelectedTasks();
    bootstrap.Modal.getInstance(document.getElementById('groupProcessModal'))?.hide();
}

function showGroupAttachmentForm(prefix, type) {
    const form = document.getElementById(`${prefix}-attachment-form`);
    const typeInput = document.getElementById(`${prefix}-attachment-type`);
    const titleInput = document.getElementById(`${prefix}-attachment-title`);
    const urlInput = document.getElementById(`${prefix}-attachment-url`);
    const urlWrap = document.getElementById(`${prefix}-attachment-url-wrap`);

    typeInput.value = type;
    titleInput.value = '';
    urlInput.value = '';
    urlWrap.style.display = type === 'file' ? 'none' : 'block';
    urlInput.placeholder = type === 'git' ? 'URL репозитория' : 'URL';
    form.style.display = 'block';
}

function hideGroupAttachmentForm(prefix) {
    const form = document.getElementById(`${prefix}-attachment-form`);
    if (form) form.style.display = 'none';
}

function submitGroupAttachmentForm(prefix) {
    const type = document.getElementById(`${prefix}-attachment-type`).value;
    const title = document.getElementById(`${prefix}-attachment-title`).value.trim() || null;
    const url = document.getElementById(`${prefix}-attachment-url`).value.trim();

    if (type !== 'file' && !url) {
        showToast('Введите URL', 'warning');
        return;
    }

    getBulkAttachmentArray(prefix).push({ attachment_type: type, title, url });
    hideGroupAttachmentForm(prefix);
    renderGroupAttachmentsList(prefix);
}

async function submitGroupAttachmentFile(prefix, input) {
    const file = input.files[0];
    if (!file) return;
    input.value = '';

    let uploadUrl;
    if (prefix === 'import-bulk') {
        const projectId = getImportProjectId();
        if (!projectId) {
            showToast('Выберите проект для загрузки файла', 'warning');
            return;
        }
        uploadUrl = `${API_BASE}/projects/${projectId}/attachments/upload`;
    } else {
        uploadUrl = IS_GLOBAL
            ? `${API_BASE}/tasks/attachments/upload`
            : `${API_BASE}/projects/${PROJECT_ID}/attachments/upload`;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const attachment = await api(uploadUrl, {
            method: 'POST',
            body: formData,
        });
        getBulkAttachmentArray(prefix).push({
            attachment_type: 'file',
            title: attachment.title || file.name,
            file_path: attachment.file_path,
        });
        renderGroupAttachmentsList(prefix);
    } catch (e) {
        showToast('Ошибка загрузки файла: ' + e.message, 'danger');
    }
}

function deleteGroupAttachment(prefix, index) {
    getBulkAttachmentArray(prefix).splice(index, 1);
    renderGroupAttachmentsList(prefix);
}

function renderGroupAttachmentsList(prefix) {
    const container = document.getElementById(`${prefix}-attachments-list`);
    if (!container) return;
    const attachments = getBulkAttachmentArray(prefix);
    if (attachments.length === 0) {
        container.innerHTML = '<span class="text-muted small">Нет вложений</span>';
        return;
    }

    container.innerHTML = attachments.map((a, idx) => {
        const icon = a.attachment_type === 'git' ? 'bi-git' : (a.attachment_type === 'link' ? 'bi-link-45deg' : 'bi-file-earmark');
        const display = escapeHtml(a.title || a.url || a.file_path || 'Вложение');
        return `
            <div class="d-flex align-items-center justify-content-between gap-2 p-2 border rounded mb-1">
                <div class="text-truncate">
                    <i class="bi ${icon} me-1"></i> ${display}
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="deleteGroupAttachment('${prefix}', ${idx})" title="Удалить"><i class="bi bi-trash"></i></button>
            </div>
        `;
    }).join('');
}

function toMoscowDateParts(date) {
    // Server returns UTC; Moscow is UTC+3 all year round.
    const moscow = new Date(date.getTime() + 3 * 60 * 60 * 1000);
    const pad = n => String(n).padStart(2, '0');
    return {
        year: moscow.getUTCFullYear(),
        month: pad(moscow.getUTCMonth() + 1),
        day: pad(moscow.getUTCDate()),
        hour: pad(moscow.getUTCHours()),
        minute: pad(moscow.getUTCMinutes()),
    };
}

function formatDateTimeMoscow(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return isoString;
    const p = toMoscowDateParts(date);
    return `${p.day}.${p.month}.${p.year} ${p.hour}:${p.minute}`;
}

function formatNowMoscowForFilename() {
    const p = toMoscowDateParts(new Date());
    return `${p.year}-${p.month}-${p.day}_${p.hour}-${p.minute}`;
}

function exportTasks(format) {
    if (filteredTasks.length === 0) {
        showToast('Нет задач для экспорта', 'warning');
        return;
    }
    const projectName = IS_GLOBAL
        ? undefined
        : (projectsMap[PROJECT_ID] || `Проект #${PROJECT_ID}`);
    const rows = filteredTasks.map(t => ({
        id: t.id,
        project: projectName || (projectsMap[t.project_id] || t.project_id),
        title: t.title,
        description: t.description,
        status: t.status?.name,
        priority: t.priority,
        assignee: formatAssignees(t, false),
        due_date: formatDateTimeMoscow(t.due_date),
        tags: t.tags,
        list_name: t.list_name,
        created_at: formatDateTimeMoscow(t.created_at),
        is_closed: t.is_closed,
    }));

    const timestamp = formatNowMoscowForFilename();
    if (format === 'json') {
        const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
        downloadBlob(blob, `tasks_${timestamp}.json`);
    } else if (format === 'csv') {
        const headers = Object.keys(rows[0]);
        const lines = [headers.join(';')];
        rows.forEach(r => {
            lines.push(headers.map(h => {
                const v = r[h];
                if (v === undefined || v === null) return '';
                const s = String(v).replace(/"/g, '""');
                return s.includes(';') || s.includes('\n') ? `"${s}"` : s;
            }).join(';'));
        });
        const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
        downloadBlob(blob, `tasks_${timestamp}.csv`);
    }
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function openSaveListModal() {
    const container = document.getElementById('save-list-columns');
    if (!container) return;

    const filterValues = {
        project: document.getElementById('filter-project')?.value || '',
        status: document.getElementById('filter-status')?.value || '',
        priority: document.getElementById('filter-priority')?.value || '',
        assignee: document.getElementById('filter-assignee')?.value || '',
        list: document.getElementById('filter-list')?.value || '',
        closed: document.getElementById('filter-closed')?.value || '',
        tags: document.getElementById('filter-tags')?.value.trim() || '',
    };

    const skipKeys = new Set();
    if (filterValues.project) skipKeys.add('project_name');
    if (filterValues.status) skipKeys.add('status_name');
    if (filterValues.priority) skipKeys.add('priority');
    if (filterValues.assignee) skipKeys.add('assignee_name');
    if (filterValues.list) skipKeys.add('list_name');
    if (filterValues.closed !== '') skipKeys.add('is_closed');
    if (filterValues.tags) skipKeys.add('tags');

    container.innerHTML = SAVE_LIST_COLUMNS
        .filter(col => !col.globalOnly || IS_GLOBAL)
        .map((col, idx) => {
            const checked = col.default && !skipKeys.has(col.key);
            return `
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" id="save-list-col-${idx}" value="${escapeHtml(col.key)}" ${checked ? 'checked' : ''} onchange="renderSaveListText()">
                    <label class="form-check-label" for="save-list-col-${idx}">${escapeHtml(col.label)}</label>
                </div>
            `;
        }).join('');

    renderSaveListText();
    bootstrap.Modal.getOrCreateInstance(document.getElementById('saveListModal')).show();
}

function getSaveListColumnValue(task, key) {
    switch (key) {
        case 'id': return String(task.id);
        case 'project_name': return projectsMap[task.project_id] || `Проект #${task.project_id}`;
        case 'title': return task.title ? task.title.trim() : `Заявка #${task.id}`;
        case 'description': return (task.description || '').replace(/\s+/g, ' ').trim();
        case 'status_name': return task.status?.name || '';
        case 'priority': return priorityLabel(task.priority);
        case 'assignee_name': return formatAssignees(task, false);
        case 'start_date': return task.start_date ? formatDateTime(task.start_date) : '—';
        case 'due_date': return task.due_date ? formatDateTime(task.due_date) : '—';
        case 'tags': return task.tags || '—';
        case 'list_name': return task.list_name || '—';
        case 'created_at': return task.created_at ? formatDateTime(task.created_at) : '—';
        case 'is_closed': return task.is_closed ? 'Закрыто' : 'Открыто';
        default: return '';
    }
}

function buildSaveListText(selectedKeys, format) {
    if (selectedKeys.length === 0) {
        return 'Выберите хотя бы одну колонку';
    }
    if (filteredTasks.length === 0) {
        return 'Нет задач для сохранения';
    }

    const selectedColumns = SAVE_LIST_COLUMNS.filter(col => selectedKeys.includes(col.key));

    if (format === 'markdown') {
        const headerLabels = selectedColumns.map(col => col.label);
        const rows = filteredTasks.map(task => {
            return '| ' + selectedColumns.map(col => {
                const v = getSaveListColumnValue(task, col.key);
                return String(v).replace(/\|/g, '\\|').replace(/\n/g, ' ');
            }).join(' | ') + ' |';
        });
        const header = '| ' + headerLabels.join(' | ') + ' |';
        const separator = '|' + headerLabels.map(() => ' --- ').join('|') + '|';
        return [header, separator, ...rows].join('\n');
    }

    if (format === 'oneline') {
        const rows = filteredTasks.map(task => {
            return selectedColumns.map(col => {
                const v = getSaveListColumnValue(task, col.key);
                return String(v).replace(/\n/g, ' ');
            }).join(' | ');
        });
        return rows.join('\n');
    }

    const titleColumn = selectedColumns.find(col => col.key === 'title');
    const detailColumns = selectedColumns.filter(col => col.key !== 'title' && col.key !== 'id');
    const lines = [];

    filteredTasks.forEach((task, idx) => {
        const title = getSaveListColumnValue(task, 'title');
        const titlePart = titleColumn ? (title === `Заявка #${task.id}` ? '' : ' ' + title) : '';

        if (format === 'todo') {
            const isDone = task.is_closed || lastStatusIds[task.project_id] === task.status_id;
            const checkbox = isDone ? '[x]' : '[ ]';
            lines.push(`- ${checkbox} #${task.id}${titlePart}`.trim());
            detailColumns.forEach(col => {
                const v = getSaveListColumnValue(task, col.key);
                lines.push(`  ${col.label}: ${String(v).replace(/\n/g, ' ')}`);
            });
        } else if (format === 'numbered') {
            lines.push(`${idx + 1}. #${task.id}${titlePart}`.trim());
            detailColumns.forEach(col => {
                const v = getSaveListColumnValue(task, col.key);
                lines.push(`   ${col.label}: ${String(v).replace(/\n/g, ' ')}`);
            });
        }
    });

    return lines.join('\n');
}

function renderSaveListText() {
    const textArea = document.getElementById('save-list-text');
    if (!textArea) return;

    const selectedKeys = Array.from(document.querySelectorAll('#save-list-columns input:checked')).map(cb => cb.value);
    const format = document.getElementById('save-list-format')?.value || 'todo';
    textArea.value = buildSaveListText(selectedKeys, format);
}

function copySaveList() {
    const text = document.getElementById('save-list-text').value;
    if (!text || text.startsWith('Выберите') || text.startsWith('Нет задач')) {
        showToast('Нечего копировать', 'warning');
        return;
    }
    copyTextToClipboard(text);
    showToast('Список скопирован', 'success');
}

function downloadSaveList() {
    const text = document.getElementById('save-list-text').value;
    if (!text || text.startsWith('Выберите') || text.startsWith('Нет задач')) {
        showToast('Нечего скачивать', 'warning');
        return;
    }
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const filename = `task_list_${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}.txt`;
    downloadBlob(blob, filename);
}

async function saveListForTelegram() {
    if (filteredTasks.length === 0) {
        showToast('Нет задач для сохранения', 'warning');
        return;
    }
    const selectedKeys = Array.from(document.querySelectorAll('#save-list-columns input:checked')).map(cb => cb.value);
    const format = document.getElementById('save-list-format')?.value || 'todo';
    const config = {
        is_global: IS_GLOBAL,
        project_id: PROJECT_ID || null,
        filters: {
            search: document.getElementById('filter-search')?.value || '',
            status: document.getElementById('filter-status')?.value || '',
            priority: document.getElementById('filter-priority')?.value || '',
            assignee: document.getElementById('filter-assignee')?.value || '',
            list_name: document.getElementById('filter-list')?.value || '',
            closed: document.getElementById('filter-closed')?.value || '',
            tags: document.getElementById('filter-tags')?.value || '',
            project_id: document.getElementById('filter-project')?.value || '',
        },
        format,
        columns: selectedKeys,
        caption: IS_GLOBAL ? '📋 <b>Все задачи</b>' : '📋 <b>Задачи проекта</b>',
    };
    try {
        await api(`${API_BASE}/tasks/telegram-list-config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });
        bootstrap.Modal.getInstance(document.getElementById('saveListModal'))?.hide();
        openTelegramScheduleModal();
    } catch (e) {
        showToast('Ошибка сохранения: ' + e.message, 'danger');
    }
}

function openTelegramScheduleModal() {
    const modalEl = document.getElementById('telegramScheduleModal');
    if (!modalEl) return;
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    const datetimeInput = document.getElementById('telegram-schedule-datetime');
    if (datetimeInput) {
        datetimeInput.value = now.toISOString().slice(0, 16);
        datetimeInput.dispatchEvent(new Event('change'));
    }
    document.querySelectorAll('input[name="telegram-schedule-type"]').forEach(r => {
        r.checked = r.value === 'once';
    });
    updateTelegramScheduleFields();
    const cronInput = document.getElementById('telegram-schedule-cron');
    if (cronInput) cronInput.value = '';
    const intervalSelect = document.getElementById('telegram-schedule-interval');
    if (intervalSelect) intervalSelect.value = 'custom';
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

function updateTelegramScheduleFields() {
    const type = document.querySelector('input[name="telegram-schedule-type"]:checked')?.value || 'once';
    const onceField = document.getElementById('telegram-schedule-once-field');
    const recurringField = document.getElementById('telegram-schedule-recurring-field');
    if (onceField) onceField.style.display = type === 'once' ? 'block' : 'none';
    if (recurringField) recurringField.style.display = type === 'recurring' ? 'block' : 'none';
}

async function scheduleTelegramSend() {
    const type = document.querySelector('input[name="telegram-schedule-type"]:checked')?.value || 'once';
    const payload = { project: 'armory:todo-telegram', schedule_type: type };
    if (type === 'once') {
        const datetime = document.getElementById('telegram-schedule-datetime')?.value;
        if (!datetime) {
            showToast('Укажите дату и время', 'warning');
            return;
        }
        payload.datetime = datetime;
    } else {
        const cron = document.getElementById('telegram-schedule-cron')?.value.trim();
        if (!cron) {
            showToast('Укажите cron-выражение', 'warning');
            return;
        }
        payload.cron = cron;
    }
    try {
        const data = await api(`${API_BASE}/scheduler/schedule`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast(data.message || 'Задача запланирована', 'success');
            bootstrap.Modal.getInstance(document.getElementById('telegramScheduleModal'))?.hide();
        }
    } catch (e) {
        showToast('Ошибка планирования: ' + e.message, 'danger');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('input[name="telegram-schedule-type"]').forEach(radio => {
        radio.addEventListener('change', updateTelegramScheduleFields);
    });
    const intervalSelect = document.getElementById('telegram-schedule-interval');
    const cronInput = document.getElementById('telegram-schedule-cron');
    if (intervalSelect && cronInput) {
        intervalSelect.addEventListener('change', () => {
            if (intervalSelect.value !== 'custom') {
                cronInput.value = intervalSelect.value;
            }
        });
    }
});

function setupTopScroll() {
    const wrapper = document.getElementById('tasks-table-wrapper');
    const top = document.getElementById('table-top-scroll');
    const inner = document.getElementById('table-top-scroll-inner');
    if (!wrapper || !top || !inner) return;

    inner.style.width = wrapper.scrollWidth + 'px';
    const hasScroll = wrapper.scrollWidth > wrapper.clientWidth;
    top.style.display = hasScroll ? 'block' : 'none';

    top.onscroll = () => { wrapper.scrollLeft = top.scrollLeft; };
    wrapper.onscroll = () => { top.scrollLeft = wrapper.scrollLeft; };
}

window.addEventListener('resize', () => {
    setupTopScroll();
    if (ganttView) syncGanttRowHeights();
});

function priorityLabel(priority) {
    return { low: 'Низкий', medium: 'Средний', high: 'Высокий' }[priority] || priority;
}

function formatDateTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return isoString;
    const pad = n => String(n).padStart(2, '0');
    return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// ═══════════════════════════════════════════════════
// ИМПОРТ ЗАДАЧ
// ═══════════════════════════════════════════════════

function resetImportState() {
    importTasksState = [];
    importBulkAttachments = [];
    importNextTempId = 1;
    document.getElementById('import-list-name').value = '';
    document.getElementById('import-todo-text').value = '';
    resetImportSingleFile();
    resetBulkForm('import-bulk');
    if (document.getElementById('import-bulk-project')) document.getElementById('import-bulk-project').value = '';
    renderImportTasksList();
    renderGroupAttachmentsList('import-bulk');
}

function openTaskImportModal() {
    resetImportState();
    loadImportStatuses();
    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('taskImportModal'));
    modal.show();
}

async function loadImportStatuses() {
    const projectId = getImportProjectId();
    if (!projectId) return;
    const statuses = await loadTaskStatuses(projectId);
    populateSelect('import-bulk-status', statuses.map(s => ({ value: s.id, label: s.name })), 'К выполнению');
}

function parseTodoText(text) {
    return text
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0)
        .map(line => line.replace(/^[\-\•\*\+\d+\.\)\]]+\s*/, '').trim())
        .filter(line => line.length > 0);
}

function splitTodoTextIntoTasks() {
    const text = document.getElementById('import-todo-text').value;
    const lines = parseTodoText(text);
    lines.forEach(line => {
        importTasksState.push({
            id: importNextTempId++,
            title: '',
            description: line,
            selected: true,
            project_id: null,
            start_date: null,
            due_date: null,
            priority: null,
            assignee_email: null,
            tags: null,
        });
    });
    renderImportTasksList();
}

function addImportTask() {
    importTasksState.push({
        id: importNextTempId++,
        title: '',
        description: '',
        selected: true,
        project_id: null,
        start_date: null,
        due_date: null,
        priority: null,
        assignee_email: null,
        tags: null,
    });
    renderImportTasksList();
}

function deleteImportTask(id) {
    importTasksState = importTasksState.filter(t => t.id !== id);
    renderImportTasksList();
}

function updateImportTaskTitle(id, title) {
    const task = importTasksState.find(t => t.id === id);
    if (task) task.title = title;
}

function updateImportTaskDescription(id, description) {
    const task = importTasksState.find(t => t.id === id);
    if (task) task.description = description;
}

function toggleImportTaskSelected(id) {
    const task = importTasksState.find(t => t.id === id);
    if (task) task.selected = !task.selected;
}

function toggleAllImportTasks(selected) {
    importTasksState.forEach(t => t.selected = selected);
    renderImportTasksList();
}

function renderImportTasksList() {
    const container = document.getElementById('import-tasks-list');
    if (!container) return;
    if (importTasksState.length === 0) {
        container.innerHTML = '<span class="text-muted small">Нажмите «Разбить на задачи» или добавьте задачи вручную</span>';
        return;
    }

    const allSelected = importTasksState.every(t => t.selected);
    let html = `
        <div class="form-check mb-2">
            <input class="form-check-input" type="checkbox" id="import-task-check-all" ${allSelected ? 'checked' : ''} onchange="toggleAllImportTasks(this.checked)">
            <label class="form-check-label" for="import-task-check-all">Выбрать все</label>
        </div>
    `;

    html += importTasksState.map(t => `
        <div class="import-task-row d-flex align-items-start gap-2 p-2 border rounded mb-1 ${t.selected ? 'import-task-selected' : ''}">
            <input class="form-check-input mt-2" type="checkbox" ${t.selected ? 'checked' : ''} onchange="toggleImportTaskSelected(${t.id}); renderImportTasksList();">
            <div class="flex-grow-1 d-flex flex-column gap-1">
                <input type="text" class="form-control form-control-sm" placeholder="Название (необязательно)" value="${escapeHtml(t.title)}" oninput="updateImportTaskTitle(${t.id}, this.value)">
                <textarea class="form-control form-control-sm" rows="2" placeholder="Описание" oninput="updateImportTaskDescription(${t.id}, this.value)">${escapeHtml(t.description)}</textarea>
            </div>
            <button type="button" class="btn btn-sm btn-outline-danger mt-1" onclick="deleteImportTask(${t.id})" title="Удалить"><i class="bi bi-trash"></i></button>
        </div>
    `).join('');

    container.innerHTML = html;
}

function getImportProjectId() {
    if (!IS_GLOBAL) return PROJECT_ID;
    const select = document.getElementById('import-bulk-project');
    return select ? (select.value || (filterOptions.projects[0]?.id)) : null;
}

function applyBulkToSelectedImportTasks() {
    const startDate = document.getElementById('import-bulk-start-date').value || null;
    const dueDate = document.getElementById('import-bulk-due-date').value || null;
    const priority = document.getElementById('import-bulk-priority').value || null;
    const statusSelect = document.getElementById('import-bulk-status');
    const statusId = statusSelect?.value ? parseInt(statusSelect.value, 10) : null;
    const assigneeEmails = getBulkAssigneeEmails('import-bulk');
    const tags = document.getElementById('import-bulk-tags').value.trim() || null;
    const listName = document.getElementById('import-bulk-list-name').value.trim() || null;
    const projectId = getImportProjectId();

    importTasksState.forEach(t => {
        if (!t.selected) return;
        if (IS_GLOBAL && projectId) t.project_id = parseInt(projectId, 10);
        if (statusId) t.status_id = statusId;
        if (startDate) t.start_date = new Date(startDate).toISOString();
        if (dueDate) t.due_date = new Date(dueDate).toISOString();
        if (priority) t.priority = priority;
        if (assigneeEmails.length > 0) t.assignee_emails = assigneeEmails;
        if (tags) t.tags = tags;
        if (listName) t.list_name = listName;
    });

    showToast('Групповые настройки применены к выбранным задачам', 'success');
    renderImportTasksList();
}

async function createTasksBulk() {
    const listName = document.getElementById('import-list-name').value.trim() || null;

    const validTasks = importTasksState.filter(t => t.title.trim() || t.description.trim());
    if (validTasks.length === 0) {
        showToast('Нет задач для создания', 'warning');
        return;
    }

    if (IS_GLOBAL) {
        const withoutProject = validTasks.filter(t => !t.project_id);
        if (withoutProject.length > 0) {
            showToast('Укажите проект для всех задач (через массовое редактирование)', 'warning');
            return;
        }
    }

    const payload = {
        tasks: validTasks.map(t => ({
            title: t.title.trim() || null,
            description: t.description.trim() || null,
            priority: t.priority || 'medium',
            status_id: t.status_id || null,
            start_date: t.start_date,
            due_date: t.due_date,
            assignee_emails: t.assignee_emails || [t.assignee_email].filter(Boolean),
            tags: t.tags,
            list_name: listName || undefined,
            project_id: IS_GLOBAL ? t.project_id : undefined,
        })).filter(t => t.project_id !== undefined || !IS_GLOBAL),
        attachments: importBulkAttachments,
    };

    try {
        const url = IS_GLOBAL ? `${API_BASE}/kanban/tasks/bulk` : `${API_BASE}/projects/${PROJECT_ID}/tasks/bulk`;
        const result = await api(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('taskImportModal')).hide();
        showToast(`Создано задач: ${result.count}`, 'success');
        await loadTasks();
        await loadFilters();
    } catch (e) {
        showToast('Ошибка создания задач: ' + e.message, 'danger');
    }
}

// ═══════════════════════════════════════════════════
// ДИАГРАММА ГАНТА
// ═══════════════════════════════════════════════════

function toggleGanttView() {
    ganttView = !ganttView;
    const tableView = document.getElementById('tasks-table-view');
    const selectionToolbar = document.getElementById('tasks-selection-toolbar');
    const ganttViewEl = document.getElementById('gantt-view');
    const label = document.getElementById('gantt-toggle-label');
    const icon = document.getElementById('gantt-toggle-icon');
    const btn = document.getElementById('gantt-toggle-btn');

    if (ganttView) {
        if (tableView) tableView.style.display = 'none';
        if (selectionToolbar) selectionToolbar.style.display = 'none';
        if (ganttViewEl) ganttViewEl.style.display = 'block';
        if (label) label.textContent = 'Список';
        if (icon) icon.className = 'bi bi-list-task me-1';
        if (btn) {
            btn.classList.remove('btn-outline-success');
            btn.classList.add('btn-success');
        }
        renderGantt();
    } else {
        if (tableView) tableView.style.display = 'block';
        if (selectionToolbar) selectionToolbar.style.display = 'flex';
        if (ganttViewEl) ganttViewEl.style.display = 'none';
        if (label) label.textContent = 'Гант';
        if (icon) icon.className = 'bi bi-bar-chart-steps me-1';
        if (btn) {
            btn.classList.remove('btn-success');
            btn.classList.add('btn-outline-success');
        }
        renderTable();
    }
}

function scrollGanttToStart() {
    const wrapper = document.getElementById('gantt-right-wrapper');
    if (wrapper) wrapper.scrollTo({ left: 0, behavior: 'smooth' });
}

function scrollGanttToEnd() {
    const wrapper = document.getElementById('gantt-right-wrapper');
    if (wrapper) wrapper.scrollTo({ left: wrapper.scrollWidth, behavior: 'smooth' });
}

function scrollGanttToToday() {
    const wrapper = document.getElementById('gantt-right-wrapper');
    if (!wrapper || !ganttMinDate || !ganttTimelineWidth || ganttTotalDays === 0) return;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    let left;
    if (today < ganttMinDate) {
        left = 0;
    } else if (today > ganttMaxDate) {
        left = wrapper.scrollWidth;
    } else {
        const dayIndex = daysDiff(ganttMinDate, today);
        left = dayIndex * 36;
    }
    wrapper.scrollTo({ left, behavior: 'smooth' });
}

function parseDatePart(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    d.setHours(0, 0, 0, 0);
    return d;
}

function daysDiff(a, b) {
    return Math.round((b - a) / (1000 * 60 * 60 * 24));
}

function ganttBarClass(task) {
    if (task.is_closed) return 'gantt-fill-closed';
    return {
        low: 'gantt-fill-priority-low',
        medium: 'gantt-fill-priority-medium',
        high: 'gantt-fill-priority-high',
    }[task.priority] || 'gantt-fill-priority-medium';
}

function ganttRowClass(task) {
    if (task.is_closed) return 'gantt-row-closed';
    return {
        low: 'gantt-row-low',
        medium: 'gantt-row-medium',
        high: 'gantt-row-high',
    }[task.priority] || 'gantt-row-medium';
}

function toggleGanttHideNoDeadline() {
    const cb = document.getElementById('gantt-hide-no-deadline');
    ganttHideNoDeadline = cb ? cb.checked : false;
    renderGantt();
}

function toggleGanttStatusOverlay() {
    const cb = document.getElementById('gantt-status-overlay');
    ganttStatusOverlayEnabled = cb ? cb.checked : true;
    renderGantt();
}

async function renderGantt() {
    const theadLeft = document.getElementById('gantt-thead-left');
    const tbodyLeft = document.getElementById('gantt-tbody-left');
    const theadRight = document.getElementById('gantt-thead-right');
    const tbodyRight = document.getElementById('gantt-tbody-right');
    const rangeLabel = document.getElementById('gantt-range-label');
    if (!theadLeft || !tbodyLeft || !theadRight || !tbodyRight) return;

    const tasksToRender = ganttHideNoDeadline
        ? filteredTasks.filter(t => t.due_date)
        : filteredTasks;

    await ensureGanttStatusHistoryLoaded();

    if (tasksToRender.length === 0) {
        tbodyLeft.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">Нет задач</td></tr>`;
        tbodyRight.innerHTML = '';
        if (theadRight) theadRight.innerHTML = '';
        if (rangeLabel) rangeLabel.textContent = '';
        return;
    }

    const allDates = [];
    tasksToRender.forEach(t => {
        const s = parseDatePart(t.start_date) || parseDatePart(t.created_at);
        const e = parseDatePart(t.due_date);
        if (s) allDates.push(s);
        if (e) allDates.push(e);
    });

    if (allDates.length === 0) {
        tbodyLeft.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">У отфильтрованных задач отсутствуют даты</td></tr>`;
        tbodyRight.innerHTML = '';
        if (theadRight) theadRight.innerHTML = '';
        if (rangeLabel) rangeLabel.textContent = '';
        return;
    }

    let minDate = new Date(Math.min(...allDates));
    let maxDate = new Date(Math.max(...allDates));
    minDate.setHours(0, 0, 0, 0);
    maxDate.setHours(0, 0, 0, 0);
    minDate.setDate(minDate.getDate() - 2);
    maxDate.setDate(maxDate.getDate() + 2);

    const totalDays = daysDiff(minDate, maxDate) + 1;
    const dayWidth = 36;
    const timelineWidth = totalDays * dayWidth;

    ganttMinDate = minDate;
    ganttMaxDate = maxDate;
    ganttTotalDays = totalDays;
    ganttTimelineWidth = timelineWidth;

    if (rangeLabel) {
        rangeLabel.textContent = `${minDate.toLocaleDateString('ru-RU')} — ${maxDate.toLocaleDateString('ru-RU')}`;
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const rightTable = document.querySelector('.gantt-table-right');
    if (rightTable) {
        rightTable.style.width = `${timelineWidth}px`;
        rightTable.style.tableLayout = 'fixed';
        let colgroup = rightTable.querySelector('colgroup');
        if (!colgroup) {
            colgroup = document.createElement('colgroup');
            rightTable.insertBefore(colgroup, rightTable.firstChild);
        }
        colgroup.innerHTML = `<col style="width:${timelineWidth}px;">`;
    }

    theadLeft.innerHTML = `
        <tr>
            <th class="gantt-col-num"><div class="gantt-cell-content">#</div></th>
            <th class="gantt-col-title"><div class="gantt-cell-content">Название</div></th>
            <th class="gantt-col-assignee"><div class="gantt-cell-content">Исполнитель</div></th>
            <th class="gantt-col-start"><div class="gantt-cell-content">Начало</div></th>
            <th class="gantt-col-end"><div class="gantt-cell-content">Конец</div></th>
            <th class="gantt-col-duration"><div class="gantt-cell-content">Длит.</div></th>
        </tr>`;

    let rightHeaderHtml = `<tr><th class="gantt-col-timeline"><div class="d-flex" style="width:${timelineWidth}px;">`;
    for (let i = 0; i < totalDays; i++) {
        const d = new Date(minDate);
        d.setDate(d.getDate() + i);
        const isToday = d.getTime() === today.getTime();
        const showMonth = i === 0 || d.getDate() === 1;
        const month = showMonth ? d.toLocaleDateString('ru-RU', { month: 'short' }).replace(/\.$/, '') : '';
        rightHeaderHtml += `<div class="gantt-day-header${isToday ? ' today' : ''}" title="${d.toLocaleDateString('ru-RU')}">${month ? `<small>${month}</small>` : ''}${d.getDate()}</div>`;
    }
    rightHeaderHtml += `</div></th></tr>`;
    theadRight.innerHTML = rightHeaderHtml;

    let leftRowsHtml = '';
    let rightRowsHtml = '';

    tasksToRender.forEach((t, idx) => {
        let start = parseDatePart(t.start_date) || parseDatePart(t.created_at);
        const end = parseDatePart(t.due_date);
        if (!start && !end) return;
        if (!start) start = end;

        const startStr = start.toLocaleDateString('ru-RU');
        const endStr = end ? end.toLocaleDateString('ru-RU') : '—';
        const duration = end ? (daysDiff(start, end) + 1) : '—';
        const assignee = formatAssignees(t);
        const titleDisplay = escapeHtml((t.title && t.title.trim()) || (t.description && t.description.trim()) || '—');

        const fillClass = ganttBarClass(t);
        const rowClass = ganttRowClass(t);
        const hoverAttrs = `data-gantt-idx="${idx}" onmouseenter="hoverGanttRow(${idx})" onmouseleave="unhoverGanttRow(${idx})"`;

        const history = taskStatusHistory[t.id] || [];
        const mapping = ganttKanbanStatusMap[t.project_id] || {};
        const testingEntry = history.find(h => h.status_id === mapping.testingStatusId);
        const deployEntry = history.find(h => h.status_id === mapping.deployStatusId);
        const testingDate = testingEntry ? parseDatePart(testingEntry.entered_at) : null;
        const deployDate = deployEntry ? parseDatePart(deployEntry.entered_at) : null;

        let daysHtml = '';
        for (let i = 0; i < totalDays; i++) {
            const dayDate = new Date(minDate);
            dayDate.setDate(dayDate.getDate() + i);
            let isActive = false;
            let isStriped = false;
            if (end) {
                const visibleStart = start < minDate ? minDate : start;
                const visibleEnd = end > maxDate ? maxDate : end;
                isActive = dayDate >= visibleStart && dayDate <= visibleEnd;
                if (isActive && deployDate && deployDate < end) {
                    isStriped = dayDate > deployDate;
                }
            }
            const isToday = dayDate.getTime() === today.getTime();
            const dayClass = isActive ? (isStriped ? ` ${fillClass}-striped` : ` ${fillClass}`) : '';
            const weekendClass = [0, 6].includes(dayDate.getDay()) ? ' weekend' : '';
            const todayClass = isToday ? ' today' : '';

            let overlayHtml = '';
            if (ganttStatusOverlayEnabled) {
                const isTestingDay = testingDate && dayDate.getTime() === testingDate.getTime();
                const isDeployDay = deployDate && dayDate.getTime() === deployDate.getTime();
                const isDeadlineDay = end && dayDate.getTime() === end.getTime() && end <= today;
                const parts = [];
                if (isTestingDay) {
                    parts.push('<span class="gantt-overlay-text testing" title="Тестирование">T</span>');
                }
                if (isDeployDay) {
                    parts.push('<span class="gantt-overlay-text deploy" title="Деплой">D</span>');
                }
                if (isDeadlineDay) {
                    if (!deployDate || deployDate > end) {
                        if (!testingDate || testingDate > end) {
                            parts.push('<span class="gantt-overlay-danger" title="Не дошла до тестирования к дедлайну">!</span>');
                        } else {
                            parts.push('<span class="gantt-overlay-warning" title="В тестировании, но не в деплое к дедлайну">⚡</span>');
                        }
                    }
                }
                if (parts.length) {
                    overlayHtml = '<div class="gantt-day-overlays">' + parts.join('') + '</div>';
                }
            }

            daysHtml += `<div class="gantt-day-cell${dayClass}${weekendClass}${todayClass}" title="#${t.id} ${escapeHtml(t.title || '')}\n${startStr} — ${endStr}">${overlayHtml}</div>`;
        }

        leftRowsHtml += `
            <tr ${hoverAttrs} class="${rowClass}" style="cursor:pointer;" onclick="openTaskViewModal(${t.id})">
                <td class="gantt-col-num"><div class="gantt-cell-content">${t.id}</div></td>
                <td class="gantt-col-title"><div class="gantt-cell-content" title="${escapeHtml(t.title || t.description || '')}">${titleDisplay}</div></td>
                <td class="gantt-col-assignee"><div class="gantt-cell-content">${assignee}</div></td>
                <td class="gantt-col-start"><div class="gantt-cell-content">${startStr}</div></td>
                <td class="gantt-col-end"><div class="gantt-cell-content">${endStr}</div></td>
                <td class="gantt-col-duration"><div class="gantt-cell-content">${duration}</div></td>
            </tr>`;

        rightRowsHtml += `
            <tr ${hoverAttrs} class="${rowClass}" style="cursor:pointer;" onclick="openTaskViewModal(${t.id})">
                <td class="gantt-col-timeline">
                    <div class="gantt-timeline-track" style="width:${timelineWidth}px;">${daysHtml}</div>
                </td>
            </tr>`;
    });

    if (!leftRowsHtml.trim()) {
        tbodyLeft.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">У отфильтрованных задач отсутствуют даты</td></tr>`;
        tbodyRight.innerHTML = '';
        if (theadRight) theadRight.innerHTML = '';
        return;
    }

    tbodyLeft.innerHTML = leftRowsHtml;
    tbodyRight.innerHTML = rightRowsHtml;
    syncGanttRowHeights();
}

function syncGanttRowHeights() {
    const leftRows = document.querySelectorAll('#gantt-tbody-left tr, #gantt-thead-left tr');
    const rightRows = document.querySelectorAll('#gantt-tbody-right tr, #gantt-thead-right tr');
    const count = Math.max(leftRows.length, rightRows.length);
    for (let i = 0; i < count; i++) {
        const left = leftRows[i];
        const right = rightRows[i];
        if (!left || !right) continue;
        left.style.height = '';
        right.style.height = '';
    }
    for (let i = 0; i < count; i++) {
        const left = leftRows[i];
        const right = rightRows[i];
        if (!left || !right) continue;
        const maxHeight = Math.max(left.offsetHeight, right.offsetHeight);
        left.style.height = `${maxHeight}px`;
        right.style.height = `${maxHeight}px`;
    }
}

function hoverGanttRow(idx) {
    document.querySelectorAll(`[data-gantt-idx="${idx}"]`).forEach(r => r.classList.add('gantt-row-hover'));
}

function unhoverGanttRow(idx) {
    document.querySelectorAll(`[data-gantt-idx="${idx}"]`).forEach(r => r.classList.remove('gantt-row-hover'));
}


async function exportGanttXlsx() {
    const params = new URLSearchParams();

    if (!IS_GLOBAL) {
        params.set('project_id', PROJECT_ID);
    } else {
        const projectEl = document.getElementById('filter-project');
        if (projectEl?.value) params.set('project_id', projectEl.value);
    }

    const search = document.getElementById('filter-search')?.value;
    if (search) params.set('search', search);

    const status = document.getElementById('filter-status')?.value;
    if (status) params.set('status', status);

    const priority = document.getElementById('filter-priority')?.value;
    if (priority) params.set('priority', priority);

    const assignee = document.getElementById('filter-assignee')?.value;
    if (assignee) params.set('assignee_email', assignee);

    const listName = document.getElementById('filter-list')?.value;
    if (listName) params.set('list_name', listName);

    const closed = document.getElementById('filter-closed')?.value;
    if (closed !== '' && closed !== null && closed !== undefined) {
        params.set('closed', closed);
    }

    const tags = document.getElementById('filter-tags')?.value;
    if (tags) params.set('tags', tags);

    if (ganttHideNoDeadline) {
        params.set('hide_no_deadline', '1');
    }

    if (ganttStatusOverlayEnabled) {
        params.set('status_overlay', '1');
    }

    params.set('sort_by', sortColumn);
    params.set('sort_order', sortDirection);

    const url = `${API_BASE}/gantt/export/xlsx?${params.toString()}`;

    try {
        const response = await fetch(url, { credentials: 'same-origin' });
        if (!response.ok) {
            let detail = `Ошибка ${response.status}`;
            try {
                const err = await response.json();
                if (err.detail) detail = err.detail;
            } catch (e) {}
            showToast(detail, 'danger');
            return;
        }
        const blob = await response.blob();
        const disposition = response.headers.get('content-disposition');
        let filename = 'gantt_export.xlsx';
        if (disposition) {
            const match = disposition.match(/filename="?([^"]+)"?/);
            if (match) filename = match[1];
        }
        const downloadUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(downloadUrl);
        showToast('Гант выгружен в XLSX', 'success');
    } catch (e) {
        showToast('Ошибка выгрузки: ' + e.message, 'danger');
    }
}
