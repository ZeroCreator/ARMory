// ═══════════════════════════════════════════════════
// КАНБАН
// ═══════════════════════════════════════════════════

let kanbanData = { statuses: [], tasks: [] };
let filterOptions = { priorities: [], assignees: [], tags: [] };
let kanbanAssignees = [];
let kanbanDragController = null;
let currentTaskId = null;
let currentStatusId = null;
let projectName = '';
let editingTaskAttachmentId = null;
window.kanbanAttachments = window.kanbanAttachments || {};

document.addEventListener('DOMContentLoaded', async () => {
    if (typeof PROJECT_ID === 'undefined') return;
    await loadProjectHeader(PROJECT_ID);
    await loadFilters();
    await loadKanbanBoard(PROJECT_ID);
    handleTaskDeepLink();

    const board = document.getElementById('kanban-board');
    if (board) {
        board.addEventListener('contextmenu', (e) => {
            const card = e.target.closest('.kanban-card');
            if (card) {
                e.preventDefault();
                e.stopPropagation();
                const taskId = parseInt(card.dataset.id, 10);
                showTaskContextMenu(e, taskId);
            }
        });

    }
});
async function loadProjectHeader(projectId) {
    try {
        const project = await api(`${API_BASE}/projects/${projectId}`);
        projectName = project.name || '';
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
        [filterOptions, kanbanAssignees] = await Promise.all([
            api(`${API_BASE}/projects/${PROJECT_ID}/kanban/filters`),
            api(`${API_BASE}/assignees`),
        ]);
        populateSelect('filter-priority', filterOptions.priorities.map(p => ({ value: p, label: priorityLabel(p) })), 'value', 'label');
        populateSelect('filter-tag', filterOptions.tags.map(t => ({ value: t, label: t })), 'value', 'label');
        populateAssigneeSelects(kanbanAssignees);
    } catch (e) {
        console.error('Failed to load filters:', e);
    }
}

function populateAssigneeSelects(assignees) {
    const options = (assignees || []).map(a => ({
        value: a.email,
        label: a.name,
    }));
    populateSelect('filter-assignee', options, 'value', 'label');
    populateSelect('task-assignee-email', options, 'value', 'label');
}

