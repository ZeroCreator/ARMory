let timeTasks = [];
let displayedTimeTasks = [];
let timeProjects = {};
let timeFilterOptions = {};
let timeSort = { key: 'created_at', direction: 'desc' };
let editingTimeTaskId = null;
let contextTimeTaskId = null;

document.addEventListener('DOMContentLoaded', async () => {
    document.getElementById('task-time-edit-form').addEventListener('submit', saveTaskTimeValues);
    document.getElementById('task-time-table-body').addEventListener('contextmenu', showTaskTimeContextMenu);
    document.getElementById('task-time-context-menu').addEventListener('click', handleTaskTimeContextAction);
    document.addEventListener('click', hideTaskTimeContextMenu);
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') hideTaskTimeContextMenu();
    });
    document.addEventListener('scroll', hideTaskTimeContextMenu, true);
    window.addEventListener('resize', hideTaskTimeContextMenu);
    await loadTaskTimeData();
    window.setInterval(loadTaskTimeData, 60000);
});

async function loadTaskTimeData() {
    const tableBody = document.getElementById('task-time-table-body');
    try {
        const taskUrl = IS_GLOBAL ? '/api/tasks' : `/api/projects/${PROJECT_ID}/tasks`;
        const filterUrl = IS_GLOBAL ? '/api/kanban/filters' : `/api/projects/${PROJECT_ID}/kanban/filters`;
        const [tasksResponse, projectsResponse, filterResponse] = await Promise.all([
            fetch(taskUrl, { credentials: 'same-origin' }),
            fetch('/api/projects', { credentials: 'same-origin' }),
            fetch(filterUrl, { credentials: 'same-origin' }),
        ]);
        if (!tasksResponse.ok) throw new Error(await tasksResponse.text());
        if (!projectsResponse.ok) throw new Error(await projectsResponse.text());
        if (!filterResponse.ok) throw new Error(await filterResponse.text());
        timeTasks = await tasksResponse.json();
        const projects = await projectsResponse.json();
        timeFilterOptions = await filterResponse.json();
        timeProjects = Object.fromEntries(projects.map(project => [project.id, project.name]));
        allTasks = timeTasks;
        projectsMap = timeProjects;
        filterOptions = timeFilterOptions;
        assigneesMap = Object.fromEntries((timeFilterOptions.assignees || []).map(assignee => [assignee.email, assignee.name]));
        populateTimeFilters();
        applyTimeFilters();
    } catch (error) {
        displayedTimeTasks = [];
        const exportButton = document.getElementById('task-time-export-xlsx');
        if (exportButton) exportButton.disabled = true;
        tableBody.innerHTML = `<tr><td colspan="${IS_GLOBAL ? 9 : 8}" class="text-center text-danger py-4">${escapeTimeHtml(error.message)}</td></tr>`;
    }
}

function populateTimeFilters() {
    const statusSelect = document.getElementById('time-filter-status');
    const statuses = [...new Set(timeTasks.filter(task => !task.is_closed).map(task => task.status?.name).filter(Boolean))]
        .sort((a, b) => a.localeCompare(b, 'ru'));
    populateTimeSelect(statusSelect, statuses.map(status => ({ value: status, label: status })), 'Все статусы');

    const projectSelect = document.getElementById('time-filter-project');
    if (projectSelect) {
        const projects = [...new Set(timeTasks.filter(task => !task.is_closed).map(task => task.project_id))]
            .map(id => ({ value: id, label: timeProjects[id] || `Проект #${id}` }))
            .sort((a, b) => a.label.localeCompare(b.label, 'ru'));
        populateTimeSelect(projectSelect, projects, 'Все проекты');
    }

    populateTimeSelect(
        document.getElementById('time-filter-priority'),
        (timeFilterOptions.priorities || []).map(priority => ({
            value: priority,
            label: ({ low: 'Низкий', medium: 'Средний', high: 'Высокий' })[priority] || priority,
        })),
    );
    populateTimeSelect(
        document.getElementById('time-filter-assignee'),
        (timeFilterOptions.assignees || []).map(assignee => ({ value: assignee.email, label: assignee.name })),
    );
    populateTimeSelect(
        document.getElementById('time-filter-list'),
        (timeFilterOptions.list_names || []).map(list => ({ value: list, label: list })),
    );

    populateTagFilterOptions('time-filter-tags', timeFilterOptions.tags);
}

function populateTimeSelect(select, options, defaultLabel = 'Все') {
    const previousValue = select.value;
    select.innerHTML = `<option value="">${escapeTimeHtml(defaultLabel)}</option>` + options.map(option =>
        `<option value="${escapeTimeHtml(String(option.value))}">${escapeTimeHtml(String(option.label))}</option>`
    ).join('');
    select.value = previousValue;
}

