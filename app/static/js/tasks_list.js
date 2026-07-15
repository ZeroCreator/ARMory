// ═══════════════════════════════════════════════════
// СПИСОК ЗАДАЧ (ТАБЛИЦА)
// ═══════════════════════════════════════════════════

let allTasks = [];
let filteredTasks = [];
let filterOptions = { projects: [], priorities: [], assignees: [], tags: [], list_names: [] };
let assigneesMap = {};
let projectsMap = {};
let sortColumn = 'created_at';
let sortDirection = 'desc';

const SAVE_LIST_COLUMNS = [
    { key: 'id', label: '#', default: true },
    { key: 'project_name', label: 'Проект', default: true, globalOnly: true },
    { key: 'title', label: 'Название', default: true },
    { key: 'description', label: 'Описание', default: true },
    { key: 'status_name', label: 'Статус', default: true },
    { key: 'priority', label: 'Приоритет', default: true },
    { key: 'assignee_name', label: 'Ответственный', default: true },
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
    if (!IS_GLOBAL) {
        await loadProjectHeader(PROJECT_ID);
    } else {
        document.getElementById('tasks-list-title').innerHTML = '<i class="bi bi-list-task"></i> Все задачи';
    }
    await loadFilters();
    await loadTasks();
});

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
        populateSelect('import-bulk-assignee', (filterOptions.assignees || []).map(a => ({ value: a.email, label: a.name })));
    } catch (e) {
        console.error('Failed to load filters:', e);
    }
}

function populateSelect(id, items) {
    const select = document.getElementById(id);
    if (!select) return;
    const currentValue = select.value;
    const defaultText = select.options[0]?.text || 'Все';
    select.innerHTML = `<option value="">${defaultText}</option>` +
        items.map(item => `<option value="${escapeHtml(String(item.value))}">${escapeHtml(String(item.label))}</option>`).join('');
    select.value = currentValue;
}

async function loadTasks() {
    const tbody = document.getElementById('tasks-table-body');
    tbody.innerHTML = '<tr><td colspan="13" class="text-center text-muted py-4">Загрузка...</td></tr>';
    try {
        const url = IS_GLOBAL ? `${API_BASE}/tasks` : `${API_BASE}/projects/${PROJECT_ID}/tasks`;
        allTasks = await api(url);
        rebuildStatusFilter();
        applyFilters();
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="13" class="text-center text-danger py-4">Ошибка загрузки: ${escapeHtml(e.message)}</td></tr>`;
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
        if (assignee && t.assignee_email !== assignee) return false;
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
        case 'assignee_name': return assigneesMap[task.assignee_email] || task.assignee_email || '';
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
        const colspan = IS_GLOBAL ? 13 : 12;
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
            <tr class="${task.is_closed ? 'table-secondary' : ''}">
                <td>${task.id}</td>
                ${projectCell}
                <td>${escapeHtml(task.title || '')}</td>
                <td class="d-none d-md-table-cell description-cell" title="${escapeHtml(task.description || '')}">${escapeHtml(task.description || '')}</td>
                <td>${escapeHtml(task.status?.name || '')}</td>
                <td><span class="badge ${priorityClass}">${priorityLabel(task.priority)}</span></td>
                <td class="d-none d-sm-table-cell">${escapeHtml(assigneesMap[task.assignee_email] || task.assignee_email || '—')}</td>
                <td class="d-none d-sm-table-cell">${task.due_date ? formatDateTime(task.due_date) : '—'}</td>
                <td class="d-none d-lg-table-cell">${tags || '—'}</td>
                <td class="d-none d-sm-table-cell">${escapeHtml(task.list_name || '—')}</td>
                <td class="d-none d-lg-table-cell">${formatDateTime(task.created_at)}</td>
                <td class="d-none d-sm-table-cell">${task.is_closed ? '<i class="bi bi-check-circle text-success"></i>' : '—'}</td>
                <td class="actions-cell">
                    <a href="${kanbanUrl}" class="btn btn-sm btn-outline-brown" title="Открыть в канбане"><i class="bi bi-kanban"></i></a>
                    <button class="btn btn-sm btn-outline-secondary" onclick="copyTaskLink(${task.project_id}, ${task.id})" title="Копировать ссылку"><i class="bi bi-link-45deg"></i></button>
                </td>
            </tr>
        `;
    }).join('');

    setupTopScroll();
}

function copyTaskLink(projectId, taskId) {
    const url = `${window.location.origin}/projects/${projectId}/kanban?task=${taskId}`;
    copyTextToClipboard(url);
    showToast('Ссылка скопирована', 'success');
}

