// ═══════════════════════════════════════════════════
// ОБЩИЙ КАНБАН
// ═══════════════════════════════════════════════════

let kanbanData = { columns: [], tasks: [] };
let filterOptions = { projects: [], priorities: [], assignees: [], tags: [] };
let projectStatuses = {};
let kanbanSortables = [];
let currentTaskId = null;
let currentStatusId = null;

document.addEventListener('DOMContentLoaded', async () => {
    await loadFilters();
    await loadKanbanBoard();
});

async function loadFilters() {
    try {
        filterOptions = await api(`${API_BASE}/kanban/filters`);
        populateSelect('filter-project', filterOptions.projects, 'id', 'name');
        populateSelect('filter-priority', filterOptions.priorities.map(p => ({ value: p, label: priorityLabel(p) })), 'value', 'label');
        populateSelect('filter-assignee', filterOptions.assignees.map(a => ({ value: a, label: a })), 'value', 'label');
        populateSelect('filter-tag', filterOptions.tags.map(t => ({ value: t, label: t })), 'value', 'label');

        populateSelect('task-project-id', filterOptions.projects, 'id', 'name');
        populateSelect('status-project-id', filterOptions.projects, 'id', 'name');

        await loadAllProjectStatuses();
    } catch (e) {
        console.error('Failed to load filters:', e);
    }
}

async function loadAllProjectStatuses() {
    projectStatuses = {};
    for (const project of filterOptions.projects) {
        try {
            const statuses = await api(`${API_BASE}/projects/${project.id}/task-statuses`);
            projectStatuses[project.id] = statuses;
        } catch (e) {
            projectStatuses[project.id] = [];
        }
    }
}

function populateSelect(id, items, valueKey, labelKey) {
    const select = document.getElementById(id);
    if (!select) return;
    const currentValue = select.value;
    const defaultText = select.options[0]?.text || 'Все';
    select.innerHTML = `<option value="">${defaultText}</option>` +
        items.map(item => `<option value="${escapeHtml(String(item[valueKey]))}">${escapeHtml(String(item[labelKey]))}</option>`).join('');
    select.value = currentValue;
}

function onTaskProjectChange() {
    const projectId = document.getElementById('task-project-id').value;
    const statusSelect = document.getElementById('task-status-id');
    statusSelect.innerHTML = '<option value="">Выберите статус</option>';
    const statuses = projectStatuses[projectId] || [];
    statuses.forEach(status => {
        const option = document.createElement('option');
        option.value = status.id;
        option.textContent = status.name;
        statusSelect.appendChild(option);
    });
}

function buildQueryString() {
    const params = new URLSearchParams();
    const projectId = document.getElementById('filter-project')?.value;
    const priority = document.getElementById('filter-priority')?.value;
    const assignee = document.getElementById('filter-assignee')?.value;
    const tag = document.getElementById('filter-tag')?.value;
    const dueBefore = document.getElementById('filter-due-before')?.value;
    const createdAfter = document.getElementById('filter-created-after')?.value;
    const createdBefore = document.getElementById('filter-created-before')?.value;

    if (projectId) params.append('project_id', projectId);
    if (priority) params.append('priority', priority);
    if (assignee) params.append('assignee_email', assignee);
    if (tag) params.append('tags', tag);
    if (dueBefore) params.append('due_before', new Date(dueBefore).toISOString());
    if (createdAfter) params.append('created_after', new Date(createdAfter).toISOString());
    if (createdBefore) params.append('created_before', new Date(createdBefore).toISOString());

    return params.toString();
}

async function loadKanbanBoard() {
    const board = document.getElementById('kanban-board');
    if (!board) return;
    board.innerHTML = '<div class="text-center text-muted py-5"><div class="spinner-border"></div></div>';

    try {
        const qs = buildQueryString();
        const url = `${API_BASE}/kanban${qs ? '?' + qs : ''}`;
        kanbanData = await api(url);
        renderBoard(kanbanData);
        initKanbanSortable();
    } catch (e) {
        board.innerHTML = `<div class="text-center text-danger py-5">Не удалось загрузить канбан: ${escapeHtml(e.message)}</div>`;
    }
}