function applyTimeFilters() {
    const search = document.getElementById('time-filter-search').value.trim().toLocaleLowerCase('ru');
    const status = document.getElementById('time-filter-status').value;
    const project = document.getElementById('time-filter-project')?.value || '';
    const priority = document.getElementById('time-filter-priority').value;
    const assignee = document.getElementById('time-filter-assignee').value;
    const listName = document.getElementById('time-filter-list').value;
    const tags = document.getElementById('time-filter-tags').value.trim();
    const dueBefore = document.getElementById('time-filter-due-before').value;
    const createdAfter = document.getElementById('time-filter-created-after').value;
    const createdBefore = document.getElementById('time-filter-created-before').value;
    const filtered = timeTasks.filter(task => {
        if (task.is_closed) return false;
        if (!hasTimeValues(task)) return false;
        if (status && task.status?.name !== status) return false;
        if (project && String(task.project_id) !== project) return false;
        if (priority && task.priority !== priority) return false;
        if (assignee && !(task.assignee_emails || [task.assignee_email]).includes(assignee)) return false;
        if (listName && task.list_name !== listName) return false;
        const taskCreated = String(task.created_at || '').slice(0, 10);
        if (createdAfter && taskCreated < createdAfter) return false;
        if (createdBefore && taskCreated > createdBefore) return false;
        const taskDue = String(task.due_date || '').slice(0, 10);
        if (dueBefore && (!taskDue || taskDue > dueBefore)) return false;
        if (search) {
            const haystack = `${task.title || ''} ${task.description || ''} ${timeProjects[task.project_id] || ''} ${task.tags || ''} ${task.list_name || ''}`.toLocaleLowerCase('ru');
            if (!haystack.includes(search)) return false;
        }
        if (!taskMatchesTagFilter(task.tags, tags)) return false;
        return true;
    });
    filtered.sort((a, b) => {
        const left = getTimeSortValue(a, timeSort.key);
        const right = getTimeSortValue(b, timeSort.key);
        const comparison = typeof left === 'number' && typeof right === 'number'
            ? left - right
            : String(left).localeCompare(String(right), 'ru');
        return timeSort.direction === 'asc' ? comparison : -comparison;
    });
    displayedTimeTasks = filtered;
    renderTaskTimeTable(filtered);
}

function resetTimeFilters() {
    [
        'time-filter-search',
        'time-filter-project',
        'time-filter-status',
        'time-filter-priority',
        'time-filter-assignee',
        'time-filter-list',
        'time-filter-tags',
        'time-filter-due-before',
        'time-filter-created-after',
        'time-filter-created-before',
    ].forEach(id => {
        const field = document.getElementById(id);
        if (field) field.value = '';
    });
    applyTimeFilters();
}

async function exportTaskTimeXlsx() {
    if (!displayedTimeTasks.length) return;
    try {
        const response = await fetch('/api/tasks/time/export/xlsx', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_ids: displayedTimeTasks.map(task => task.id),
                project_id: PROJECT_ID,
            }),
        });
        if (!response.ok) {
            let detail = `Ошибка ${response.status}`;
            try {
                const error = await response.json();
                if (error.detail) detail = error.detail;
            } catch (error) {}
            if (typeof showToast === 'function') showToast(detail, 'danger');
            return;
        }
        const blob = await response.blob();
        const disposition = response.headers.get('content-disposition');
        const filename = disposition?.match(/filename="?([^";]+)"?/i)?.[1] || 'task_time.xlsx';
        const downloadUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(downloadUrl);
    } catch (error) {
        console.error('Не удалось выгрузить таблицу учёта времени:', error);
        if (typeof showToast === 'function') showToast(`Ошибка выгрузки: ${error.message}`, 'danger');
    }
}

function hasTimeValues(task) {
    return task.estimated_minutes != null
        || (task.work_seconds || 0) > 0
        || (task.testing_seconds || 0) > 0
        || (task.actual_seconds || 0) > 0;
}

function getTimeSortValue(task, key) {
    if (key === 'created_at') {
        const createdAt = Date.parse(task.created_at || '');
        return Number.isNaN(createdAt) ? Number(task.id) || 0 : createdAt;
    }
    if (key === 'project') return timeProjects[task.project_id] || '';
    if (key === 'title') return task.title || task.description || '';
    if (key === 'status') return task.status?.name || '';
    return task[key] ?? -1;
}

function sortTaskTime(key) {
    if (timeSort.key === key) {
        timeSort.direction = timeSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        timeSort = { key, direction: 'asc' };
    }
    applyTimeFilters();
}

