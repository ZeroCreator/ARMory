// ═══════════════════════════════════════════════════
// КАНБАН
// ═══════════════════════════════════════════════════

let kanbanData = { statuses: [], tasks: [] };
let filterOptions = { priorities: [], assignees: [], tags: [] };
let kanbanSortables = [];
let currentTaskId = null;
let currentStatusId = null;

document.addEventListener('DOMContentLoaded', () => {
    if (typeof PROJECT_ID === 'undefined') return;
    loadProjectHeader(PROJECT_ID);
    loadFilters();
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

async function loadFilters() {
    try {
        filterOptions = await api(`${API_BASE}/projects/${PROJECT_ID}/kanban/filters`);
        populateSelect('filter-priority', filterOptions.priorities.map(p => ({ value: p, label: priorityLabel(p) })), 'value', 'label');
        populateSelect('filter-assignee', filterOptions.assignees.map(a => ({ value: a, label: a })), 'value', 'label');
        populateSelect('filter-tag', filterOptions.tags.map(t => ({ value: t, label: t })), 'value', 'label');
    } catch (e) {
        console.error('Failed to load filters:', e);
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

function buildQueryString() {
    const params = new URLSearchParams();
    const priority = document.getElementById('filter-priority')?.value;
    const assignee = document.getElementById('filter-assignee')?.value;
    const tag = document.getElementById('filter-tag')?.value;
    const dueBefore = document.getElementById('filter-due-before')?.value;
    const createdAfter = document.getElementById('filter-created-after')?.value;
    const createdBefore = document.getElementById('filter-created-before')?.value;

    if (priority) params.append('priority', priority);
    if (assignee) params.append('assignee_email', assignee);
    if (tag) params.append('tags', tag);
    if (dueBefore) params.append('due_before', new Date(dueBefore).toISOString());
    if (createdAfter) params.append('created_after', new Date(createdAfter).toISOString());
    if (createdBefore) params.append('created_before', new Date(createdBefore).toISOString());

    return params.toString();
}

async function loadKanbanBoard(projectId) {
    const board = document.getElementById('kanban-board');
    if (!board) return;
    board.innerHTML = '<div class="text-center text-muted py-5"><div class="spinner-border"></div></div>';

    try {
        const qs = buildQueryString();
        const url = `${API_BASE}/projects/${projectId}/tasks/board${qs ? '?' + qs : ''}`;
        const data = await api(url);
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

    const attachmentsHtml = renderCardAttachments(task.attachments);

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
            ${attachmentsHtml}
            <div class="kanban-card-footer">
                <div class="d-flex align-items-center gap-2">
                    ${tags ? `<div class="kanban-tags">${tags}</div>` : ''}
                </div>
                <span class="kanban-created-at" title="Создано"><i class="bi bi-calendar"></i> ${formatDateTime(task.created_at)}</span>
            </div>
        </div>
    `;
}

function renderCardAttachments(attachments) {
    if (!attachments || attachments.length === 0) return '';

    const visible = attachments.slice(0, 3);
    const restCount = attachments.length - visible.length;

    const items = visible.map(a => {
        let icon = 'bi-paperclip';
        let href = '#';
        let title = escapeHtml(a.title || '');
        if (a.attachment_type === 'link') {
            icon = 'bi-link-45deg';
            href = escapeHtml(a.url || '#');
            if (!title) title = 'Ссылка';
        } else if (a.attachment_type === 'git') {
            icon = 'bi-git';
            href = escapeHtml(a.url || '#');
            if (!title) title = 'Git';
        } else if (a.attachment_type === 'file') {
            icon = 'bi-file-earmark';
            href = `/uploads/${escapeHtml(a.file_path || '')}`;
            if (!title) title = 'Файл';
        }
        return `<a href="${href}" target="_blank" rel="noopener" class="kanban-card-attachment" title="${title}" onclick="event.stopPropagation()"><i class="bi ${icon}"></i></a>`;
    }).join('');

    const more = restCount > 0
        ? `<span class="kanban-card-attachment" title="Ещё ${restCount} вложение(й)">+${restCount}</span>`
        : '';

    return `<div class="kanban-card-attachments mb-2">${items}${more}</div>`;
}

function updateTaskCardInBoard(task) {
    const card = document.querySelector(`.kanban-card[data-id="${task.id}"]`);
    if (card) {
        card.outerHTML = renderTaskCard(task);
    }
}

function initKanbanSortable() {
    kanbanSortables.forEach(s => s.destroy());
    kanbanSortables = [];

    document.querySelectorAll('.kanban-column-body').forEach(body => {
        const sortable = Sortable.create(body, {
            group: 'kanban-tasks',
            animation: 80,
            delay: 100,
            delayOnTouchOnly: true,
            scroll: false,
            swapThreshold: 0.65,
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
            animation: 80,
            handle: '.kanban-column-header',
            draggable: '.kanban-column',
            scroll: false,
            swapThreshold: 0.65,
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
    const addAttachBtn = document.getElementById('task-add-attachment-btn');
    if (addAttachBtn) addAttachBtn.disabled = !currentTaskId;
    hideAttachmentForm();

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
        renderTaskAttachments(task.attachments || []);
    } else {
        titleEl.textContent = 'Новая задача';
        form.priority.value = 'medium';
        deleteBtn.style.display = 'none';
        renderTaskAttachments([]);
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

function renderTaskAttachments(attachments) {
    const container = document.getElementById('task-attachments-list');
    if (!container) return;
    if (!currentTaskId) {
        container.innerHTML = '<span class="text-muted small">Сохраните задачу, чтобы добавить вложения</span>';
        return;
    }
    if (!attachments || attachments.length === 0) {
        container.innerHTML = '<span class="text-muted small">Нет вложений</span>';
        return;
    }
    container.innerHTML = attachments.map(a => {
        let icon = 'bi-paperclip';
        let display = escapeHtml(a.title || a.url || a.file_path || 'Вложение');
        let href = '';
        if (a.attachment_type === 'link') {
            icon = 'bi-link-45deg';
            href = escapeHtml(a.url || '#');
        } else if (a.attachment_type === 'git') {
            icon = 'bi-git';
            href = escapeHtml(a.url || '#');
        } else if (a.attachment_type === 'file') {
            icon = 'bi-file-earmark';
            href = `/uploads/${escapeHtml(a.file_path || '')}`;
        }
        const link = href
            ? `<a href="${href}" target="_blank" rel="noopener" class="text-decoration-none">${display}</a>`
            : `<span>${display}</span>`;
        return `
            <div class="d-flex align-items-center justify-content-between gap-2 p-2 border rounded mb-1">
                <div class="text-truncate">
                    <i class="bi ${icon} me-1"></i> ${link}
                </div>
                <button type="button" class="btn btn-sm btn-link text-danger p-0" onclick="deleteTaskAttachment(${a.id})" title="Удалить">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        `;
    }).join('');
}

function getCurrentTaskProjectId() {
    return PROJECT_ID;
}

function showAttachmentForm(type) {
    if (!currentTaskId) {
        alert('Сначала сохраните задачу, чтобы добавить вложение');
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
    if (!currentTaskId) return;
    const projectId = getCurrentTaskProjectId();
    if (!projectId) return;

    const type = document.getElementById('attachment-form-type').value;
    const title = document.getElementById('attachment-form-title').value.trim() || null;
    const url = document.getElementById('attachment-form-url').value.trim();

    if (type !== 'file' && !url) {
        alert('Введите URL');
        return;
    }

    try {
        await api(`${API_BASE}/projects/${projectId}/tasks/${currentTaskId}/attachments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ attachment_type: type, title, url }),
        });
        hideAttachmentForm();
        await reloadCurrentTask();
    } catch (e) {
        alert('Ошибка добавления вложения: ' + e.message);
    }
}