function renderBoard(data) {
    const board = document.getElementById('kanban-board');
    if (!board) return;

    if (!data.columns || data.columns.length === 0) {
        board.innerHTML = `
            <div class="text-center text-muted py-5">
                <i class="bi bi-kanban display-4"></i>
                <p class="mt-3">Нет задач или колонок.</p>
            </div>`;
        return;
    }

    board.innerHTML = data.columns.map(column => {
        const tasks = (data.tasks || []).filter(t => t.status && t.status.name === column.name);
        return `
            <div class="kanban-column" data-name="${escapeHtml(column.name)}">
                <div class="kanban-column-header" style="border-top-color: ${escapeHtml(column.color)}">
                    <span class="kanban-column-title">${escapeHtml(column.name)}</span>
                    <span class="badge bg-secondary rounded-pill kanban-column-count">${tasks.length}</span>
                </div>
                <div class="kanban-column-body" data-column-name="${escapeHtml(column.name)}">
                    ${tasks.map(task => renderTaskCard(task)).join('')}
                </div>
                <div class="kanban-column-footer">
                    <button class="btn btn-sm btn-outline-brown w-100" onclick="openTaskModal(null, null, '${escapeHtml(column.name)}')">
                        <i class="bi bi-plus-lg me-1"></i> Добавить задачу
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function renderTaskCard(task) {
    const taskProjectId = String(task.project_id);
    const project = (filterOptions?.projects || []).find(p => String(p.id) === taskProjectId);
    const projectName = project ? project.name : `Проект #${task.project_id}`;

    const priorityClass = {
        low: 'bg-success',
        medium: 'bg-warning text-dark',
        high: 'bg-danger',
    }[task.priority] || 'bg-secondary';

    const dueDate = task.due_date
        ? `<span class="kanban-task-meta kanban-deadline-meta" title="Дедлайн"><i class="bi bi-bell"></i> ${formatDateTime(task.due_date)}</span>`
        : '';

    const assignee = task.assignee_email
        ? `<span class="kanban-task-meta" title="Ответственный"><i class="bi bi-person"></i> ${escapeHtml(task.assignee_email)}</span>`
        : '';

    const tags = task.tags
        ? task.tags.split(',').map(t => t.trim()).filter(Boolean).map(t =>
            `<span class="kanban-tag">${escapeHtml(t)}</span>`
          ).join('')
        : '';

    return `
        <div class="kanban-card" data-id="${task.id}" onclick="openTaskModal(${task.id})">
            <div class="d-flex justify-content-between align-items-start mb-2">
                <span class="kanban-card-title">${escapeHtml(task.title)}</span>
                <span class="badge ${priorityClass} priority-badge">${priorityLabel(task.priority)}</span>
            </div>
            <div class="kanban-task-project">
                <i class="bi bi-folder"></i> ${escapeHtml(projectName)}
            </div>
            ${task.description ? `<p class="kanban-card-desc">${escapeHtml(task.description)}</p>` : ''}
            <div class="kanban-task-meta-wrap">
                ${dueDate}
                ${assignee}
            </div>
            <div class="kanban-card-footer">
                ${tags ? `<div class="kanban-tags">${tags}</div>` : '<div></div>'}
                <span class="kanban-created-at" title="Создано"><i class="bi bi-calendar"></i> ${formatDateTime(task.created_at)}</span>
            </div>
        </div>
    `;
}

function initKanbanSortable() {
    kanbanSortables.forEach(s => s.destroy());
    kanbanSortables = [];

    document.querySelectorAll('.kanban-column-body').forEach(body => {
        const sortable = Sortable.create(body, {
            group: 'kanban-global-tasks',
            animation: 150,
            delay: 100,
            delayOnTouchOnly: true,
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            onEnd: function (evt) {
                const taskId = parseInt(evt.item.dataset.id, 10);
                const columnName = evt.to.dataset.columnName;
                updateTaskColumn(taskId, columnName);
            },
        });
        kanbanSortables.push(sortable);
    });
}

async function updateTaskColumn(taskId, columnName) {
    try {
        await api(`${API_BASE}/kanban/tasks/${taskId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ column_name: columnName }),
        });
        loadKanbanBoard();
        await loadFilters();
    } catch (e) {
        alert('Ошибка перемещения задачи: ' + e.message);
        loadKanbanBoard();
    }
}

// ═══════════════════════════════════════════════════
// ЗАДАЧИ
// ═══════════════════════════════════════════════════

function openTaskModal(taskId, defaultProjectId, defaultColumnName) {
    currentTaskId = taskId || null;
    const modalEl = document.getElementById('taskModal');
    const form = document.getElementById('task-form');
    const titleEl = document.getElementById('task-modal-title');
    const deleteBtn = document.getElementById('task-delete-btn');

    form.reset();
    document.getElementById('task-id').value = '';
    document.getElementById('task-project-id').value = defaultProjectId || '';
    onTaskProjectChange();

    if (taskId) {
        const task = kanbanData.tasks.find(t => t.id === taskId);
        if (!task) return;
        titleEl.textContent = task.title;
        document.getElementById('task-id').value = task.id;
        document.getElementById('task-project-id').value = task.project_id;
        onTaskProjectChange();
        document.getElementById('task-status-id').value = task.status_id;
        form.title.value = task.title;
        form.description.value = task.description || '';
        form.priority.value = task.priority || 'medium';
        form.due_date.value = task.due_date ? formatDateTimeLocal(task.due_date) : '';
        form.assignee_email.value = task.assignee_email || '';
        form.tags.value = task.tags || '';
        deleteBtn.style.display = 'inline-block';
    } else {
        titleEl.textContent = 'Новая задача';
        form.priority.value = 'medium';
        deleteBtn.style.display = 'none';
        if (defaultColumnName) {
            // Подобрать первый проект, у которого есть такой статус
            for (const project of filterOptions.projects) {
                const statuses = projectStatuses[project.id] || [];
                if (statuses.some(s => s.name === defaultColumnName)) {
                    document.getElementById('task-project-id').value = project.id;
                    onTaskProjectChange();
                    const status = statuses.find(s => s.name === defaultColumnName);
                    if (status) document.getElementById('task-status-id').value = status.id;
                    break;
                }
            }
        }
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

async function saveTask() {
    const form = document.getElementById('task-form');
    const saveBtn = document.querySelector('#taskModal .modal-footer .btn-primary');

    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.dataset.originalText = saveBtn.textContent;
        saveBtn.textContent = 'Сохранение...';
    }

    try {
        if (!form.title.value.trim()) {
            alert('Введите название задачи');
            return;
        }
        const projectId = parseInt(document.getElementById('task-project-id').value, 10);
        const statusId = parseInt(document.getElementById('task-status-id').value, 10);
        if (!projectId) {
            alert('Выберите проект');
            return;
        }
        if (!statusId) {
            alert('Выберите статус');
            return;
        }

        const payload = {
            title: form.title.value.trim(),
            description: form.description.value.trim() || null,
            priority: form.priority.value,
            due_date: form.due_date.value ? new Date(form.due_date.value).toISOString() : null,
            assignee_email: form.assignee_email.value.trim() || null,
            tags: form.tags.value.trim() || null,
        };

        if (currentTaskId) {
            await api(`${API_BASE}/projects/${projectId}/tasks/${currentTaskId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...payload, status_id: statusId }),
            });
        } else {
            await api(`${API_BASE}/projects/${projectId}/tasks`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...payload, status_id: statusId }),
            });
        }
        bootstrap.Modal.getOrCreateInstance(document.getElementById('taskModal')).hide();
        loadKanbanBoard();
        await loadFilters();
    } catch (e) {
        console.error('saveTask error:', e);
        alert('Ошибка сохранения задачи: ' + e.message);
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = saveBtn.dataset.originalText || 'Сохранить';
        }
    }
}