function renderTaskTimeTable(tasks) {
    hideTaskTimeContextMenu();
    const body = document.getElementById('task-time-table-body');
    const foot = document.getElementById('task-time-table-foot');
    document.getElementById('task-time-export-xlsx').disabled = !tasks.length;
    const projectColumnCount = IS_GLOBAL ? 1 : 0;
    const columnCount = 8 + projectColumnCount;
    if (!tasks.length) {
        body.innerHTML = `<tr><td colspan="${columnCount}" class="text-center text-muted py-4">Нет задач</td></tr>`;
        foot.innerHTML = '';
        return;
    }

    let plannedTotal = 0;
    let plannedCount = 0;
    let workTotal = 0;
    let testingTotal = 0;
    let actualTotal = 0;
    tasks.forEach(task => {
        if (task.estimated_minutes != null) {
            plannedTotal += task.estimated_minutes * 60;
            plannedCount += 1;
        }
        workTotal += task.work_seconds || 0;
        testingTotal += task.testing_seconds || 0;
        actualTotal += task.actual_seconds || 0;
    });

    body.innerHTML = tasks.map(task => {
        const estimate = task.estimated_minutes == null ? null : task.estimated_minutes * 60;
        const actual = task.actual_seconds || 0;
        const deviation = estimate == null ? null : actual - estimate;
        const deviationClass = deviation == null ? 'text-muted' : deviation > 0 ? 'text-danger' : deviation < 0 ? 'text-success' : 'text-muted';
        const projectCell = IS_GLOBAL ? `<td>${escapeTimeHtml(timeProjects[task.project_id] || `Проект #${task.project_id}`)}</td>` : '';
        return `<tr data-task-id="${task.id}">
            <td>${task.id}</td>
            ${projectCell}
            <td><div class="d-flex align-items-center gap-2">
                <button class="task-time-title flex-grow-1" type="button" data-task-id="${task.id}" onclick="openTaskTimeEditor(${task.id})">${escapeTimeHtml(task.title || task.description || '—')}</button>
                <button class="btn btn-sm btn-outline-primary flex-shrink-0" type="button" title="Редактировать задачу" aria-label="Редактировать задачу" onclick="openTaskViewModal(${task.id})"><i class="bi bi-pencil-square" aria-hidden="true"></i></button>
            </div></td>
            <td>${escapeTimeHtml(task.status?.name || '—')}</td>
            <td class="text-nowrap">${estimate == null ? '—' : formatEffortTime(estimate)}</td>
            <td class="text-nowrap">${formatEffortTime(task.work_seconds || 0)}</td>
            <td class="text-nowrap">${formatEffortTime(task.testing_seconds || 0)}</td>
            <td class="text-nowrap fw-semibold">${formatEffortTime(actual)}</td>
            <td class="text-nowrap ${deviationClass}">${deviation == null ? '—' : formatSignedEffortTime(deviation)}</td>
        </tr>`;
    }).join('');

    const totalDeviation = actualTotal - plannedTotal;
    const totalDeviationClass = totalDeviation > 0 ? 'text-danger' : totalDeviation < 0 ? 'text-success' : 'text-muted';
    foot.innerHTML = `<tr>
        <td colspan="${3 + projectColumnCount}" class="text-end">Итого</td>
        <td>${plannedCount ? formatEffortTime(plannedTotal) : '—'}</td>
        <td>${formatEffortTime(workTotal)}</td>
        <td>${formatEffortTime(testingTotal)}</td>
        <td>${formatEffortTime(actualTotal)}</td>
        <td class="${totalDeviationClass}">${plannedCount === tasks.length ? formatSignedEffortTime(totalDeviation) : '—'}</td>
    </tr>`;
}

function showTaskTimeContextMenu(event) {
    const row = event.target.closest('tr[data-task-id]');
    if (!row) return;
    event.preventDefault();
    event.stopPropagation();
    contextTimeTaskId = Number(row.dataset.taskId);
    const menu = document.getElementById('task-time-context-menu');
    menu.style.display = 'block';
    menu.style.left = `${Math.max(0, Math.min(event.clientX, window.innerWidth - menu.offsetWidth))}px`;
    menu.style.top = `${Math.max(0, Math.min(event.clientY, window.innerHeight - menu.offsetHeight))}px`;
}

function hideTaskTimeContextMenu() {
    const menu = document.getElementById('task-time-context-menu');
    if (menu) menu.style.display = 'none';
    contextTimeTaskId = null;
}

