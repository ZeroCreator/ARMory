// ═══════════════════════════════════════════════════
// ОБЩИЙ КАНБАН
// ═══════════════════════════════════════════════════

let kanbanData = { columns: [], tasks: [] };
let filterOptions = { projects: [], priorities: [], assignees: [], tags: [] };
let kanbanAssignees = [];
let projectStatuses = {};
let kanbanSortables = [];
let currentTaskId = null;
let currentStatusId = null;
let editingTaskAttachmentId = null;
window.kanbanAttachments = window.kanbanAttachments || {};

document.addEventListener('DOMContentLoaded', async () => {
    await loadFilters();
    await loadKanbanBoard();
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
        board.addEventListener('click', (e) => {
            const card = e.target.closest('.kanban-card');
            if (card) {
                document.querySelectorAll('.kanban-card-highlighted').forEach(c => {
                    c.classList.remove('kanban-card-highlighted');
                });
            }
        });
    }
});

async function loadFilters() {
    try {
        [filterOptions, kanbanAssignees] = await Promise.all([
            api(`${API_BASE}/kanban/filters`),
            api(`${API_BASE}/assignees`),
        ]);
        populateSelect('filter-project', filterOptions.projects, 'id', 'name');
        populateSelect('filter-priority', filterOptions.priorities.map(p => ({ value: p, label: priorityLabel(p) })), 'value', 'label');
        populateSelect('filter-tag', filterOptions.tags.map(t => ({ value: t, label: t })), 'value', 'label');

        populateSelect('task-project-id', filterOptions.projects, 'id', 'name');
        populateSelect('status-project-id', filterOptions.projects, 'id', 'name');

        populateAssigneeSelects(kanbanAssignees);
        await loadAllProjectStatuses();
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
            <div class="kanban-column" data-name="${escapeHtml(column.name)}" data-column-name="${escapeHtml(column.name)}">
                <div class="kanban-column-header" style="border-top-color: ${escapeHtml(column.color)}" oncontextmenu="showColumnContextMenu(event, '${escapeHtml(column.name)}')">
                    <span class="kanban-column-title">${escapeHtml(column.name)}</span>
                    <span class="badge bg-secondary rounded-pill kanban-column-count">${tasks.length}</span>
                </div>
                <div class="kanban-column-body" data-column-name="${escapeHtml(column.name)}">
                    ${tasks.map(task => renderTaskCard(task)).join('')}
                </div>
                <div class="kanban-column-footer">
                    <button class="btn btn-sm btn-outline-brown w-100" onclick="openTaskModal(null)">
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
        ? `<span class="kanban-task-meta" title="Ответственный"><i class="bi bi-person"></i> ${escapeHtml(renderAssigneeName(task.assignee_email))}</span>`
        : '';

    const tags = task.tags
        ? task.tags.split(',').map(t => t.trim()).filter(Boolean).map(t =>
            `<span class="kanban-tag">${escapeHtml(t)}</span>`
          ).join('')
        : '';

    const attachmentsHtml = renderCardAttachments(task.attachments, task);

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

function renderCardAttachments(attachments, task) {
    if (!attachments || attachments.length === 0) return '';

    const projectId = task ? task.project_id : null;
    const taskId = task ? task.id : null;
    attachments.forEach(a => {
        window.kanbanAttachments[a.id] = { ...a, project_id: projectId, task_id: taskId };
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

function initKanbanSortable() {
    kanbanSortables.forEach(s => s.destroy());
    kanbanSortables = [];

    document.querySelectorAll('.kanban-column-body').forEach(body => {
        const sortable = Sortable.create(body, {
            group: 'kanban-global-tasks',
            animation: 80,
            delay: 100,
            delayOnTouchOnly: true,
            scroll: false,
            swapThreshold: 0.65,
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            onEnd: function (evt) {
                const taskId = parseInt(evt.item.dataset.id, 10);
                const columnName = evt.to.dataset.columnName;
                updateKanbanColumnCounts();
                updateTaskColumn(taskId, columnName);
            },
        });
        kanbanSortables.push(sortable);
    });
}

async function updateTaskColumn(taskId, columnName) {
    try {
        const updatedTask = await api(`${API_BASE}/kanban/tasks/${taskId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ column_name: columnName }),
        });
        const idx = kanbanData.tasks.findIndex(t => t.id === taskId);
        if (idx !== -1) {
            kanbanData.tasks[idx] = updatedTask;
        }
        updateKanbanColumnCounts();
    } catch (e) {
        alert('Ошибка перемещения задачи: ' + e.message);
        loadKanbanBoard();
    }
}

// ═══════════════════════════════════════════════════
// ЗАДАЧИ
// ═══════════════════════════════════════════════════

function openTaskModal(taskId, defaultProjectId) {
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

function getCurrentTaskProjectId() {
    if (!currentTaskId) return null;
    const task = kanbanData.tasks.find(t => t.id === currentTaskId);
    return task ? task.project_id : null;
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
            actionBtn = `<a href="${escapeHtml(a.url || '#')}" target="_blank" class="btn btn-sm btn-outline-brown" title="Открыть" onclick="event.stopPropagation()"><i class="bi bi-box-arrow-up-right"></i></a>`;
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
    const projectId = getCurrentTaskProjectId();
    if (!projectId) return;
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
        await api(`${API_BASE}/projects/${projectId}/tasks/${currentTaskId}/attachments/${editingTaskAttachmentId}`, {
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
    const projectId = getCurrentTaskProjectId();
    if (!projectId) return;
    if (!confirm('Удалить вложение?')) return;

    try {
        await api(`${API_BASE}/projects/${projectId}/tasks/${currentTaskId}/attachments/${attachmentId}`, {
            method: 'DELETE',
        });
        await reloadCurrentTask();
    } catch (e) {
        alert('Ошибка удаления вложения: ' + e.message);
    }
}

async function reloadCurrentTask() {
    if (!currentTaskId) return;
    const projectId = getCurrentTaskProjectId();
    if (!projectId) return;
    try {
        const task = await api(`${API_BASE}/projects/${projectId}/tasks/${currentTaskId}`);
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

function openStatusModal(columnName) {
    currentStatusId = columnName || null;
    const modalEl = document.getElementById('statusModal');
    const form = document.getElementById('status-form');
    const titleEl = document.getElementById('status-modal-title');
    const deleteBtn = document.getElementById('status-delete-btn');

    form.reset();
    document.getElementById('status-id').value = '';

    if (columnName) {
        const column = kanbanData.columns.find(c => c.name === columnName);
        if (!column) return;
        titleEl.textContent = 'Редактировать колонку';
        document.getElementById('status-id').value = column.name;
        form.name.value = column.name;
        form.color.value = column.color;
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

        const name = form.name.value.trim();
        const color = form.color.value;

        if (currentStatusId) {
            const payload = {};
            if (name !== currentStatusId) payload.new_name = name;
            if (color) payload.color = color;
            if (Object.keys(payload).length > 0) {
                await api(`${API_BASE}/kanban/columns/${encodeURIComponent(currentStatusId)}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
            }
        } else {
            await api(`${API_BASE}/kanban/columns`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, color }),
            });
        }
        bootstrap.Modal.getOrCreateInstance(document.getElementById('statusModal')).hide();
        await loadFilters();
        loadKanbanBoard();
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
    const column = kanbanData.columns.find(c => c.name === currentStatusId);
    if (!column) return;
    const hasTasks = kanbanData.tasks.some(t => t.status && t.status.name === currentStatusId);
    if (hasTasks) {
        alert('Нельзя удалить колонку с задачами. Переместите или удалите задачи сначала.');
        return;
    }
    if (!confirm(`Удалить колонку "${column.name}"?`)) return;

    try {
        await api(`${API_BASE}/kanban/columns/${encodeURIComponent(currentStatusId)}`, { method: 'DELETE' });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('statusModal')).hide();
        await loadFilters();
        loadKanbanBoard();
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
    const columnName = item.dataset.columnName || '';
    const email = item.dataset.email || '';
    if (action === 'copy-link') copyTaskLink(taskId);
    else if (action === 'assignee-submenu') showTaskAssigneeSubmenu();
    else if (action === 'set-assignee') setTaskAssignee(lastTaskContextMenuTaskId, email);
    else if (action === 'back-to-task-menu') renderTaskContextMenu(lastTaskContextMenuTaskId, lastTaskContextMenuEvent);
    else if (action === 'edit-task') editTaskFromContext(taskId);
    else if (action === 'delete-task') deleteTaskFromContext(taskId);
    else if (action === 'edit-column') editColumnFromContext(columnName);
    else if (action === 'delete-column') deleteColumnFromContext(columnName);
}

function hideContextMenu() {
    const menu = document.getElementById('kanban-context-menu');
    if (menu) menu.style.display = 'none';
}

function showColumnContextMenu(event, columnName) {
    event.preventDefault();
    const menu = getContextMenu();
    const safeName = escapeHtml(columnName);
    menu.innerHTML = `
        <button class="kanban-context-item" data-action="edit-column" data-column-name="${safeName}">
            <i class="bi bi-pencil me-2"></i> Изменить
        </button>
        <button class="kanban-context-item text-danger" data-action="delete-column" data-column-name="${safeName}">
            <i class="bi bi-trash me-2"></i> Удалить
        </button>
    `;
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

function editColumnFromContext(columnName) {
    hideContextMenu();
    openStatusModal(columnName);
}

function deleteColumnFromContext(columnName) {
    hideContextMenu();
    currentStatusId = columnName;
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
    const task = kanbanData.tasks.find(t => t.id === taskId);
    if (!task) return;
    try {
        await api(`${API_BASE}/projects/${task.project_id}/tasks/${taskId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ assignee_email: email || null }),
        });
        loadKanbanBoard();
    } catch (e) {
        alert('Ошибка установки ответственного: ' + e.message);
    }
}

function copyTaskLink(taskId) {
    const task = kanbanData.tasks.find(t => t.id === taskId);
    const projectId = task ? task.project_id : null;
    const url = projectId
        ? `${window.location.origin}/projects/${projectId}/kanban?task=${taskId}`
        : `${window.location.origin}/kanban?task=${taskId}`;
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
    const task = kanbanData.tasks.find(t => t.id === taskId);
    if (!task) return;
    if (!confirm('Удалить задачу?')) return;
    try {
        await api(`${API_BASE}/projects/${task.project_id}/tasks/${taskId}`, { method: 'DELETE' });
        loadKanbanBoard();
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
        const dt = new Date().toISOString().slice(0, 16).replace('T', '_').replace(/:/g, '-');
        a.download = `kanban_export_${dt}.json`;
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
