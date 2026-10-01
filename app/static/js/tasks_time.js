let timeTasks = [];
let timeProjects = {};
let timeSort = { key: 'created_at', direction: 'desc' };

document.addEventListener('DOMContentLoaded', async () => {
    await loadTaskTimeData();
    window.setInterval(loadTaskTimeData, 60000);
});

async function loadTaskTimeData() {
    const tableBody = document.getElementById('task-time-table-body');
    try {
        const taskUrl = IS_GLOBAL ? '/api/tasks' : `/api/projects/${PROJECT_ID}/tasks`;
        const [tasksResponse, projectsResponse] = await Promise.all([
            fetch(taskUrl, { credentials: 'same-origin' }),
            fetch('/api/projects', { credentials: 'same-origin' }),
        ]);
        if (!tasksResponse.ok) throw new Error(await tasksResponse.text());
        if (!projectsResponse.ok) throw new Error(await projectsResponse.text());
        timeTasks = await tasksResponse.json();
        const projects = await projectsResponse.json();
        timeProjects = Object.fromEntries(projects.map(project => [project.id, project.name]));
        populateTimeFilters();
        applyTimeFilters();
    } catch (error) {
        tableBody.innerHTML = `<tr><td colspan="${IS_GLOBAL ? 9 : 8}" class="text-center text-danger py-4">${escapeTimeHtml(error.message)}</td></tr>`;
    }
}

function populateTimeFilters() {
    const statusSelect = document.getElementById('time-filter-status');
    const previousStatus = statusSelect.value;
    const statuses = [...new Set(timeTasks.map(task => task.status?.name).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru'));
    statusSelect.innerHTML = '<option value="">Все статусы</option>' + statuses.map(status =>
        `<option value="${escapeTimeHtml(status)}">${escapeTimeHtml(status)}</option>`
    ).join('');
    statusSelect.value = previousStatus;

    const projectSelect = document.getElementById('time-filter-project');
    if (!projectSelect) return;
    const previousProject = projectSelect.value;
    const projects = [...new Set(timeTasks.map(task => task.project_id))]
        .map(id => ({ id, name: timeProjects[id] || `Проект #${id}` }))
        .sort((a, b) => a.name.localeCompare(b.name, 'ru'));
    projectSelect.innerHTML = '<option value="">Все проекты</option>' + projects.map(project =>
        `<option value="${project.id}">${escapeTimeHtml(project.name)}</option>`
    ).join('');
    projectSelect.value = previousProject;
}

function applyTimeFilters() {
    const search = document.getElementById('time-filter-search').value.trim().toLocaleLowerCase('ru');
    const status = document.getElementById('time-filter-status').value;
    const project = document.getElementById('time-filter-project')?.value || '';
    const filtered = timeTasks.filter(task => {
        if (!hasTimeValues(task)) return false;
        if (status && task.status?.name !== status) return false;
        if (project && String(task.project_id) !== project) return false;
        if (search) {
            const haystack = `${task.title || ''} ${task.description || ''} ${timeProjects[task.project_id] || ''}`.toLocaleLowerCase('ru');
            if (!haystack.includes(search)) return false;
        }
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
    renderTaskTimeTable(filtered);
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
    const body = document.getElementById('task-time-table-body');
    const foot = document.getElementById('task-time-table-foot');
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
        const taskLink = `/projects/${task.project_id}/kanban?task=${task.id}`;
        const projectCell = IS_GLOBAL ? `<td>${escapeTimeHtml(timeProjects[task.project_id] || `Проект #${task.project_id}`)}</td>` : '';
        return `<tr>
            <td>${task.id}</td>
            ${projectCell}
            <td><a class="task-time-title text-decoration-none" href="${taskLink}">${escapeTimeHtml(task.title || task.description || '—')}</a></td>
            <td>${escapeTimeHtml(task.status?.name || '—')}</td>
            <td class="text-nowrap">${estimate == null ? '—' : formatEffortTime(estimate)}</td>
            <td class="text-nowrap">${formatEffortTime(task.work_seconds || 0)}</td>
            <td class="text-nowrap">${formatEffortTime(task.testing_seconds || 0)}</td>
            <td class="text-nowrap fw-semibold">${formatEffortTime(actual)}</td>
            <td class="text-nowrap ${deviationClass}">${deviation == null ? '—' : formatSignedEffortTime(deviation)}</td>
        </tr>`;
    }).join('');

    foot.innerHTML = `<tr>
        <td colspan="${3 + projectColumnCount}" class="text-end">Итого</td>
        <td>${plannedCount ? formatEffortTime(plannedTotal) : '—'}</td>
        <td>${formatEffortTime(workTotal)}</td>
        <td>${formatEffortTime(testingTotal)}</td>
        <td>${formatEffortTime(actualTotal)}</td>
        <td>${plannedCount === tasks.length ? formatSignedEffortTime(actualTotal - plannedTotal) : '—'}</td>
    </tr>`;
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