function renderAssigneeName(email) {
    if (!email) return '';
    const assignee = kanbanAssignees.find(a => a.email === email);
    return assignee ? assignee.name : email;
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
                <div class="kanban-column-header" style="border-top-color: ${escapeHtml(status.color)}" oncontextmenu="showColumnContextMenu(event, ${status.id})">
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

    const dueDate = task.due_date && !task.is_closed
        ? `<span class="kanban-task-meta kanban-deadline-meta" title="Дедлайн"><i class="bi bi-bell"></i> ${formatDateTime(task.due_date)}</span>`
        : '';

    const assignee = task.assignee_email
        ? `<span class="kanban-task-meta" title="Ответственный"><i class="bi bi-person"></i> ${escapeHtml(renderAssigneeName(task.assignee_email))}</span>`
        : '';

    const tags = task.tags
        ? task.tags.split(',').map(t => t.trim()).filter(Boolean).map(t =>
            `<span class="kanban-tag ${task.is_closed ? 'kanban-tag-closed' : ''}">${escapeHtml(t)}</span>`
          ).join('')
        : '';

    const attachmentsHtml = renderCardAttachments(task.attachments);
    const closedClass = task.is_closed ? 'kanban-card-closed' : '';
    const closedBadge = task.is_closed ? '<span class="badge bg-secondary ms-2"><i class="bi bi-check-circle"></i> Закрыто</span>' : '';

    return `
        <div class="kanban-card ${closedClass}" data-id="${task.id}" data-status-id="${task.status_id}" onclick="handleCardClick(${task.id}, this)">
            <div class="d-flex justify-content-between align-items-center mb-1">
                <span class="badge bg-orange">#${task.id}</span>
                <span class="badge ${priorityClass} priority-badge">${priorityLabel}</span>
            </div>
            <div class="mb-2">
                <span class="kanban-card-title">${escapeHtml(task.title)}${closedBadge}</span>
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

    attachments.forEach(a => {
        window.kanbanAttachments[a.id] = { ...a, project_id: PROJECT_ID };
    });

    const typeIcons = {
        file: 'bi-file-earmark',
        git: 'bi-git',
        link: 'bi-link-45deg',
    };
    const typeLabels = {
        file: 'Файл',
        git: 'Git-репозиторий',
        link: 'Ссылка',
    };

    const types = [...new Set(attachments.map(a => a.attachment_type))];
    const icons = types.map(type => {
        const icon = typeIcons[type] || 'bi-paperclip';
        const label = typeLabels[type] || 'Вложение';
        const first = attachments.find(a => a.attachment_type === type);
        const onclick = first
            ? `event.stopPropagation(); openTaskAttachmentPreview(${first.id})`
            : '';
        return `<span class="kanban-card-attachment-type" style="cursor:pointer" title="${label}" ${onclick ? `onclick="${onclick}"` : ''}><i class="bi ${icon}"></i></span>`;
    }).join('');

    return `
        <div class="kanban-card-attachments mb-2">
            ${icons}
            <span class="kanban-card-attachment-count">${attachments.length}</span>
        </div>
    `;
}

function updateTaskCardInBoard(task) {
    const card = document.querySelector(`.kanban-card[data-id="${task.id}"]`);
    if (card) {
        card.outerHTML = renderTaskCard(task);
    }
}

function updateKanbanColumnCounts() {
    document.querySelectorAll('.kanban-column').forEach(column => {
        const count = column.querySelectorAll('.kanban-column-body .kanban-card').length;
        const badge = column.querySelector('.kanban-column-count');
        if (badge) badge.textContent = count;
    });
}

function updateLocalTaskOrder(statusId, taskIds) {
    const orderMap = new Map(taskIds.map((id, idx) => [id, idx]));
    kanbanData.tasks.forEach(task => {
        if (task.status_id === statusId && orderMap.has(task.id)) {
            task.sort_order = orderMap.get(task.id);
        }
    });
    kanbanData.tasks.sort((a, b) => {
        if (a.status_id !== b.status_id) return a.status_id - b.status_id;
        return (a.sort_order || 0) - (b.sort_order || 0);
    });
}

function handleCardClick(taskId, card) {
    if (!kanbanDragController) return;
    kanbanDragController.handleCardClick(taskId, () => {
        // Если карточка подсвечена (например, после перехода по ссылке),
        // клик только снимает подсветку, не открывая задачу повторно.
        if (card.classList.contains('kanban-card-highlighted')) {
            card.classList.remove('kanban-card-highlighted');
            return;
        }
        openTaskModal(taskId);
    });
}

function initKanbanSortable() {
    kanbanDragController = new KanbanDragController({
        boardSelector: '#kanban-board',
        group: 'kanban-tasks',
        getColumnId: (body) => parseInt(body.dataset.statusId, 10),
        onUpdateCounts: updateKanbanColumnCounts,
        onSameColumnReorder: (taskIds, statusId) => {
            updateLocalTaskOrder(statusId, taskIds);
            updateTaskStatus(null, statusId, taskIds);
        },
        onCrossColumnMove: (taskId, statusId) => {
            const columnBody = document.querySelector(`.kanban-column-body[data-status-id="${statusId}"]`);
            const taskIds = [taskId, ...Array.from(columnBody?.querySelectorAll('.kanban-card') || [])
                .map(card => parseInt(card.dataset.id, 10))
                .filter(id => id !== taskId)];
            updateLocalTaskOrder(statusId, taskIds);
            updateTaskStatus(taskId, statusId, taskIds);
        },
    });
    kanbanDragController.init();

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

async function updateTaskStatus(taskId, statusId, taskIds) {
    // Оптимистично обновляем локальные данные
    if (taskId) {
        const task = kanbanData.tasks.find(t => t.id === taskId);
        if (task) {
            task.status_id = statusId;
            task.sort_order = taskIds.indexOf(taskId);
        }
    }

    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/reorder`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status_id: statusId, task_ids: taskIds }),
        });
        updateKanbanColumnCounts();
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
    const exportBtn = document.getElementById('task-export-btn');
    const statusDisplay = document.getElementById('task-status-display');
    const statusDisplayName = document.getElementById('task-status-display-name');
    if (addAttachBtn) addAttachBtn.disabled = !currentTaskId;
    if (exportBtn) exportBtn.style.display = currentTaskId ? 'inline-block' : 'none';
    hideAttachmentForm();

    form.reset();
    document.getElementById('task-id').value = '';
    document.getElementById('task-status-id').value = defaultStatusId || '';

    const effectiveStatusId = taskId ? null : (defaultStatusId || '');
    const statusName = effectiveStatusId
        ? (kanbanData.statuses.find(s => s.id === Number(effectiveStatusId))?.name || '')
        : '';
    if (statusDisplay && statusDisplayName) {
        if (statusName) {
            statusDisplay.style.display = 'block';
            statusDisplayName.textContent = statusName;
        } else {
            statusDisplay.style.display = 'none';
            statusDisplayName.textContent = '';
        }
    }

    if (taskId) {
        const task = kanbanData.tasks.find(t => t.id === taskId);
        if (!task) return;
        titleEl.textContent = `Заявка #${task.id}`;
        document.getElementById('task-id').value = task.id;
        document.getElementById('task-status-id').value = task.status_id;
        if (statusDisplay && statusDisplayName) {
            statusDisplay.style.display = 'block';
            statusDisplayName.textContent = task.status?.name || '';
        }
        form.title.value = task.title;
        form.description.value = task.description || '';
        form.priority.value = task.priority || 'medium';
        document.getElementById('task-is-closed').checked = !!task.is_closed;
        form.due_date.value = task.due_date ? formatDateTimeLocal(task.due_date) : '';
        form.assignee_email.value = task.assignee_email || '';
        form.tags.value = task.tags || '';
        form.list_name.value = task.list_name || '';
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

    const payload = {
        title: form.title.value.trim() || null,
        description: form.description.value.trim() || null,
        priority: form.priority.value,
        is_closed: document.getElementById('task-is-closed').checked,
        due_date: form.due_date.value ? new Date(form.due_date.value).toISOString() : null,
        assignee_email: form.assignee_email.value.trim() || null,
        tags: form.tags.value.trim() || null,
        list_name: form.list_name.value.trim() || null,
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

async function exportCurrentTask() {
    if (!currentTaskId) return;
    try {
        const task = await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/${currentTaskId}/export`);
        const blob = new Blob([JSON.stringify(task, null, 2)], { type: 'application/json' });
        const filename = `task_${currentTaskId}_${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}.json`;
        downloadBlob(blob, filename);
        showToast('Задача экспортирована', 'success');
    } catch (e) {
        showToast('Ошибка экспорта: ' + e.message, 'danger');
    }
}

async function deleteTaskFromModal() {
    if (!currentTaskId) return;

    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/${currentTaskId}`, { method: 'DELETE' });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('taskModal')).hide();
        loadKanbanBoard(PROJECT_ID);
    } catch (e) {
        alert('Ошибка удаления задачи: ' + e.message);
    }
}