async function submitAttachmentFile(input) {
    if (!currentTaskId) {
        alert('Сначала сохраните задачу, чтобы добавить вложение');
        input.value = '';
        return;
    }
    const projectId = getCurrentTaskProjectId();
    if (!projectId) {
        input.value = '';
        return;
    }
    const file = input.files[0];
    if (!file) return;
    input.value = '';

    const formData = new FormData();
    formData.append('file', file);

    try {
        await api(`${API_BASE}/projects/${projectId}/tasks/${currentTaskId}/attachments/upload`, {
            method: 'POST',
            body: formData,
        });
        hideAttachmentForm();
        await reloadCurrentTask();
    } catch (e) {
        alert('Ошибка загрузки файла: ' + e.message);
    }
}

async function deleteTaskAttachment(attachmentId) {
    if (!currentTaskId) return;
    if (!confirm('Удалить вложение?')) return;

    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/${currentTaskId}/attachments/${attachmentId}`, {
            method: 'DELETE',
        });
        await reloadCurrentTask();
    } catch (e) {
        alert('Ошибка удаления вложения: ' + e.message);
    }
}

async function reloadCurrentTask() {
    if (!currentTaskId) return;
    try {
        const task = await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/${currentTaskId}`);
        renderTaskAttachments(task.attachments || []);
        const idx = kanbanData.tasks.findIndex(t => t.id === currentTaskId);
        if (idx !== -1) {
            kanbanData.tasks[idx] = task;
        }
        updateTaskCardInBoard(task);
    } catch (e) {
        console.error('Failed to reload task:', e);
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

function parseServerDate(isoString) {
    if (!isoString) return null;
    // Сервер отдаёт naive-UTC даты без Z; интерпретируем их как UTC
    if (!isoString.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(isoString)) {
        isoString += 'Z';
    }
    const date = new Date(isoString);
    return isNaN(date.getTime()) ? null : date;
}

function formatDateTime(isoString) {
    const date = parseServerDate(isoString);
    if (!date) return isoString;
    return date.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function formatDateTimeLocal(isoString) {
    const date = parseServerDate(isoString);
    if (!date) return '';
    const pad = n => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function applyFilters() {
    loadKanbanBoard(PROJECT_ID);
}

function resetFilters() {
    document.getElementById('filter-priority').value = '';
    document.getElementById('filter-assignee').value = '';
    document.getElementById('filter-tag').value = '';
    document.getElementById('filter-due-before').value = '';
    document.getElementById('filter-created-after').value = '';
    document.getElementById('filter-created-before').value = '';
    loadKanbanBoard(PROJECT_ID);
}

function priorityLabel(priority) {
    return {
        low: 'Низкий',
        medium: 'Средний',
        high: 'Высокий',
    }[priority] || priority;
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
