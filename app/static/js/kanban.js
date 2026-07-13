// ═══════════════════════════════════════════════════
// КАНБАН
// ═══════════════════════════════════════════════════

let kanbanData = { statuses: [], tasks: [] };
let kanbanSortables = [];
let currentTaskId = null;
let currentStatusId = null;

document.addEventListener('DOMContentLoaded', () => {
    if (typeof PROJECT_ID === 'undefined') return;
    loadProjectHeader(PROJECT_ID);
    loadKanbanBoard(PROJECT_ID);
});

async function loadProjectHeader(projectId) {
    try {
        const project = await api(`${API_BASE}/projects/${projectId}`);
        const header = document.getElementById('kanban-header');
        if (header) {
            header.innerHTML = `
                <h2 class="mb-0">${escapeHtml(project.name)}</h2>
                ${project.description ? `<p class="text-muted mb-0">${escapeHtml(project.description)}</p>` : ''}
            `;
        }
    } catch (e) {
        console.error('Failed to load project header:', e);
    }
}

async function loadKanbanBoard(projectId) {
    const board = document.getElementById('kanban-board');
    if (!board) return;
    board.innerHTML = '<div class="text-center text-muted py-5"><div class="spinner-border"></div></div>';

    try {
        const data = await api(`${API_BASE}/projects/${projectId}/tasks/board`);
        kanbanData = data;
        renderBoard(data);
        initKanbanSortable();
    } catch (e) {
        board.innerHTML = `<div class="text-center text-danger py-5">Не удалось загрузить канбан: ${escapeHtml(e.message)}</div>`;
    }
}

function renderBoard(data) {
    const board = document.getElementById('kanban-board');
    if (!board) return;

    if (!data.statuses || data.statuses.length === 0) {
        board.innerHTML = `
            <div class="text-center text-muted py-5">
                <i class="bi bi-kanban display-4"></i>
                <p class="mt-3">Нет колонок. Создайте первую колонку, чтобы начать.</p>
                <button class="btn btn-primary" onclick="openStatusModal()">
                    <i class="bi bi-plus-lg me-1"></i> Создать колонку
                </button>
            </div>`;
        return;
    }

    board.innerHTML = data.statuses.map(status => {
        const tasks = (data.tasks || []).filter(t => t.status_id === status.id);
        return `
            <div class="kanban-column" data-id="${status.id}">
                <div class="kanban-column-header" style="border-top-color: ${escapeHtml(status.color)}">
                    <span class="kanban-column-title">${escapeHtml(status.name)}</span>
                    <div class="kanban-column-actions">
                        <span class="badge bg-secondary rounded-pill kanban-column-count">${tasks.length}</span>
                        <button class="btn btn-sm btn-link text-muted p-0" onclick="openStatusModal(${status.id})">
                            <i class="bi bi-three-dots-vertical"></i>
                        </button>
                    </div>
                </div>
                <div class="kanban-column-body" data-status-id="${status.id}">
                    ${tasks.map(task => renderTaskCard(task)).join('')}
                </div>
                <div class="kanban-column-footer">
                    <button class="btn btn-sm btn-outline-brown w-100" onclick="openTaskModal(null, ${status.id})">
                        <i class="bi bi-plus-lg me-1"></i> Добавить задачу
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function renderTaskCard(task) {
    const priorityClass = {
        low: 'bg-success',
        medium: 'bg-warning text-dark',
        high: 'bg-danger',
    }[task.priority] || 'bg-secondary';

    const priorityLabel = {
        low: 'Низкий',
        medium: 'Средний',
        high: 'Высокий',
    }[task.priority] || task.priority;

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
        <div class="kanban-card" data-id="${task.id}" data-status-id="${task.status_id}" onclick="openTaskModal(${task.id})">
            <div class="d-flex justify-content-between align-items-start mb-2">
                <span class="kanban-card-title">${escapeHtml(task.title)}</span>
                <span class="badge ${priorityClass} priority-badge">${priorityLabel}</span>
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
            group: 'kanban-tasks',
            animation: 150,
            delay: 100,
            delayOnTouchOnly: true,
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            onEnd: function (evt) {
                const taskId = parseInt(evt.item.dataset.id, 10);
                const newStatusId = parseInt(evt.to.dataset.statusId, 10);
                const newIndex = evt.newIndex;
                updateTaskStatus(taskId, newStatusId, newIndex);
            },
        });
        kanbanSortables.push(sortable);
    });

    const board = document.getElementById('kanban-board');
    if (board && board.classList.contains('kanban-board')) {
        Sortable.create(board, {
            animation: 150,
            handle: '.kanban-column-header',
            draggable: '.kanban-column',
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            onEnd: function () {
                const statusIds = Array.from(board.querySelectorAll('.kanban-column'))
                    .map(col => parseInt(col.dataset.id, 10));
                reorderStatuses(statusIds);
            },
        });
    }
}

async function updateTaskStatus(taskId, statusId, newIndex) {
    const columnBody = document.querySelector(`.kanban-column-body[data-status-id="${statusId}"]`);
    if (!columnBody) return;

    const taskIds = Array.from(columnBody.querySelectorAll('.kanban-card'))
        .map(card => parseInt(card.dataset.id, 10));

    // Оптимистично обновляем локальные данные
    const task = kanbanData.tasks.find(t => t.id === taskId);
    if (task) task.status_id = statusId;

    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/reorder`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status_id: statusId, task_ids: taskIds }),
        });
    } catch (e) {
        alert('Ошибка обновления статуса: ' + e.message);
        loadKanbanBoard(PROJECT_ID);
    }
}