async function deleteTaskFromModal() {
    if (!currentTaskId) return;
    const task = kanbanData.tasks.find(t => t.id === currentTaskId);
    if (!task) return;
    if (!confirm('Удалить задачу?')) return;

    try {
        await api(`${API_BASE}/projects/${task.project_id}/tasks/${currentTaskId}`, { method: 'DELETE' });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('taskModal')).hide();
        await loadFilters();
        loadKanbanBoard();
    } catch (e) {
        alert('Ошибка удаления задачи: ' + e.message);
    }
}

// ═══════════════════════════════════════════════════
// КОЛОНКИ
// ═══════════════════════════════════════════════════

function openStatusModal(statusId) {
    currentStatusId = statusId || null;
    const modalEl = document.getElementById('statusModal');
    const form = document.getElementById('status-form');
    const titleEl = document.getElementById('status-modal-title');
    const deleteBtn = document.getElementById('status-delete-btn');

    form.reset();
    document.getElementById('status-id').value = '';

    if (statusId) {
        const status = findStatusById(statusId);
        if (!status) return;
        titleEl.textContent = 'Редактировать колонку';
        document.getElementById('status-id').value = status.id;
        document.getElementById('status-project-id').value = status.project_id;
        form.name.value = status.name;
        form.color.value = status.color;
        deleteBtn.style.display = 'inline-block';
    } else {
        titleEl.textContent = 'Новая колонка';
        form.color.value = '#a78bfa';
        deleteBtn.style.display = 'none';
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

function findStatusById(statusId) {
    for (const projectId in projectStatuses) {
        const status = projectStatuses[projectId].find(s => s.id === statusId);
        if (status) return status;
    }
    return null;
}

async function saveStatus() {
    const form = document.getElementById('status-form');
    const saveBtn = document.querySelector('#statusModal .modal-footer .btn-primary');

    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.dataset.originalText = saveBtn.textContent;
        saveBtn.textContent = 'Сохранение...';
    }

    try {
        if (!form.name.value.trim()) {
            alert('Введите название колонки');
            return;
        }
        const projectId = parseInt(document.getElementById('status-project-id').value, 10);
        if (!projectId) {
            alert('Выберите проект');
            return;
        }

        const payload = {
            name: form.name.value.trim(),
            color: form.color.value,
        };

        if (currentStatusId) {
            await api(`${API_BASE}/projects/${projectId}/task-statuses/${currentStatusId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        } else {
            await api(`${API_BASE}/projects/${projectId}/task-statuses`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        }
        bootstrap.Modal.getOrCreateInstance(document.getElementById('statusModal')).hide();
        loadKanbanBoard();
        await loadFilters();
    } catch (e) {
        console.error('saveStatus error:', e);
        alert('Ошибка сохранения колонки: ' + e.message);
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = saveBtn.dataset.originalText || 'Сохранить';
        }
    }
}

async function deleteStatusFromModal() {
    if (!currentStatusId) return;
    const status = findStatusById(currentStatusId);
    if (!status) return;
    const hasTasks = kanbanData.tasks.some(t => t.status_id === currentStatusId);
    if (hasTasks) {
        alert('Нельзя удалить колонку с задачами. Переместите или удалите задачи сначала.');
        return;
    }
    if (!confirm(`Удалить колонку "${status.name}"?`)) return;

    try {
        await api(`${API_BASE}/projects/${status.project_id}/task-statuses/${currentStatusId}`, { method: 'DELETE' });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('statusModal')).hide();
        await loadFilters();
        loadKanbanBoard();
    } catch (e) {
        alert('Ошибка удаления колонки: ' + e.message);
    }
}

// ═══════════════════════════════════════════════════
// УТИЛИТЫ
// ═══════════════════════════════════════════════════

function applyFilters() {
    loadKanbanBoard();
}

function resetFilters() {
    document.getElementById('filter-project').value = '';
    document.getElementById('filter-priority').value = '';
    document.getElementById('filter-assignee').value = '';
    document.getElementById('filter-tag').value = '';
    document.getElementById('filter-due-before').value = '';
    document.getElementById('filter-created-after').value = '';
    document.getElementById('filter-created-before').value = '';
    loadKanbanBoard();
}

function priorityLabel(priority) {
    return {
        low: 'Низкий',
        medium: 'Средний',
        high: 'Высокий',
    }[priority] || priority;
}

function formatDateTime(isoString) {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return isoString;
    return date.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function formatDateTimeLocal(isoString) {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return '';
    const pad = n => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function escapeHtml(text) {
    if (text == null) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

async function exportKanban() {
    try {
        const data = await api(`${API_BASE}/kanban/export`);
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `kanban_export_${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('Ошибка экспорта канбана: ' + e.message);
    }
}

async function importKanban(input) {
    const file = input.files[0];
    if (!file) return;
    input.value = '';

    if (!confirm('Импорт заменит существующие колонки и задачи с совпадающими названиями и может создать новые проекты. Продолжить?')) {
        return;
    }

    try {
        const text = await file.text();
        const data = JSON.parse(text);
        const result = await api(`${API_BASE}/kanban/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        alert(`Импорт завершён. Проектов: ${result.imported_projects}, колонок: ${result.imported_statuses}, задач: ${result.imported_tasks}`);
        await loadFilters();
        await loadKanbanBoard();
    } catch (e) {
        alert('Ошибка импорта канбана: ' + e.message);
    }
}