function exportTasks(format) {
    if (filteredTasks.length === 0) {
        alert('Нет задач для экспорта');
        return;
    }
    const rows = filteredTasks.map(t => ({
        id: t.id,
        project: IS_GLOBAL ? (projectsMap[t.project_id] || t.project_id) : undefined,
        title: t.title,
        description: t.description,
        status: t.status?.name,
        priority: t.priority,
        assignee: assigneesMap[t.assignee_email] || t.assignee_email,
        due_date: t.due_date,
        tags: t.tags,
        list_name: t.list_name,
        created_at: t.created_at,
        is_closed: t.is_closed,
    }));

    if (format === 'json') {
        const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
        downloadBlob(blob, `tasks_${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}.json`);
    } else if (format === 'csv') {
        const headers = Object.keys(rows[0]).filter(k => k !== 'project' || IS_GLOBAL);
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
        downloadBlob(blob, `tasks_${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}.csv`);
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
        case 'assignee_name': return assigneesMap[task.assignee_email] || task.assignee_email || '—';
        case 'due_date': return task.due_date ? formatDateTime(task.due_date) : '—';
        case 'tags': return task.tags || '—';
        case 'list_name': return task.list_name || '—';
        case 'created_at': return task.created_at ? formatDateTime(task.created_at) : '—';
        case 'is_closed': return task.is_closed ? 'Закрыто' : 'Открыто';
        default: return '';
    }
}

function renderSaveListText() {
    const textArea = document.getElementById('save-list-text');
    if (!textArea) return;

    const selectedKeys = Array.from(document.querySelectorAll('#save-list-columns input:checked')).map(cb => cb.value);
    if (selectedKeys.length === 0) {
        textArea.value = 'Выберите хотя бы одну колонку';
        return;
    }
    if (filteredTasks.length === 0) {
        textArea.value = 'Нет задач для сохранения';
        return;
    }

    const format = document.getElementById('save-list-format')?.value || 'todo';
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
        textArea.value = [header, separator, ...rows].join('\n');
        return;
    }

    if (format === 'oneline') {
        const rows = filteredTasks.map(task => {
            return selectedColumns.map(col => {
                const v = getSaveListColumnValue(task, col.key);
                return String(v).replace(/\n/g, ' ');
            }).join(' | ');
        });
        textArea.value = rows.join('\n');
        return;
    }

    const titleColumn = selectedColumns.find(col => col.key === 'title');
    const detailColumns = selectedColumns.filter(col => col.key !== 'title');
    const lines = [];

    filteredTasks.forEach((task, idx) => {
        const title = getSaveListColumnValue(task, 'title');
        const titlePart = titleColumn ? (title === `Заявка #${task.id}` ? '' : ' ' + title) : '';

        if (format === 'todo') {
            lines.push(`- [ ] #${task.id}${titlePart}`.trim());
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

    textArea.value = lines.join('\n');
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
// ИМПОРТ ЗАДАЧ ИЗ TODO-СПИСКА
// ═══════════════════════════════════════════════════

function resetImportState() {
    importTasksState = [];
    importBulkAttachments = [];
    importNextTempId = 1;
    document.getElementById('import-list-name').value = '';
    document.getElementById('import-todo-text').value = '';
    document.getElementById('import-bulk-due-date').value = '';
    document.getElementById('import-bulk-priority').value = 'medium';
    document.getElementById('import-bulk-assignee').value = '';
    document.getElementById('import-bulk-tags').value = '';
    if (document.getElementById('import-bulk-project')) document.getElementById('import-bulk-project').value = '';
    hideImportBulkAttachmentForm();
    renderImportTasksList();
    renderImportBulkAttachmentsList();
}

function openTaskImportModal() {
    resetImportState();
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
            project_id: null,
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

    const projectId = getImportProjectId();
    if (!projectId) {
        alert('Выберите проект для загрузки файла');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const attachment = await api(`${API_BASE}/projects/${projectId}/attachments/upload`, {
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

function getImportProjectId() {
    if (!IS_GLOBAL) return PROJECT_ID;
    const select = document.getElementById('import-bulk-project');
    return select ? (select.value || (filterOptions.projects[0]?.id)) : null;
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
    const projectId = getImportProjectId();

    importTasksState.forEach(t => {
        if (!t.selected) return;
        if (IS_GLOBAL && projectId) t.project_id = parseInt(projectId, 10);
        if (dueDate) t.due_date = new Date(dueDate).toISOString();
        if (priority) t.priority = priority;
        if (assignee) t.assignee_email = assignee;
        if (tags) t.tags = tags;
    });

    showToast('Массовые настройки применены к выбранным задачам', 'success');
    renderImportTasksList();
}

async function createTasksBulk() {
    const listName = document.getElementById('import-list-name').value.trim();
    if (!listName) {
        alert('Введите название списка');
        return;
    }

    const validTasks = importTasksState.filter(t => t.title.trim() || t.description.trim());
    if (validTasks.length === 0) {
        alert('Нет задач для создания');
        return;
    }

    if (IS_GLOBAL) {
        const withoutProject = validTasks.filter(t => !t.project_id);
        if (withoutProject.length > 0) {
            alert('Укажите проект для всех задач (через массовое редактирование)');
            return;
        }
    }

    const payload = {
        tasks: validTasks.map(t => ({
            title: t.title.trim() || null,
            description: t.description.trim() || null,
            priority: t.priority || 'medium',
            due_date: t.due_date,
            assignee_email: t.assignee_email,
            tags: t.tags,
            list_name: listName,
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
        alert('Ошибка создания задач: ' + e.message);
    }
}