async function reorderStatuses(statusIds) {
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/task-statuses/reorder`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status_ids: statusIds }),
        });
    } catch (e) {
        alert('Ошибка изменения порядка колонок: ' + e.message);
        loadKanbanBoard(PROJECT_ID);
    }
}

// ═══════════════════════════════════════════════════
// ЗАДАЧИ
// ═══════════════════════════════════════════════════

function openTaskModal(taskId, defaultStatusId) {
    currentTaskId = taskId || null;
    const modalEl = document.getElementById('taskModal');
    const form = document.getElementById('task-form');
    const titleEl = document.getElementById('task-modal-title');
    const deleteBtn = document.getElementById('task-delete-btn');

    form.reset();
    document.getElementById('task-id').value = '';
    document.getElementById('task-status-id').value = defaultStatusId || '';

    if (taskId) {
        const task = kanbanData.tasks.find(t => t.id === taskId);
        if (!task) return;
        titleEl.textContent = 'Редактировать задачу';
        document.getElementById('task-id').value = task.id;
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
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

async function saveTask() {
    const form = document.getElementById('task-form');
    if (!form.title.value.trim()) {
        alert('Введите название задачи');
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

    try {
        if (currentTaskId) {
            await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/${currentTaskId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        } else {
            const statusId = parseInt(document.getElementById('task-status-id').value, 10);
            if (!statusId) {
                alert('Не выбрана колонка');
                return;
            }
            await api(`${API_BASE}/projects/${PROJECT_ID}/tasks`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...payload, status_id: statusId }),
            });
        }
        bootstrap.Modal.getOrCreateInstance(document.getElementById('taskModal')).hide();
        loadKanbanBoard(PROJECT_ID);
    } catch (e) {
        alert('Ошибка сохранения задачи: ' + e.message);
    }
}

async function deleteTaskFromModal() {
    if (!currentTaskId) return;
    if (!confirm('Удалить задачу?')) return;

    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/${currentTaskId}`, { method: 'DELETE' });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('taskModal')).hide();
        loadKanbanBoard(PROJECT_ID);
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
        const status = kanbanData.statuses.find(s => s.id === statusId);
        if (!status) return;
        titleEl.textContent = 'Редактировать колонку';
        document.getElementById('status-id').value = status.id;
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

async function saveStatus() {
    const form = document.getElementById('status-form');
    if (!form.name.value.trim()) {
        alert('Введите название колонки');
        return;
    }

    const payload = {
        name: form.name.value.trim(),
        color: form.color.value,
    };

    try {
        if (currentStatusId) {
            await api(`${API_BASE}/projects/${PROJECT_ID}/task-statuses/${currentStatusId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        } else {
            await api(`${API_BASE}/projects/${PROJECT_ID}/task-statuses`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        }
        bootstrap.Modal.getOrCreateInstance(document.getElementById('statusModal')).hide();
        loadKanbanBoard(PROJECT_ID);
    } catch (e) {
        alert('Ошибка сохранения колонки: ' + e.message);
    }
}

async function deleteStatusFromModal() {
    if (!currentStatusId) return;
    const status = kanbanData.statuses.find(s => s.id === currentStatusId);
    const hasTasks = kanbanData.tasks.some(t => t.status_id === currentStatusId);
    if (hasTasks) {
        alert('Нельзя удалить колонку с задачами. Переместите или удалите задачи сначала.');
        return;
    }
    if (!confirm(`Удалить колонку "${status?.name || ''}"?`)) return;

    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/task-statuses/${currentStatusId}`, { method: 'DELETE' });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('statusModal')).hide();
        loadKanbanBoard(PROJECT_ID);
    } catch (e) {
        alert('Ошибка удаления колонки: ' + e.message);
    }
}

// ═══════════════════════════════════════════════════
// УТИЛИТЫ
// ═══════════════════════════════════════════════════

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