function handleTaskTimeContextAction(event) {
    const action = event.target.closest('[data-action]')?.dataset.action;
    const task = timeTasks.find(item => item.id === contextTimeTaskId);
    if (!action || !task) return;
    hideTaskTimeContextMenu();
    if (action === 'copy-link') copyTaskLink(task.project_id, task.id);
    if (action === 'edit-time') openTaskTimeEditor(task.id);
    if (action === 'edit-task') openTaskViewModal(task.id);
}

function openTaskTimeEditor(taskId) {
    const task = timeTasks.find(item => item.id === taskId);
    if (!task) return;
    editingTimeTaskId = taskId;
    document.getElementById('task-time-edit-title').textContent = task.title || task.description || '—';
    setTaskTimeInputs('plan', task.estimated_minutes == null ? null : task.estimated_minutes * 60);
    setTaskTimeInputs('work', task.work_seconds || 0);
    setTaskTimeInputs('testing', task.testing_seconds || 0);
    setTaskTimeInputs('actual', task.actual_seconds || 0);
    document.getElementById('task-time-edit-form').dataset.initial = JSON.stringify({
        plan: task.estimated_minutes,
        work: Math.floor((task.work_seconds || 0) / 60),
        testing: Math.floor((task.testing_seconds || 0) / 60),
        actual: Math.floor((task.actual_seconds || 0) / 60),
    });
    bootstrap.Modal.getOrCreateInstance(document.getElementById('task-time-edit-modal')).show();
}

function setTaskTimeInputs(field, seconds) {
    const totalMinutes = seconds == null ? null : Math.floor(seconds / 60);
    const values = totalMinutes == null
        ? ['', '', '']
        : [Math.floor(totalMinutes / 1440), Math.floor((totalMinutes % 1440) / 60), totalMinutes % 60];
    ['days', 'hours', 'minutes'].forEach((unit, index) => {
        document.getElementById(`task-time-edit-${field}-${unit}`).value = values[index];
    });
}

function getTaskTimeInputMinutes(field) {
    const days = Number(document.getElementById(`task-time-edit-${field}-days`).value || 0);
    const hours = Number(document.getElementById(`task-time-edit-${field}-hours`).value || 0);
    const minutes = Number(document.getElementById(`task-time-edit-${field}-minutes`).value || 0);
    const allEmpty = ['days', 'hours', 'minutes'].every(unit =>
        document.getElementById(`task-time-edit-${field}-${unit}`).value === ''
    );
    if (field === 'plan' && allEmpty) return null;
    return days * 1440 + hours * 60 + minutes;
}

async function saveTaskTimeValues(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity() || editingTimeTaskId == null) return;
    const task = timeTasks.find(item => item.id === editingTimeTaskId);
    if (!task) return;
    const initial = JSON.parse(form.dataset.initial || '{}');
    const plan = getTaskTimeInputMinutes('plan');
    const work = getTaskTimeInputMinutes('work');
    const testing = getTaskTimeInputMinutes('testing');
    const actual = getTaskTimeInputMinutes('actual');
    const payload = {};
    if ((plan ?? null) !== (initial.plan ?? null)) payload.estimated_minutes = plan;
    if (work !== initial.work) payload.work_seconds = work * 60;
    if (testing !== initial.testing) payload.testing_seconds = testing * 60;
    if (actual !== initial.actual) payload.actual_seconds = actual * 60;
    if (!Object.keys(payload).length) {
        bootstrap.Modal.getInstance(document.getElementById('task-time-edit-modal'))?.hide();
        return;
    }

    const submitButton = form.querySelector('[type="submit"]');
    submitButton.disabled = true;
    try {
        const response = await fetch(`/api/projects/${task.project_id}/tasks/${task.id}`, {
            method: 'PATCH',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error(await response.text());
        bootstrap.Modal.getInstance(document.getElementById('task-time-edit-modal'))?.hide();
        await loadTaskTimeData();
    } catch (error) {
        console.error('Не удалось сохранить время задачи:', error);
    } finally {
        submitButton.disabled = false;
    }
}

function formatEffortTime(seconds) {
    const totalMinutes = Math.floor(Math.max(0, Number(seconds) || 0) / 60);
    const days = Math.floor(totalMinutes / 1440);
    const hours = Math.floor((totalMinutes % 1440) / 60);
    const minutes = totalMinutes % 60;
    const parts = [];
    if (days) parts.push(`${days} д`);
    if (hours || days) parts.push(`${hours} ч`);
    if (minutes || (!days && !hours)) parts.push(`${minutes} мин`);
    return parts.join(' ');
}

function formatSignedEffortTime(seconds) {
    if (seconds === 0) return '0 мин';
    return `${seconds > 0 ? '+' : '−'}${formatEffortTime(Math.abs(seconds))}`;
}

function escapeTimeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }[character]));
}