function getCurrentTaskProjectId() {
    return PROJECT_ID;
}

function copyTaskAttachmentUrl(url) {
    if (!url) return showToast('Ссылка пуста', 'warning');
    copyTextToClipboard(url);
    showToast('Ссылка скопирована в буфер обмена', 'success');
}

function copyTaskAttachmentById(attachmentId) {
    const attachment = window.kanbanAttachments?.[attachmentId];
    if (!attachment) return showToast('Вложение не найдено', 'warning');
    copyTaskAttachmentUrl(attachment.url);
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
    const projectId = getCurrentTaskProjectId();
    attachments.forEach(a => {
        window.kanbanAttachments[a.id] = { ...a, project_id: projectId, task_id: currentTaskId };
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
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="event.stopPropagation(); editTaskAttachment(${a.id})" title="Изменить">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="event.stopPropagation(); deleteTaskAttachment(${a.id})" title="Удалить">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function editTaskAttachment(attachmentId) {
    const attachment = window.kanbanAttachments?.[attachmentId];
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
    if (!editingTaskAttachmentId || !currentTaskId) return;
    const attachment = window.kanbanAttachments?.[editingTaskAttachmentId];
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
        await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/${currentTaskId}/attachments/${editingTaskAttachmentId}`, {
            method: 'PATCH',
            body: formData,
        });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('editTaskAttachmentModal')).hide();
        await reloadCurrentTask();
    } catch (e) {
        alert('Ошибка изменения вложения: ' + e.message);
    }
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
// ОТВЕТСТВЕННЫЕ
// ═══════════════════════════════════════════════════

function openAssigneeModal() {
    const modalEl = document.getElementById('assigneeModal');
    const form = document.getElementById('assignee-form');
    form.reset();
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

async function saveAssignee() {
    const form = document.getElementById('assignee-form');
    if (!form.name.value.trim() || !form.email.value.trim()) {
        alert('Введите имя и email');
        return;
    }

    try {
        await api(`${API_BASE}/assignees`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: form.name.value.trim(),
                email: form.email.value.trim(),
            }),
        });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('assigneeModal')).hide();
        kanbanAssignees = await api(`${API_BASE}/assignees`);
        populateAssigneeSelects(kanbanAssignees);
    } catch (e) {
        alert('Ошибка добавления ответственного: ' + e.message);
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
// КОНТЕКСТНОЕ МЕНЮ КОЛОНОК
// ═══════════════════════════════════════════════════

function getContextMenu() {
    let menu = document.getElementById('kanban-context-menu');
    if (!menu) {
        menu = document.createElement('div');
        menu.id = 'kanban-context-menu';
        menu.className = 'kanban-context-menu';
        menu.addEventListener('click', handleContextMenuClick);
        document.body.appendChild(menu);
    }
    return menu;
}

function handleContextMenuClick(e) {
    const item = e.target.closest('[data-action]');
    if (!item) return;
    e.preventDefault();
    e.stopPropagation();
    const action = item.dataset.action;
    const taskId = item.dataset.taskId ? parseInt(item.dataset.taskId, 10) : null;
    const email = item.dataset.email || '';
    if (action === 'copy-link') copyTaskLink(taskId);
    else if (action === 'assignee-submenu') showTaskAssigneeSubmenu();
    else if (action === 'set-assignee') setTaskAssignee(lastTaskContextMenuTaskId, email);
    else if (action === 'back-to-task-menu') renderTaskContextMenu(lastTaskContextMenuTaskId, lastTaskContextMenuEvent);
    else if (action === 'edit-task') editTaskFromContext(taskId);
    else if (action === 'delete-task') deleteTaskFromContext(taskId);
    else if (action === 'edit-column') editColumnFromContext(taskId);
    else if (action === 'delete-column') deleteColumnFromContext(taskId);
}

function hideContextMenu() {
    const menu = document.getElementById('kanban-context-menu');
    if (menu) menu.style.display = 'none';
}

function showColumnContextMenu(event, statusId) {
    event.preventDefault();
    const menu = getContextMenu();
    if (!statusId) {
        menu.innerHTML = `
            <div class="kanban-context-item disabled">
                <i class="bi bi-info-circle me-2"></i> Выберите проект в фильтре
            </div>
        `;
    } else {
        menu.innerHTML = `
            <button class="kanban-context-item" data-action="edit-column" data-task-id="${statusId}">
                <i class="bi bi-pencil me-2"></i> Изменить
            </button>
            <button class="kanban-context-item text-danger" data-action="delete-column" data-task-id="${statusId}">
                <i class="bi bi-trash me-2"></i> Удалить
            </button>
        `;
    }
    positionContextMenu(menu, event);
}

function positionContextMenu(menu, event) {
    menu.style.display = 'block';
    const rect = menu.getBoundingClientRect();
    let left = event.clientX;
    let top = event.clientY;
    if (left + rect.width > window.innerWidth) {
        left = window.innerWidth - rect.width - 8;
    }
    if (top + rect.height > window.innerHeight) {
        top = window.innerHeight - rect.height - 8;
    }
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
}

function editColumnFromContext(statusId) {
    hideContextMenu();
    openStatusModal(statusId);
}

function deleteColumnFromContext(statusId) {
    hideContextMenu();
    currentStatusId = statusId;
    deleteStatusFromModal();
}

document.addEventListener('click', (e) => {
    const menu = document.getElementById('kanban-context-menu');
    if (menu && !menu.contains(e.target)) {
        hideContextMenu();
    }
});

// ═══════════════════════════════════════════════════
// КОНТЕКСТНОЕ МЕНЮ ЗАДАЧ
// ═══════════════════════════════════════════════════

let lastTaskContextMenuEvent = null;
let lastTaskContextMenuTaskId = null;

function showTaskContextMenu(event, taskId) {
    event.preventDefault();
    event.stopPropagation();
    lastTaskContextMenuEvent = event;
    lastTaskContextMenuTaskId = taskId;
    renderTaskContextMenu(taskId, event);
}

function renderTaskContextMenu(taskId, event) {
    const menu = getContextMenu();
    menu.innerHTML = `
        <button class="kanban-context-item" data-action="copy-link" data-task-id="${taskId}">
            <i class="bi bi-link-45deg me-2"></i> Ссылка на задачу
        </button>
        <button class="kanban-context-item" data-action="assignee-submenu">
            <i class="bi bi-person me-2"></i> Установить ответственного
        </button>
        <button class="kanban-context-item" data-action="edit-task" data-task-id="${taskId}">
            <i class="bi bi-pencil me-2"></i> Редактировать
        </button>
        <button class="kanban-context-item text-danger" data-action="delete-task" data-task-id="${taskId}">
            <i class="bi bi-trash me-2"></i> Удалить
        </button>
    `;
    positionContextMenu(menu, event);
}

function showTaskAssigneeSubmenu() {
    const taskId = lastTaskContextMenuTaskId;
    const menu = getContextMenu();
    const options = (kanbanAssignees || []).map(a => `
        <button class="kanban-context-item" data-action="set-assignee" data-email="${escapeHtml(a.email)}">
            ${escapeHtml(a.name)}
        </button>
    `).join('');
    menu.innerHTML = `
        <button class="kanban-context-item" data-action="back-to-task-menu">
            <i class="bi bi-arrow-left me-2"></i> Назад
        </button>
        <div class="kanban-context-divider"></div>
        <button class="kanban-context-item" data-action="set-assignee" data-email="">
            Не назначен
        </button>
        ${options}
    `;
}

async function setTaskAssignee(taskId, email) {
    hideContextMenu();
    try {
        const updatedTask = await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/${taskId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ assignee_email: email || null }),
        });
        const idx = kanbanData.tasks.findIndex(t => t.id === taskId);
        if (idx !== -1) {
            kanbanData.tasks[idx] = updatedTask;
        }
        updateTaskCardInBoard(updatedTask);
    } catch (e) {
        alert('Ошибка установки ответственного: ' + e.message);
    }
}

function copyTaskLink(taskId) {
    const url = `${window.location.origin}/projects/${PROJECT_ID}/kanban?task=${taskId}`;
    copyTextToClipboard(url);
    showToast('Ссылка скопирована в буфер обмена');
    hideContextMenu();
}

function editTaskFromContext(taskId) {
    hideContextMenu();
    openTaskModal(taskId);
}

async function deleteTaskFromContext(taskId) {
    hideContextMenu();
    if (!confirm('Удалить задачу?')) return;
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/${taskId}`, { method: 'DELETE' });
        loadKanbanBoard(PROJECT_ID);
    } catch (e) {
        alert('Ошибка удаления задачи: ' + e.message);
    }
}

function handleTaskDeepLink() {
    const params = new URLSearchParams(window.location.search);
    const taskId = params.get('task');
    if (!taskId) return;
    history.replaceState(null, '', window.location.pathname);
    const card = document.querySelector(`.kanban-card[data-id="${taskId}"]`);
    if (card) {
        card.classList.add('kanban-card-highlighted');
    }
    openTaskModal(parseInt(taskId, 10));
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

// ═══════════════════════════════════════════════════
// ИМПОРТ ЗАДАЧ
// ═══════════════════════════════════════════════════

let importTasksState = [];
let importBulkAttachments = [];
let importNextTempId = 1;

function resetImportState() {
    importTasksState = [];
    importBulkAttachments = [];
    importNextTempId = 1;
    document.getElementById('import-todo-text').value = '';
    document.getElementById('import-bulk-due-date').value = '';
    document.getElementById('import-bulk-priority').value = 'medium';
    document.getElementById('import-bulk-assignee').value = '';
    document.getElementById('import-bulk-tags').value = '';
    hideImportBulkAttachmentForm();
    renderImportTasksList();
    renderImportBulkAttachmentsList();
}

function openTaskImportModal() {
    resetImportState();
    populateSelect('import-bulk-assignee', kanbanAssignees.map(a => ({ value: a.email, label: a.name })), 'value', 'label');
    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('taskImportModal'));
    modal.show();
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

function showImportBulkAttachmentForm(type) {
    const form = document.getElementById('import-bulk-attachment-form');
    const typeInput = document.getElementById('import-bulk-attachment-type');
    const titleInput = document.getElementById('import-bulk-attachment-title');
    const urlInput = document.getElementById('import-bulk-attachment-url');
    const urlWrap = document.getElementById('import-bulk-attachment-url-wrap');

    typeInput.value = type;
    titleInput.value = '';
    urlInput.value = '';
    urlWrap.style.display = type === 'file' ? 'none' : 'block';
    urlInput.placeholder = type === 'git' ? 'URL репозитория' : 'URL';
    form.style.display = 'block';
}

function hideImportBulkAttachmentForm() {
    const form = document.getElementById('import-bulk-attachment-form');
    if (form) form.style.display = 'none';
}

function submitImportBulkAttachmentForm() {
    const type = document.getElementById('import-bulk-attachment-type').value;
    const title = document.getElementById('import-bulk-attachment-title').value.trim() || null;
    const url = document.getElementById('import-bulk-attachment-url').value.trim();

    if (type !== 'file' && !url) {
        alert('Введите URL');
        return;
    }

    importBulkAttachments.push({ attachment_type: type, title, url });
    hideImportBulkAttachmentForm();
    renderImportBulkAttachmentsList();
}

async function submitImportBulkAttachmentFile(input) {
    const file = input.files[0];
    if (!file) return;
    input.value = '';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const attachment = await api(`${API_BASE}/projects/${PROJECT_ID}/attachments/upload`, {
            method: 'POST',
            body: formData,
        });
        importBulkAttachments.push({
            attachment_type: 'file',
            title: attachment.title || file.name,
            file_path: attachment.file_path,
        });
        renderImportBulkAttachmentsList();
    } catch (e) {
        alert('Ошибка загрузки файла: ' + e.message);
    }
}

function deleteImportBulkAttachment(index) {
    importBulkAttachments.splice(index, 1);
    renderImportBulkAttachmentsList();
}

function renderImportBulkAttachmentsList() {
    const container = document.getElementById('import-bulk-attachments-list');
    if (!container) return;
    if (importBulkAttachments.length === 0) {
        container.innerHTML = '<span class="text-muted small">Нет вложений</span>';
        return;
    }

    container.innerHTML = importBulkAttachments.map((a, idx) => {
        const icon = a.attachment_type === 'git' ? 'bi-git' : (a.attachment_type === 'link' ? 'bi-link-45deg' : 'bi-file-earmark');
        const display = escapeHtml(a.title || a.url || a.file_path || 'Вложение');
        return `
            <div class="d-flex align-items-center justify-content-between gap-2 p-2 border rounded mb-1">
                <div class="text-truncate">
                    <i class="bi ${icon} me-1"></i> ${display}
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="deleteImportBulkAttachment(${idx})" title="Удалить"><i class="bi bi-trash"></i></button>
            </div>
        `;
    }).join('');
}

function applyBulkToSelectedImportTasks() {
    const dueDate = document.getElementById('import-bulk-due-date').value || null;
    const priority = document.getElementById('import-bulk-priority').value || null;
    const assignee = document.getElementById('import-bulk-assignee').value || null;
    const tags = document.getElementById('import-bulk-tags').value.trim() || null;

    importTasksState.forEach(t => {
        if (!t.selected) return;
        if (dueDate) t.due_date = new Date(dueDate).toISOString();
        if (priority) t.priority = priority;
        if (assignee) t.assignee_email = assignee;
        if (tags) t.tags = tags;
    });

    showToast('Массовые настройки применены к выбранным задачам', 'success');
    renderImportTasksList();
}

async function createTasksBulk() {
    const validTasks = importTasksState.filter(t => t.title.trim() || t.description.trim());
    if (validTasks.length === 0) {
        alert('Нет задач для создания');
        return;
    }

    const payload = {
        tasks: validTasks.map(t => ({
            title: t.title.trim() || null,
            description: t.description.trim() || null,
            priority: t.priority || 'medium',
            due_date: t.due_date,
            assignee_email: t.assignee_email,
            tags: t.tags,
        })),
        attachments: importBulkAttachments,
    };

    try {
        const result = await api(`${API_BASE}/projects/${PROJECT_ID}/tasks/bulk`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('taskImportModal')).hide();
        showToast(`Создано задач: ${result.count}`, 'success');
        loadKanbanBoard(PROJECT_ID);
    } catch (e) {
        alert('Ошибка создания задач: ' + e.message);
    }
}

async function exportProjectKanban() {
    try {
        const data = await api(`${API_BASE}/projects/${PROJECT_ID}/kanban/export`);
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const safeName = (projectName || `project_${PROJECT_ID}`).replace(/[^a-zA-Z0-9а-яА-Я._-]/g, '_');
        const dt = new Date().toISOString().slice(0, 16).replace('T', '_').replace(/:/g, '-');
        a.download = `kanban_${safeName}_${dt}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('Ошибка экспорта канбана проекта: ' + e.message);
    }
}

async function importProjectKanban(input) {
    const file = input.files[0];
    if (!file) return;
    input.value = '';

    if (!confirm('Импорт заменит существующие колонки и задачи с совпадающими названиями в этом проекте. Продолжить?')) {
        return;
    }

    try {
        const text = await file.text();
        const data = JSON.parse(text);
        const result = await api(`${API_BASE}/projects/${PROJECT_ID}/kanban/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        alert(`Импорт завершён. Колонок: ${result.imported_statuses}, задач: ${result.imported_tasks}`);
        loadKanbanBoard(PROJECT_ID);
    } catch (e) {
        alert('Ошибка импорта канбана проекта: ' + e.message);
    }
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
