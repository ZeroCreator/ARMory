const API_BASE = '/api';

async function api(url, options = {}) {
    const res = await fetch(url, options);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    if (res.status === 204) return null;
    return res.json();
}

function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString('ru-RU') + ' ' + d.toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'});
}

function formatSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
    return (bytes/1024/1024).toFixed(1) + ' MB';
}

function showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
    }

    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-bg-${type} border-0`;
    toastEl.setAttribute('role', 'alert');
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${escapeHtml(message)}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    container.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

function isLocalhost() {
    const host = window.location.hostname;
    return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '0.0.0.0';
}


// ═══════════════════════════════════════════════════
// Категории
// ═══════════════════════════════════════════════════

const CATEGORY_ICONS = {
    image:        'bi-image',
    video:        'bi-camera-video',
    audio:        'bi-music-note-beamed',
    pdf:          'bi-file-earmark-pdf',
    word:         'bi-file-earmark-word',
    spreadsheet:  'bi-file-earmark-excel',
    presentation: 'bi-file-earmark-slides',
    archive:      'bi-file-zip',
    code:         'bi-file-code',
    text:         'bi-file-text',
    drive:        'bi-google',
    docs:         'bi-file-earmark-word',
    sheets:       'bi-file-earmark-spreadsheet',
    slides:       'bi-file-earmark-slides',
    youtube:      'bi-youtube',
    figma:        'bi-palette',
    notion:       'bi-journal-text',
    github:       'bi-github',
    gitlab:       'bi-git',
    link:         'bi-link-45deg',
    file:         'bi-file-earmark',
    note:         'bi-sticky',
};

const CATEGORY_LABELS = {
    image:        'Изображение',
    video:        'Видео',
    audio:        'Аудио',
    pdf:          'PDF',
    word:         'Word',
    spreadsheet:  'Excel',
    presentation: 'PowerPoint',
    archive:      'Архив',
    code:         'Код',
    text:         'Текст',
    drive:        'Google Drive',
    docs:         'Google Docs',
    sheets:       'Google Sheets',
    slides:       'Google Slides',
    youtube:      'YouTube',
    figma:        'Figma',
    notion:       'Notion',
    github:       'GitHub',
    gitlab:       'GitLab',
    link:         'Ссылка',
    file:         'Файл',
    note:         'Заметка',
};

function getCategoryIcon(cat) {
    return CATEGORY_ICONS[cat] || CATEGORY_ICONS.file;
}

function getCategoryLabel(cat) {
    return CATEGORY_LABELS[cat] || null;
}

function getItemLabel(item) {
    const known = getCategoryLabel(item.category || detectCategoryFromItem(item));
    if (known) return known;
    if (item.file_name) {
        const parts = item.file_name.split('.');
        if (parts.length > 1) return parts.pop().toUpperCase();
    }
    return item.item_type === 'link' ? 'Ссылка' : 'Файл';
}

function detectCategoryFromItem(item) {
    if (item.item_type === 'link') {
        const u = (item.url || '').toLowerCase();
        if (u.includes('youtube.com') || u.includes('youtu.be')) return 'youtube';
        if (u.includes('drive.google.com')) return 'drive';
        if (u.includes('docs.google.com/document')) return 'docs';
        if (u.includes('docs.google.com/spreadsheets')) return 'sheets';
        if (u.includes('docs.google.com/presentation')) return 'slides';
        if (u.includes('figma.com')) return 'figma';
        if (u.includes('notion.so')) return 'notion';
        if (u.includes('github.com')) return 'github';
        if (u.includes('gitlab.com')) return 'gitlab';
        return 'link';
    }
    const fn = (item.file_name || '').toLowerCase();
    const ext = fn.split('.').pop();
    const map = {
        jpg:'image', jpeg:'image', png:'image', gif:'image', svg:'image', webp:'image',
        mp4:'video', avi:'video', mov:'video', mkv:'video', webm:'video',
        mp3:'audio', wav:'audio', ogg:'audio', flac:'audio',
        pdf:'pdf',
        doc:'word', docx:'word', rtf:'word',
        xls:'spreadsheet', xlsx:'spreadsheet', ods:'spreadsheet', csv:'spreadsheet',
        ppt:'presentation', pptx:'presentation', odp:'presentation',
        zip:'archive', rar:'archive', '7z':'archive', tar:'archive', gz:'archive',
        py:'code', js:'code', ts:'code', html:'code', css:'code', json:'code', yaml:'code', yml:'code', sql:'code',
        txt:'text', md:'text', log:'text',
    };
    return map[ext] || 'file';
}

// ═══════════════════════════════════════════════════
// ПРОЕКТЫ
// ═══════════════════════════════════════════════════

let allProjects = [];
let currentProjectsPage = 1;
const PROJECTS_PER_PAGE = 6;

async function loadProjects() {
    const container = document.getElementById('projects-list');
    try {
        const projects = await api(`${API_BASE}/projects`);
        allProjects = projects;
        currentProjectsPage = 1;
        renderProjectsPage();
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Ошибка загрузки: ${e.message}</div>`;
        document.getElementById('projects-pagination').innerHTML = '';
    }
}

function renderProjectsPage() {
    const container = document.getElementById('projects-list');
    const paginationContainer = document.getElementById('projects-pagination');
    const projects = allProjects;

    if (!projects.length) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="bi bi-folder"></i>
                <p>Проектов пока нет. Создайте первый проект!</p>
            </div>`;
        paginationContainer.innerHTML = '';
        return;
    }

    const totalPages = Math.ceil(projects.length / PROJECTS_PER_PAGE);
    const start = (currentProjectsPage - 1) * PROJECTS_PER_PAGE;
    const end = start + PROJECTS_PER_PAGE;
    const pageProjects = projects.slice(start, end);

    container.innerHTML = pageProjects.map((p, idx) => `
        <div class="col-lg-6 col-xl-6 col-xxl-4 project-col fade-in" data-id="${p.id}">
            <div class="project-card" data-href="/projects/${p.id}">
                <div class="project-drag-handle"><i class="bi bi-grip-vertical"></i></div>
                <div>
                    <div class="project-title">${escapeHtml(p.name)}</div>
                    <div class="project-desc">${escapeHtml(p.description || 'Без описания')}</div>
                </div>
                <div class="project-meta d-flex justify-content-between">
                    <span><i class="bi bi-folder me-1"></i>${p.sections?.length ?? 0} разделов, <i class="bi bi-files me-1"></i>${p.documents?.length ?? 0} групп</span>
                    <span>${formatDate(p.updated_at)}</span>
                </div>
            </div>
        </div>
    `).join('');

    container.querySelectorAll('.project-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.closest('.project-drag-handle')) return;
            location.href = card.dataset.href;
        });
    });

    renderPagination('projects-pagination', currentProjectsPage, totalPages, (page) => {
        currentProjectsPage = page;
        renderProjectsPage();
    }, container);

    initProjectSortable();
}

function renderProjectsPagination(totalPages) {
    let html = '';
    for (let i = 1; i <= totalPages; i++) {
        const activeClass = i === currentProjectsPage ? 'active' : '';
        html += `<button class="pagination-btn ${activeClass}" data-page="${i}">${i}</button>`;
    }
    return html;
}

/**
 * Рендерит числовую пагинацию в указанный контейнер.
 * @param {string} containerId - id DOM-элемента для пагинации
 * @param {number} currentPage - текущая страница (1-based)
 * @param {number} totalPages - общее число страниц
 * @param {function(number):void} onPageChange - колбэк, вызываемый с новой страницей (1-based)
 * @param {HTMLElement|null} scrollTarget - элемент, к которому прокрутить после смены страницы
 */
function renderPagination(containerId, currentPage, totalPages, onPageChange, scrollTarget) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    // Строгое представление: 3 цифры + многоточие + последняя страница
    const windowSize = 3;
    const half = Math.floor(windowSize / 2);
    let start = Math.max(1, currentPage - half);
    let end = Math.min(totalPages, currentPage + half);

    if (end - start + 1 < windowSize) {
        if (start === 1) {
            end = Math.min(totalPages, start + windowSize - 1);
        } else if (end === totalPages) {
            start = Math.max(1, end - windowSize + 1);
        }
    }

    const pages = [];
    for (let i = start; i <= end; i++) pages.push(i);
    if (end < totalPages) {
        pages.push('ellipsis');
        pages.push(totalPages);
    }

    let html = '';
    html += `<button class="pagination-btn pagination-btn-nav" data-page="${currentPage - 1}" aria-label="Назад" ${currentPage === 1 ? 'disabled' : ''}>` +
            `<i class="bi bi-chevron-left"></i></button>`;

    pages.forEach(p => {
        if (p === 'ellipsis') {
            html += `<span class="pagination-btn pagination-btn-ellipsis" aria-hidden="true">...</span>`;
        } else {
            const activeClass = p === currentPage ? 'active' : '';
            html += `<button class="pagination-btn ${activeClass}" data-page="${p}" aria-label="Страница ${p}">${p}</button>`;
        }
    });

    html += `<button class="pagination-btn pagination-btn-nav" data-page="${currentPage + 1}" aria-label="Вперёд" ${currentPage === totalPages ? 'disabled' : ''}>` +
            `<i class="bi bi-chevron-right"></i></button>`;

    container.innerHTML = html;

    container.querySelectorAll('.pagination-btn[data-page]').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.disabled) return;
            const page = parseInt(btn.dataset.page, 10);
            onPageChange(page);
            if (scrollTarget) scrollTarget.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    });
}

let projectSortable = null;

function initProjectSortable() {
    const el = document.getElementById('projects-list');
    if (!el) return;
    if (projectSortable) projectSortable.destroy();

    projectSortable = Sortable.create(el, {
        animation: 150,
        handle: '.project-drag-handle',
        draggable: '.project-col',
        forceFallback: true,
        fallbackClass: 'sortable-drag',
        ghostClass: 'sortable-ghost',
        dragClass: 'sortable-drag',
        onEnd: function () {
            const ids = Array.from(el.children)
                .filter(child => child.classList.contains('project-col'))
                .map(child => parseInt(child.dataset.id));
            if (ids.length > 1) {
                reorderProjects(ids);
            }
        }
    });
}

async function reorderProjects(projectIds) {
    try {
        await api(`${API_BASE}/projects/reorder`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({project_ids: projectIds})
        });
        // Обновить локальный порядок для текущей страницы
        const start = (currentProjectsPage - 1) * PROJECTS_PER_PAGE;
        const end = Math.min(start + PROJECTS_PER_PAGE, allProjects.length);
        const projectMap = new Map(allProjects.map(p => [p.id, p]));
        const reordered = projectIds.map(id => projectMap.get(id)).filter(Boolean);
        allProjects = allProjects.slice(0, start).concat(reordered).concat(allProjects.slice(end));
    } catch (e) {
        console.error('Reorder projects failed:', e);
        loadProjects();
    }
}

async function createProject() {
    const form = document.getElementById('project-form');
    const data = Object.fromEntries(new FormData(form));
    if (!data.name.trim()) return alert('Введите название проекта');
    try {
        await api(`${API_BASE}/projects`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        form.reset();
        bootstrap.Modal.getInstance(document.getElementById('projectModal')).hide();
        loadProjects();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

// ═══════════════════════════════════════════════════
// ДЕТАЛИ ПРОЕКТА
// ═══════════════════════════════════════════════════

async function loadProject(id) {
    const header = document.getElementById('project-header');
    try {
        const p = await api(`${API_BASE}/projects/${id}`);
        header.innerHTML = `
            <div class="d-flex justify-content-between align-items-start fade-in">
                <div>
                    <h2>${escapeHtml(p.name)}</h2>
                    <p class="text-muted mb-0">${escapeHtml(p.description || 'Без описания')}</p>
                </div>
                <button class="btn btn-outline-primary" data-bs-toggle="modal" data-bs-target="#editProjectModal" onclick="fillEditForm(${JSON.stringify(p).replace(/"/g,'&quot;')})">
                    <i class="bi bi-pencil"></i> Редактировать
                </button>
            </div>
            <hr>`;
    } catch (e) {
        header.innerHTML = `<div class="alert alert-danger">Ошибка загрузки проекта: ${e.message}</div>`;
    }
}

function fillEditForm(p) {
    const f = document.getElementById('edit-project-form');
    f.name.value = p.name;
    f.description.value = p.description || '';
    f.dataset.id = p.id;
}

async function updateProject() {
    const f = document.getElementById('edit-project-form');
    const id = f.dataset.id;
    const data = { name: f.name.value, description: f.description.value };
    try {
        await api(`${API_BASE}/projects/${id}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        bootstrap.Modal.getInstance(document.getElementById('editProjectModal')).hide();
        loadProject(id);
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function deleteProject() {
    if (!confirm('Удалить проект и все документы?')) return;
    const f = document.getElementById('edit-project-form');
    const id = f.dataset.id;
    try {
        await api(`${API_BASE}/projects/${id}`, { method: 'DELETE' });
        location.href = '/';
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

// ═══════════════════════════════════════════════════
// РАЗДЕЛЫ
// ═══════════════════════════════════════════════════

let sectionsCache = [];
let sectionSortable = null;

function getCollapsedState(projectId) {
    const key = `sections_collapsed_${projectId}`;
    return JSON.parse(localStorage.getItem(key) || '{}');
}

function isSectionCollapsed(projectId, sectionId) {
    return getCollapsedState(projectId)[sectionId] !== false;
}

function toggleSection(sectionId) {
    const state = getCollapsedState(PROJECT_ID);
    state[sectionId] = !state[sectionId];
    localStorage.setItem(`sections_collapsed_${PROJECT_ID}`, JSON.stringify(state));
    const card = document.querySelector(`.section-card[data-id="${sectionId}"]`);
    if (!card) return;
    const body = card.querySelector('.section-body');
    const icon = card.querySelector('.section-toggle-icon');
    if (body) body.classList.toggle('d-none');
    if (icon) {
        icon.classList.toggle('bi-chevron-down');
        icon.classList.toggle('bi-chevron-right');
    }
}

function getGroupCollapsedState(projectId) {
    const key = `groups_collapsed_${projectId}`;
    return JSON.parse(localStorage.getItem(key) || '{}');
}

function isGroupCollapsed(projectId, groupId) {
    return getGroupCollapsedState(projectId)[groupId] !== false;
}

function toggleGroup(groupId) {
    const state = getGroupCollapsedState(PROJECT_ID);
    state[groupId] = !state[groupId];
    localStorage.setItem(`groups_collapsed_${PROJECT_ID}`, JSON.stringify(state));
    const card = document.querySelector(`.doc-group[data-id="${groupId}"]`);
    if (!card) return;
    const body = card.querySelector('.doc-group-body');
    const icon = card.querySelector('.group-toggle-icon');
    if (body) body.classList.toggle('d-none');
    if (icon) {
        icon.classList.toggle('bi-chevron-down');
        icon.classList.toggle('bi-chevron-right');
    }
}

async function loadSections(projectId) {
    const container = document.getElementById('documents-list');
    const header = document.getElementById('content-header');
    try {
        const [sections, ungrouped] = await Promise.all([
            api(`${API_BASE}/projects/${projectId}/sections`),
            api(`${API_BASE}/projects/${projectId}/documents`)
        ]);
        sectionsCache = sections || [];
        const hasContent = (sections && sections.length) || (ungrouped && ungrouped.length);
        if (!hasContent) {
            if (header) header.textContent = 'Разделы и группы';
            container.innerHTML = `
                <div class="empty-state">
                    <i class="bi bi-file-earmark-text"></i>
                    <p>Разделов и групп пока нет. Создайте первый раздел или группу!</p>
                </div>`;
            return;
        }
        if (header) {
            if (sections && sections.length) {
                header.textContent = 'Разделы';
            } else {
                header.textContent = 'Группы';
            }
        }
        let html = '';
        if (sections && sections.length) {
            html += sections.map((s, idx) => renderSection(s, idx)).join('');
        }
        if (ungrouped && ungrouped.length) {
            html += renderUngrouped(ungrouped);
        }
        container.innerHTML = html;
        initSectionSortable(projectId);
        document.querySelectorAll('.section-body, .ungrouped-block').forEach(el => {
            initGroupSortable(projectId, el);
        });
        document.querySelectorAll('.doc-group-body').forEach(el => {
            initItemSortable(projectId, el);
        });
        handleOpenItemFromUrl();
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Ошибка загрузки: ${e.message}</div>`;
    }
}

function toggleItemHighlight(itemEl) {
    if (!itemEl) return;
    const isHighlighted = itemEl.classList.contains('doc-item-highlighted');
    document.querySelectorAll('.doc-item-highlighted').forEach(el => el.classList.remove('doc-item-highlighted'));
    if (!isHighlighted) {
        itemEl.classList.add('doc-item-highlighted');
    }
}

function handleOpenItemFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const openItemId = params.get('open_item');
    if (!openItemId) return;

    const itemId = parseInt(openItemId, 10);
    if (!itemId) return;

    const itemEl = document.querySelector(`.doc-item[data-id="${itemId}"]`);
    if (!itemEl) return;

    // Развернуть раздел, если элемент внутри раздела
    const sectionCard = itemEl.closest('.section-card');
    if (sectionCard) {
        const sectionId = parseInt(sectionCard.dataset.id, 10);
        const state = getCollapsedState(PROJECT_ID);
        if (state[sectionId] !== false) {
            state[sectionId] = false;
            localStorage.setItem(`sections_collapsed_${PROJECT_ID}`, JSON.stringify(state));
            const body = sectionCard.querySelector('.section-body');
            const icon = sectionCard.querySelector('.section-toggle-icon');
            if (body) body.classList.remove('d-none');
            if (icon) {
                icon.classList.remove('bi-chevron-right');
                icon.classList.add('bi-chevron-down');
            }
        }
    }

    // Развернуть группу
    const groupEl = itemEl.closest('.doc-group');
    if (groupEl) {
        const groupId = parseInt(groupEl.dataset.id, 10);
        const state = getGroupCollapsedState(PROJECT_ID);
        if (state[groupId] !== false) {
            state[groupId] = false;
            localStorage.setItem(`groups_collapsed_${PROJECT_ID}`, JSON.stringify(state));
            const body = groupEl.querySelector('.doc-group-body');
            const icon = groupEl.querySelector('.group-toggle-icon');
            if (body) body.classList.remove('d-none');
            if (icon) {
                icon.classList.remove('bi-chevron-right');
                icon.classList.add('bi-chevron-down');
            }
        }
    }

    // Подсветить элемент
    toggleItemHighlight(itemEl);

    // Прокрутить к элементу
    setTimeout(() => {
        itemEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);

    // Открыть предпросмотр файла
    let itemData = null;
    try {
        itemData = JSON.parse(itemEl.dataset.item.replace(/&quot;/g, '"').replace(/&#39;/g, "'"));
    } catch (e) {
        console.warn('Failed to parse item data for preview', e);
    }
    if (itemData && itemData.item_type !== 'link') {
        setTimeout(() => {
            openItemPreview(itemData);
        }, 400);
    }

    // Очистить параметр URL, чтобы при обновлении страницы не открывалось повторно
    if (window.history.replaceState) {
        const url = new URL(window.location.href);
        url.searchParams.delete('open_item');
        window.history.replaceState({}, '', url.toString());
    }
}

function renderSection(section, idx) {
    const collapsed = isSectionCollapsed(PROJECT_ID, section.id);
    const docsHtml = (section.documents || []).map((d, iidx) => renderGroup(d, iidx)).join('');
    const descHtml = section.description ? `<div class="section-desc small">${escapeHtml(section.description)}</div>` : '';
    return `
        <div class="section-card mb-3 fade-in" data-id="${section.id}">
            <div class="section-header" onclick="toggleSection(${section.id})">
                <div class="d-flex align-items-center gap-2 flex-fill">
                    <div class="doc-drag-handle" onclick="event.stopPropagation()"><i class="bi bi-grip-vertical"></i></div>
                    <i class="bi ${collapsed ? 'bi-chevron-right' : 'bi-chevron-down'} section-toggle-icon"></i>
                    <div>
                        <div class="d-flex align-items-center gap-2">
                            <h5 class="mb-0 section-title">${escapeHtml(section.name)}</h5>
                            <span class="text-muted small">${section.documents?.length || 0} групп</span>
                        </div>
                        ${descHtml}
                    </div>
                </div>
                <div class="section-actions" onclick="event.stopPropagation()">
                    <button class="btn btn-sm btn-outline-primary" onclick="showAddGroupModal(${section.id})"><i class="bi bi-plus-lg"></i></button>
                    <button class="btn btn-sm btn-outline-secondary" onclick="showEditSectionModal(${section.id}, '${escapeHtml(section.name).replace(/'/g, "\\'")}', '${escapeHtml(section.description || '').replace(/'/g, "\\'")}')"><i class="bi bi-pencil"></i></button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteSection(${section.id})"><i class="bi bi-trash"></i></button>
                </div>
            </div>
            <div class="section-body ${collapsed ? 'd-none' : ''}">
                ${docsHtml || '<div class="text-muted small py-2">Нет групп — добавьте группу в этот раздел</div>'}
            </div>
        </div>`;
}

function renderUngrouped(docs) {
    const docsHtml = docs.map((d, idx) => renderGroup(d, idx)).join('');
    return `
        <div class="ungrouped-block mb-4">
            ${docsHtml}
        </div>`;
}

function renderGroup(doc, idx) {
    const itemsHtml = (doc.items || []).map((item, iidx) => renderItem(doc, item, iidx)).join('');
    const emptyItems = !doc.items || !doc.items.length
        ? '<div class="text-muted small ps-2">Нет материалов — добавьте ссылку или файл</div>'
        : '';
    const descHtml = doc.description ? `<div class="group-desc small">${escapeHtml(doc.description)}</div>` : '';

    const groupCollapsed = isGroupCollapsed(PROJECT_ID, doc.id);
    return `
        <div class="doc-group fade-in" data-id="${doc.id}">
            <div class="doc-group-header" onclick="toggleGroup(${doc.id})">
                <div class="d-flex justify-content-between align-items-center">
                    <div class="d-flex align-items-center gap-2">
                        <div class="doc-drag-handle" onclick="event.stopPropagation()"><i class="bi bi-grip-vertical"></i></div>
                        <i class="bi ${groupCollapsed ? 'bi-chevron-right' : 'bi-chevron-down'} group-toggle-icon"></i>
                        <div>
                            <h5 class="mb-0 doc-group-title">${escapeHtml(doc.title)}</h5>
                            ${descHtml}
                        </div>
                    </div>
                    <div class="doc-group-actions" onclick="event.stopPropagation()">
                        <button class="btn btn-sm btn-outline-primary" onclick="event.stopPropagation(); showAddItemModal(${doc.id})">
                            <i class="bi bi-plus-lg"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-secondary" onclick="event.stopPropagation(); showEditGroupModal(${doc.id}, '${escapeHtml(doc.title).replace(/'/g, "\\'")}', ${doc.section_id === null ? 'null' : doc.section_id}, '${escapeHtml(doc.description || '').replace(/'/g, "\\'")}')">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="event.stopPropagation(); deleteGroup(${doc.id})">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
            <div class="doc-group-body ${groupCollapsed ? 'd-none' : ''}">
                ${itemsHtml}
                ${emptyItems}
            </div>
        </div>`;
}

function renderItem(doc, item, idx) {
    const cat = item.category || detectCategoryFromItem(item);
    const iconClass = getCategoryIcon(cat);
    const label = getItemLabel(item);
    const isLink = item.item_type === 'link';
    const isNote = item.item_type === 'note';
    const displayTitle = item.title || (isLink ? truncate(item.url, 45) : (item.file_name || 'Заметка'));
    let subtitle = '';
    if (isLink) {
        try {
            subtitle = escapeHtml(new URL(item.url).hostname);
        } catch (e) {
            subtitle = escapeHtml(truncate(item.url, 40));
        }
    } else if (isNote) {
        subtitle = escapeHtml(truncate(item.content, 60));
    } else {
        subtitle = escapeHtml(item.file_name || '') + (item.file_size ? ' · ' + formatSize(item.file_size) : '');
    }
    let titleHtml;
    if (isLink) {
        titleHtml = `<a href="${escapeHtml(item.url)}" target="_blank" class="link-title">${escapeHtml(displayTitle)}</a>`;
    } else {
        titleHtml = escapeHtml(displayTitle);
    }
    const previewBtn = (isLink)
        ? ''
        : `<button class="btn btn-sm btn-outline-brown" onclick='event.stopPropagation(); openItemPreview(${JSON.stringify({...item, category: cat, document_id: doc.id}).replace(/'/g, "&#39;")})'><i class="bi bi-eye"></i></button>`;
    const downloadBtn = (isLink || isNote)
        ? ''
        : `<a href="${API_BASE}/projects/${PROJECT_ID}/documents/${doc.id}/items/${item.id}/download" class="btn btn-sm btn-outline-success"><i class="bi bi-download"></i></a>`;
    const alexandriteBtn = (isLink || isNote)
        ? ''
        : `<button class="btn btn-sm btn-outline-primary" onclick='event.stopPropagation(); openItemInAlexandrite(${JSON.stringify(item).replace(/'/g, "&#39;")})' title="Открыть в Alexandrite"><i class="bi bi-gem"></i></button>`;

    const itemData = JSON.stringify({...item, category: cat, document_id: doc.id}).replace(/"/g, '&quot;').replace(/'/g, "&#39;");
    return `
        <div class="doc-item d-flex align-items-center gap-2 py-2 ${idx > 0 ? 'border-top' : ''}" data-id="${item.id}" data-document-id="${doc.id}" data-item="${itemData}" oncontextmenu="handleProjectItemContextMenu(event, ${doc.id}, ${item.id})">
            <div class="doc-item-drag-handle" onclick="event.stopPropagation()" title="Переместить"><i class="bi bi-grip-vertical"></i></div>
            <div class="doc-item-icon ${cat}"><i class="bi ${iconClass}"></i></div>
            <div class="doc-item-info flex-fill" onclick='${isLink ? `event.stopPropagation(); toggleItemHighlight(this.closest(".doc-item"))` : `event.stopPropagation(); toggleItemHighlight(this.closest(".doc-item")); openItemPreview(${JSON.stringify({...item, category: cat, document_id: doc.id}).replace(/'/g, "&#39;")})`}'>
                <div class="doc-item-title d-flex align-items-center gap-2">
                    ${titleHtml}
                    <span class="doc-category ${cat}">${escapeHtml(label)}</span>
                </div>
                <div class="doc-item-meta">${subtitle}</div>
            </div>
            <div class="doc-item-actions d-flex gap-1">
                ${alexandriteBtn}
                <button class="btn btn-sm btn-outline-secondary" onclick='event.stopPropagation(); showEditItemModal(${doc.id}, ${JSON.stringify(item).replace(/'/g, "&#39;")})'><i class="bi bi-pencil"></i></button>
                ${previewBtn}
                ${downloadBtn}
                <button class="btn btn-sm btn-outline-danger" onclick="event.stopPropagation(); deleteItem(${doc.id}, ${item.id})"><i class="bi bi-trash"></i></button>
            </div>
        </div>`;
}

// ═══════════════════════════════════════════════════
// КОНТЕКСТНОЕ МЕНЮ ФАЙЛОВ ПРОЕКТА
// ═══════════════════════════════════════════════════

let projectItemContextTarget = null;

function handleProjectItemContextMenu(event, docId, itemId) {
    event.preventDefault();
    event.stopPropagation();
    const itemEl = event.currentTarget;
    let item = null;
    try {
        item = JSON.parse(itemEl.dataset.item.replace(/&quot;/g, '"').replace(/&#39;/g, "'"));
    } catch (e) {
        console.warn('Failed to parse item data', e);
    }
    projectItemContextTarget = { docId, itemId, item, element: itemEl };
    const menu = document.getElementById('project-item-context-menu');
    // Скрыть/показать пункты, недоступные для ссылок или заметок
    const isFile = item && item.item_type === 'file';
    menu.querySelectorAll('.project-item-context-item').forEach(el => {
        const action = el.dataset.action;
        if (['preview', 'alexandrite', 'download'].includes(action)) {
            el.style.display = isFile ? 'flex' : 'none';
        } else {
            el.style.display = 'flex';
        }
    });
    menu.style.display = 'block';
    const x = Math.min(event.clientX, window.innerWidth - 220);
    const y = Math.min(event.clientY, window.innerHeight - 80);
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
}

function hideProjectItemContextMenu() {
    const menu = document.getElementById('project-item-context-menu');
    if (menu) menu.style.display = 'none';
    projectItemContextTarget = null;
}

function copyProjectItemShareLink(docId, itemId) {
    const url = `${window.location.origin}/projects/${PROJECT_ID}?open_item=${itemId}`;
    copyTextToClipboard(url);
    showToast('Ссылка скопирована в буфер обмена');
}

function copyTextToClipboard(text) {
    const fallbackCopy = (txt) => {
        const ta = document.createElement('textarea');
        ta.value = txt;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.top = '-9999px';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.focus();
        ta.setSelectionRange(0, txt.length);
        try {
            document.execCommand('copy');
        } catch (e) {
            console.error('Fallback copy error:', e);
        }
        document.body.removeChild(ta);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).catch((err) => {
            console.warn('Clipboard API failed, using fallback:', err);
            fallbackCopy(text);
        });
    } else {
        fallbackCopy(text);
    }
}

// ═══════════════════════════════════════════════════
// CRUD РАЗДЕЛОВ
// ═══════════════════════════════════════════════════

async function createSection() {
    const form = document.getElementById('section-form');
    const data = new FormData(form);
    if (!data.get('name').trim()) return alert('Введите название раздела');
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/sections`, {
            method: 'POST',
            body: data
        });
        form.reset();
        bootstrap.Modal.getInstance(document.getElementById('sectionModal')).hide();
        loadSections(PROJECT_ID);
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

function showEditSectionModal(sectionId, name, description) {
    const f = document.getElementById('edit-section-form');
    f.section_id.value = sectionId;
    f.name.value = name;
    f.description.value = description || '';
    new bootstrap.Modal(document.getElementById('editSectionModal')).show();
}

async function updateSection() {
    const f = document.getElementById('edit-section-form');
    const sectionId = f.section_id.value;
    const name = f.name.value;
    const description = f.description.value;
    if (!name.trim()) return alert('Введите название');
    const fd = new FormData();
    fd.append('name', name);
    if (description) fd.append('description', description);
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/sections/${sectionId}`, {
            method: 'PATCH',
            body: fd
        });
        bootstrap.Modal.getInstance(document.getElementById('editSectionModal')).hide();
        loadSections(PROJECT_ID);
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function deleteSection(sectionId) {
    if (!confirm('Удалить раздел и всё его содержимое? Это действие нельзя отменить.')) return;
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/sections/${sectionId}`, { method: 'DELETE' });
        loadSections(PROJECT_ID);
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

function deleteSectionFromModal() {
    const f = document.getElementById('edit-section-form');
    const sectionId = f.section_id.value;
    bootstrap.Modal.getInstance(document.getElementById('editSectionModal')).hide();
    deleteSection(sectionId);
}

function initSectionSortable(projectId) {
    const el = document.getElementById('documents-list');
    if (!el) return;
    if (sectionSortable) sectionSortable.destroy();

    sectionSortable = Sortable.create(el, {
        animation: 150,
        handle: '.doc-drag-handle',
        draggable: '.section-card',
        forceFallback: true,
        fallbackClass: 'sortable-drag',
        ghostClass: 'sortable-ghost',
        dragClass: 'sortable-drag',
        onEnd: function (evt) {
            const ids = Array.from(el.children)
                .filter(child => child.classList.contains('section-card'))
                .map(child => parseInt(child.dataset.id));
            if (ids.length > 1) {
                reorderSections(projectId, ids);
            }
        }
    });
}

function initGroupSortable(projectId, el) {
    if (!el) return;
    const existing = el._sortable;
    if (existing) existing.destroy();

    el._sortable = Sortable.create(el, {
        animation: 150,
        handle: '.doc-drag-handle',
        draggable: '.doc-group',
        forceFallback: true,
        fallbackClass: 'sortable-drag',
        ghostClass: 'sortable-ghost',
        dragClass: 'sortable-drag',
        onEnd: function () {
            const ids = Array.from(el.children)
                .filter(child => child.classList.contains('doc-group'))
                .map(child => parseInt(child.dataset.id));
            if (ids.length > 1) {
                reorderDocuments(projectId, ids);
            }
        }
    });
}

function initItemSortable(projectId, el) {
    if (!el) return;
    const groupEl = el.closest('.doc-group');
    const docId = groupEl ? parseInt(groupEl.dataset.id) : null;
    if (!docId) return;
    const existing = el._itemSortable;
    if (existing) existing.destroy();

    el._itemSortable = Sortable.create(el, {
        animation: 150,
        handle: '.doc-item-drag-handle',
        draggable: '.doc-item',
        forceFallback: true,
        fallbackClass: 'sortable-drag',
        ghostClass: 'sortable-ghost',
        dragClass: 'sortable-drag',
        onEnd: function () {
            const ids = Array.from(el.children)
                .filter(child => child.classList.contains('doc-item'))
                .map(child => parseInt(child.dataset.id));
            if (ids.length > 1) {
                reorderItems(projectId, docId, ids);
            }
        }
    });
}

async function reorderDocuments(projectId, documentIds) {
    try {
        await api(`${API_BASE}/projects/${projectId}/documents/reorder`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({document_ids: documentIds})
        });
    } catch (e) {
        console.error('Reorder documents failed:', e);
        loadSections(projectId);
    }
}

async function reorderItems(projectId, docId, itemIds) {
    try {
        await api(`${API_BASE}/projects/${projectId}/documents/${docId}/items/reorder`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({item_ids: itemIds})
        });
    } catch (e) {
        console.error('Reorder items failed:', e);
        loadSections(projectId);
    }
}

async function reorderSections(projectId, sectionIds) {
    try {
        await api(`${API_BASE}/projects/${projectId}/sections/reorder`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({section_ids: sectionIds})
        });
    } catch (e) {
        console.error('Reorder sections failed:', e);
        loadSections(projectId);
    }
}

// ═══════════════════════════════════════════════════
// CRUD ГРУПП
// ═══════════════════════════════════════════════════

function fillSectionSelects() {
    const options = sectionsCache.map(s => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join('');
    const base = '<option value="">Без раздела</option><option value="-1">Без раздела</option>';
    const sel1 = document.getElementById('group-section-select');
    const sel2 = document.getElementById('edit-group-section-select');
    if (sel1) sel1.innerHTML = '<option value="">Без раздела</option>' + options;
    if (sel2) sel2.innerHTML = '<option value="-1">Без раздела</option>' + options;
}

function showAddGroupModal(sectionId) {
    fillSectionSelects();
    document.getElementById('group-form').reset();
    const sel = document.getElementById('group-section-select');
    if (sel && sectionId) sel.value = sectionId;
    new bootstrap.Modal(document.getElementById('groupModal')).show();
}

async function createGroup() {
    const form = document.getElementById('group-form');
    const data = new FormData(form);
    if (!data.get('title').trim()) return alert('Введите название группы');
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/documents`, {
            method: 'POST',
            body: data
        });
        form.reset();
        bootstrap.Modal.getInstance(document.getElementById('groupModal')).hide();
        loadSections(PROJECT_ID);
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

function showEditGroupModal(docId, title, sectionId, description) {
    fillSectionSelects();
    const f = document.getElementById('edit-group-form');
    f.doc_id.value = docId;
    f.title.value = title;
    f.querySelector('[name="description"]').value = description || '';
    f.querySelector('[name="section_id"]').value = sectionId === null ? '-1' : sectionId;
    new bootstrap.Modal(document.getElementById('editGroupModal')).show();
}

async function updateGroup() {
    const f = document.getElementById('edit-group-form');
    const docId = f.doc_id.value;
    const title = f.title.value;
    const description = f.querySelector('[name="description"]').value;
    const sectionId = f.querySelector('[name="section_id"]').value;
    if (!title.trim()) return alert('Введите название');
    const fd = new FormData();
    fd.append('title', title);
    if (description) fd.append('description', description);
    fd.append('section_id', sectionId);
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/documents/${docId}`, {
            method: 'PATCH',
            body: fd
        });
        bootstrap.Modal.getInstance(document.getElementById('editGroupModal')).hide();
        loadSections(PROJECT_ID);
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function deleteGroup(docId) {
    if (!confirm('Удалить группу и все материалы в ней?')) return;
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/documents/${docId}`, { method: 'DELETE' });
        loadSections(PROJECT_ID);
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

function deleteGroupFromModal() {
    const f = document.getElementById('edit-group-form');
    const docId = f.doc_id.value;
    bootstrap.Modal.getInstance(document.getElementById('editGroupModal')).hide();
    deleteGroup(docId);
}

// ═══════════════════════════════════════════════════
// CRUD ЭЛЕМЕНТОВ
// ═══════════════════════════════════════════════════

function showAddItemModal(docId) {
    document.getElementById('item-document-id').value = docId;
    document.getElementById('item-form').reset();
    toggleItemType();
    new bootstrap.Modal(document.getElementById('itemModal')).show();
}

function toggleItemType() {
    const type = document.getElementById('item-type-select').value;
    document.getElementById('item-url-field').classList.toggle('d-none', type !== 'link');
    document.getElementById('item-file-field').classList.toggle('d-none', type !== 'file');
    document.getElementById('item-content-field').classList.toggle('d-none', type !== 'note');
}

async function createItem() {
    const form = document.getElementById('item-form');
    const fd = new FormData(form);
    const docId = fd.get('document_id');
    const type = fd.get('item_type');
    if (type === 'link' && !fd.get('url').trim()) return alert('Введите ссылку');
    if (type === 'file' && !fd.get('file').size) return alert('Выберите файл');
    if (type === 'note' && !fd.get('content').trim()) return alert('Введите текст заметки');

    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/documents/${docId}/items`, {
            method: 'POST',
            body: fd
        });
        form.reset();
        toggleItemType();
        bootstrap.Modal.getInstance(document.getElementById('itemModal')).hide();
        loadSections(PROJECT_ID);
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

function showEditItemModal(docId, item) {
    const f = document.getElementById('edit-item-form');
    f.reset();
    f.doc_id.value = docId;
    f.item_id.value = item.id;
    f.title.value = item.title || '';
    const urlWrap = document.getElementById('edit-item-url-wrap');
    const contentWrap = document.getElementById('edit-item-content-wrap');
    const fileWrap = document.getElementById('edit-item-file-wrap');
    if (item.item_type === 'link') {
        urlWrap.classList.remove('d-none');
        contentWrap.classList.add('d-none');
        fileWrap.classList.add('d-none');
        f.url.value = item.url || '';
        f.content.value = '';
    } else if (item.item_type === 'note') {
        urlWrap.classList.add('d-none');
        contentWrap.classList.remove('d-none');
        fileWrap.classList.add('d-none');
        f.url.value = '';
        f.content.value = item.content || '';
    } else {
        urlWrap.classList.add('d-none');
        contentWrap.classList.add('d-none');
        fileWrap.classList.remove('d-none');
        f.url.value = '';
        f.content.value = '';
    }
    new bootstrap.Modal(document.getElementById('editItemModal')).show();
}

async function updateItem() {
    const f = document.getElementById('edit-item-form');
    const docId = f.doc_id.value;
    const itemId = f.item_id.value;
    const fd = new FormData();
    fd.append('title', f.title.value);
    if (!f.url.parentElement.classList.contains('d-none')) {
        fd.append('url', f.url.value);
    }
    if (!f.content.parentElement.classList.contains('d-none')) {
        fd.append('content', f.content.value);
    }
    if (!f.file.parentElement.classList.contains('d-none') && f.file.files[0]) {
        fd.append('file', f.file.files[0]);
    }
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/documents/${docId}/items/${itemId}`, {
            method: 'PATCH',
            body: fd
        });
        bootstrap.Modal.getInstance(document.getElementById('editItemModal')).hide();
        loadSections(PROJECT_ID);
        showToast('Изменения сохранены');
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

function deleteItemFromEditModal() {
    const f = document.getElementById('edit-item-form');
    const docId = f.doc_id.value;
    const itemId = f.item_id.value;
    bootstrap.Modal.getInstance(document.getElementById('editItemModal')).hide();
    deleteItem(docId, itemId);
}

async function deleteItem(docId, itemId) {
    if (!confirm('Удалить этот элемент?')) return;
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/documents/${docId}/items/${itemId}`, { method: 'DELETE' });
        loadSections(PROJECT_ID);
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

function openItemInAlexandrite(item) {
    if (!item.file_path) return alert('Файл не найден');
    const root = encodeURIComponent(LOCAL_STORAGE_PATH || './data/uploads');
    const path = encodeURIComponent(item.file_path);
    window.open(`/alexandrite?root=${root}&open=${path}`, '_blank');
}

async function openItemLocally(item) {
    try {
        await api(getItemOpenUrl(item), { method: 'POST' });
        showToast('Файл открыт в приложении');
    } catch (e) {
        showToast(`Не удалось открыть файл: ${e.message}`, 'warning');
    }
}

// ═══════════════════════════════════════════════════
// ПРЕДПРОСМОТР
// ═══════════════════════════════════════════════════

function getYoutubeEmbedUrl(url) {
    if (!url) return '';
    const match = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]+)/);
    return match ? `https://www.youtube.com/embed/${match[1]}` : url;
}

function getItemPreviewUrl(item) {
    if (item.item_type === 'link') return item.url;
    return `${API_BASE}/projects/${PROJECT_ID}/documents/${item.document_id}/items/${item.id}/preview`;
}

function getItemDownloadUrl(item) {
    return `${API_BASE}/projects/${PROJECT_ID}/documents/${item.document_id}/items/${item.id}/download`;
}

function getItemOpenUrl(item) {
    return `${API_BASE}/projects/${PROJECT_ID}/documents/${item.document_id}/items/${item.id}/open`;
}

async function openItemPreview(item) {
    const cat = item.category || detectCategoryFromItem(item);
    const isOffice = item.item_type === 'file' && ['word', 'spreadsheet', 'presentation'].includes(cat);

    if (isOffice) {
        if (isLocalhost()) {
            return openItemLocally(item);
        }
        return openItemInCollabora(item);
    }

    const modalEl = document.getElementById('previewModal');
    const content = document.getElementById('preview-content');
    const title = document.getElementById('preview-title');
    const downloadBtn = document.getElementById('preview-download');

    title.textContent = item.file_name || item.title || 'Просмотр';
    downloadBtn.href = getItemDownloadUrl(item);
    downloadBtn.style.display = item.item_type === 'link' ? 'none' : 'inline-block';
    content.innerHTML = '<div class="text-center p-5"><div class="spinner-border"></div></div>';

    const modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
    modal.show();

    switch (cat) {
        case 'note': {
            content.innerHTML = `
                <div class="p-4">
                    <div class="note-preview">
                        <h5 class="mb-3">${escapeHtml(item.title || 'Заметка')}</h5>
                        <div class="note-text">${escapeHtml(item.content || '').replace(/\n/g, '<br>')}</div>
                    </div>
                </div>`;
            break;
        }
        case 'image': {
            content.innerHTML = `<div class="text-center p-3"><img src="${getItemPreviewUrl(item)}" class="img-fluid rounded" style="max-height:75vh;" onerror="previewError()"></div>`;
            break;
        }
        case 'video': {
            content.innerHTML = `<div class="p-3"><video controls class="w-100 rounded" style="max-height:75vh;"><source src="${getItemPreviewUrl(item)}">Ваш браузер не поддерживает видео.</video></div>`;
            break;
        }
        case 'audio': {
            content.innerHTML = `<div class="p-5 text-center"><audio controls class="w-100"><source src="${getItemPreviewUrl(item)}">Ваш браузер не поддерживает аудио.</audio></div>`;
            break;
        }
        case 'pdf': {
            content.innerHTML = `<iframe src="${getItemPreviewUrl(item)}" class="w-100 border-0" style="height:75vh;"></iframe>`;
            break;
        }
        case 'youtube': {
            const embed = getYoutubeEmbedUrl(item.url);
            content.innerHTML = `<div class="ratio ratio-16x9"><iframe src="${embed}" allowfullscreen></iframe></div>`;
            break;
        }
        case 'text':
        case 'code': {
            if (item.item_type === 'link') {
                content.innerHTML = `<iframe src="${escapeHtml(item.url)}" class="w-100 border-0" style="height:75vh;"></iframe>`;
            } else if (isMarkdownFile(item.file_name)) {
                try {
                    const resp = await fetch(getItemPreviewUrl(item));
                    if (!resp.ok) throw new Error('HTTP ' + resp.status);
                    const text = await resp.text();
                    const html = typeof marked !== 'undefined'
                        ? marked.parse(text)
                        : escapeHtml(text).replace(/\n/g, '<br>');
                    content.innerHTML = `<div class="markdown-preview">${html}</div>`;
                } catch (e) {
                    previewError();
                }
            } else {
                try {
                    const resp = await fetch(getItemPreviewUrl(item));
                    if (!resp.ok) throw new Error('HTTP ' + resp.status);
                    const text = await resp.text();
                    content.innerHTML = `<div class="p-3"><pre class="preview-code"><code>${escapeHtml(text)}</code></pre></div>`;
                } catch (e) {
                    previewError();
                }
            }
            break;
        }
        default: {
            if (item.item_type === 'file' && cat === 'archive') {
                const label = getItemLabel(item);
                content.innerHTML = `
                    <div class="empty-state py-5">
                        <i class="bi bi-file-earmark-x"></i>
                        <p>Предпросмотр недоступен для этого формата (${escapeHtml(label)})</p>
                        <a href="${getItemDownloadUrl(item)}" class="btn btn-success">
                            <i class="bi bi-download me-1"></i> Скачать файл
                        </a>
                    </div>`;
            } else if (item.item_type === 'link') {
                content.innerHTML = `<iframe src="${escapeHtml(item.url)}" class="w-100 border-0" style="height:75vh;"></iframe>`;
            } else {
                content.innerHTML = `<iframe src="${getItemPreviewUrl(item)}" class="w-100 border-0" style="height:75vh;"></iframe>`;
            }
        }
    }
}

async function openItemInCollabora(item) {
    const modalEl = document.getElementById('previewModal');
    const content = document.getElementById('preview-content');
    const title = document.getElementById('preview-title');
    const downloadBtn = document.getElementById('preview-download');

    title.textContent = item.file_name || item.title || 'Документ';
    downloadBtn.href = getItemDownloadUrl(item);
    downloadBtn.style.display = 'inline-block';
    content.innerHTML = '<div class="text-center p-5"><div class="spinner-border"></div></div>';

    const modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
    modal.show();

    try {
        const data = await api(`${API_BASE}/projects/${PROJECT_ID}/documents/${item.document_id}/items/${item.id}/collabora`);
        content.innerHTML = `<iframe src="${escapeHtml(data.url)}" class="w-100 border-0" style="height:75vh;" sandbox="allow-scripts allow-same-origin allow-popups allow-forms"></iframe>`;
    } catch (e) {
        content.innerHTML = `
            <div class="empty-state py-5">
                <i class="bi bi-exclamation-triangle"></i>
                <p>Не удалось открыть в Collabora: ${escapeHtml(e.message)}</p>
                <a href="${getItemDownloadUrl(item)}" class="btn btn-success">
                    <i class="bi bi-download me-1"></i> Скачать файл
                </a>
            </div>`;
    }
}

function isMarkdownFile(fileName) {
    if (!fileName) return false;
    const ext = fileName.split('.').pop().toLowerCase();
    return ext === 'md' || ext === 'markdown';
}

function previewError() {
    const content = document.getElementById('preview-content');
    content.innerHTML = `
        <div class="empty-state py-5">
            <i class="bi bi-exclamation-triangle"></i>
            <p>Не удалось загрузить предпросмотр</p>
        </div>`;
}

// ═══════════════════════════════════════════════════
// БОКОВЫЕ ПАНЕЛИ
// ═══════════════════════════════════════════════════

async function loadSidebars() {
    try {
        const [leftBlocks, rightBlocks] = await Promise.all([
            api(`${API_BASE}/sidebar/blocks?position=left`),
            api(`${API_BASE}/sidebar/blocks?position=right`)
        ]);
        renderSidebarBlocks('left', leftBlocks);
        renderSidebarBlocks('right', rightBlocks);
    } catch (e) {
        console.error('Sidebar load error:', e);
    }
}

function getSidebarBlockCollapsedState() {
    return JSON.parse(localStorage.getItem('sidebar_blocks_collapsed') || '{}');
}

function isSidebarBlockCollapsed(blockId) {
    // По умолчанию блоки свёрнуты
    const state = getSidebarBlockCollapsedState();
    return state[blockId] !== false;
}

function toggleSidebarBlock(blockId) {
    const state = getSidebarBlockCollapsedState();
    state[blockId] = !isSidebarBlockCollapsed(blockId);
    localStorage.setItem('sidebar_blocks_collapsed', JSON.stringify(state));
    const block = document.querySelector(`.sidebar-block[data-id="${blockId}"]`);
    if (!block) return;
    const list = block.querySelector('.sidebar-link-list');
    const icon = block.querySelector('.sidebar-block-toggle i');
    if (list) list.classList.toggle('d-none');
    if (icon) {
        icon.classList.toggle('bi-chevron-down');
        icon.classList.toggle('bi-chevron-right');
    }
}

function renderSidebarBlocks(position, blocks) {
    const container = document.getElementById(`sidebar-${position}-blocks`);
    if (!container) return;
    if (!blocks || !blocks.length) {
        container.innerHTML = `<div class="text-muted small text-center py-3">Нет блоков</div>`;
        return;
    }
    container.innerHTML = blocks.map(block => {
        const collapsed = isSidebarBlockCollapsed(block.id);
        const blockNote = block.note ? `<span class="sidebar-note-badge" onclick="event.stopPropagation(); openSidebarNoteModal('block', ${block.id})" title="${escapeHtml(block.note)}"><i class="bi bi-sticky"></i></span>` : '';
        return `
        <div class="sidebar-block fade-in" data-id="${block.id}" data-type="block" oncontextmenu="handleSidebarContextMenu(event, 'block', ${block.id}, '${escapeHtml(block.title).replace(/'/g, "\\'")}')">
            <div class="sidebar-block-header">
                <div class="sidebar-block-title-wrap">
                    <h4 class="sidebar-block-title">${escapeHtml(block.title)}</h4>
                </div>
                ${blockNote}
                <div class="sidebar-block-toggle" onclick="event.stopPropagation(); toggleSidebarBlock(${block.id})" title="Свернуть/развернуть"><i class="bi ${collapsed ? 'bi-chevron-right' : 'bi-chevron-down'}"></i></div>
                <div class="sidebar-drag-handle" title="Переместить блок" onclick="event.stopPropagation()"><i class="bi bi-grip-vertical"></i></div>
            </div>
            <ul class="sidebar-link-list ${collapsed ? 'd-none' : ''}" data-block-id="${block.id}">
                ${(block.links || []).map(link => {
                    const linkNote = link.note ? `<span class="sidebar-note-badge" onclick="event.stopPropagation(); openSidebarNoteModal('link', ${link.id})" title="${escapeHtml(link.note)}"><i class="bi bi-sticky"></i></span>` : '';
                    return `
                    <li class="sidebar-link-item" data-id="${link.id}" data-type="link" oncontextmenu="handleSidebarContextMenu(event, 'link', ${link.id}, '${escapeHtml(link.title).replace(/'/g, "\\'")}')">
                        <a href="${escapeHtml(link.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">
                            ${escapeHtml(link.title)}
                        </a>
                        ${linkNote}
                        <div class="sidebar-link-drag-handle" title="Переместить" onclick="event.stopPropagation()"><i class="bi bi-grip-vertical"></i></div>
                    </li>
                `}).join('')}
            </ul>
        </div>
    `}).join('');
    initSidebarBlockSortable(position);
    container.querySelectorAll('.sidebar-link-list').forEach(ul => {
        initSidebarLinkSortable(ul);
    });
}

function showAddBlockModal(position) {
    document.getElementById('sidebar-block-position').value = position;
    document.getElementById('sidebar-block-form').reset();
    const modalEl = document.getElementById('sidebarBlockModal');
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

async function createSidebarBlock() {
    const form = document.getElementById('sidebar-block-form');
    const data = Object.fromEntries(new FormData(form));
    if (!data.title.trim()) return alert('Введите название блока');
    try {
        await api(`${API_BASE}/sidebar/blocks`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('sidebarBlockModal')).hide();
        loadSidebars();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function deleteSidebarBlock(blockId) {
    if (!confirm('Удалить блок и все ссылки в нем?')) return;
    try {
        await api(`${API_BASE}/sidebar/blocks/${blockId}`, { method: 'DELETE' });
        loadSidebars();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

function showAddLinkModal(blockId) {
    document.getElementById('sidebar-link-block-id').value = blockId;
    document.getElementById('sidebar-link-form').reset();
    const modalEl = document.getElementById('sidebarLinkModal');
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

async function createSidebarLink() {
    const form = document.getElementById('sidebar-link-form');
    const data = Object.fromEntries(new FormData(form));
    const blockId = data.block_id;
    if (!data.title.trim() || !data.url.trim()) return alert('Заполните все поля');
    try {
        await api(`${API_BASE}/sidebar/blocks/${blockId}/links`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title: data.title, url: data.url})
        });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('sidebarLinkModal')).hide();
        loadSidebars();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function deleteSidebarLink(linkId) {
    if (!confirm('Удалить ссылку?')) return;
    try {
        await api(`${API_BASE}/sidebar/links/${linkId}`, { method: 'DELETE' });
        loadSidebars();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

// ═══════════════════════════════════════════════════
// СОРТИРОВКА БОКОВОЙ ПАНЕЛИ
// ═══════════════════════════════════════════════════

let sidebarBlockSortables = {};
let sidebarLinkSortables = {};

function initSidebarBlockSortable(position) {
    const el = document.getElementById(`sidebar-${position}-blocks`);
    if (!el) return;
    if (sidebarBlockSortables[position]) sidebarBlockSortables[position].destroy();

    sidebarBlockSortables[position] = Sortable.create(el, {
        animation: 150,
        handle: '.sidebar-drag-handle',
        draggable: '.sidebar-block',
        ghostClass: 'sortable-ghost',
        dragClass: 'sortable-drag',
        onEnd: function () {
            const ids = Array.from(el.children)
                .filter(child => child.classList.contains('sidebar-block'))
                .map(child => parseInt(child.dataset.id));
            if (ids.length > 1) {
                reorderSidebarBlocks(ids);
            }
        }
    });
}

function initSidebarLinkSortable(ul) {
    if (!ul) return;
    const blockId = ul.dataset.blockId;
    if (!blockId) return;
    if (sidebarLinkSortables[blockId]) sidebarLinkSortables[blockId].destroy();

    sidebarLinkSortables[blockId] = Sortable.create(ul, {
        animation: 150,
        handle: '.sidebar-link-drag-handle',
        draggable: '.sidebar-link-item',
        ghostClass: 'sortable-ghost',
        dragClass: 'sortable-drag',
        onEnd: function () {
            const ids = Array.from(ul.children)
                .filter(child => child.classList.contains('sidebar-link-item'))
                .map(child => parseInt(child.dataset.id));
            if (ids.length > 1) {
                reorderSidebarLinks(blockId, ids);
            }
        }
    });
}

async function reorderSidebarBlocks(blockIds) {
    try {
        await api(`${API_BASE}/sidebar/blocks/reorder`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({block_ids: blockIds})
        });
    } catch (e) {
        console.error('Reorder sidebar blocks failed:', e);
        loadSidebars();
    }
}

async function reorderSidebarLinks(blockId, linkIds) {
    try {
        await api(`${API_BASE}/sidebar/blocks/${blockId}/links/reorder`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({link_ids: linkIds})
        });
    } catch (e) {
        console.error('Reorder sidebar links failed:', e);
        loadSidebars();
    }
}

// ═══════════════════════════════════════════════════
// КОНТЕКСТНОЕ МЕНЮ БОКОВОЙ ПАНЕЛИ
// ═══════════════════════════════════════════════════

let sidebarContextTarget = null;

function handleSidebarContextMenu(event, type, id, title) {
    event.preventDefault();
    event.stopPropagation();
    let url = null;
    if (type === 'link') {
        const targetEl = event.target && event.target.nodeType === Node.ELEMENT_NODE ? event.target : event.target.parentElement;
        const linkEl = targetEl ? targetEl.closest('.sidebar-link-item') : null;
        const a = linkEl ? linkEl.querySelector('a') : null;
        url = a ? a.getAttribute('href') : null;
        if (!url) console.warn('Sidebar context menu: link href not found', event.target, linkEl, a);
    }
    sidebarContextTarget = { type, id, title, url };
    console.log('Sidebar context menu target:', sidebarContextTarget);
    const menu = document.getElementById('sidebar-context-menu');
    const firstItem = menu.querySelector('[data-action="add-link"]');
    if (type === 'link') {
        firstItem.innerHTML = '<i class="bi bi-link-45deg"></i> Скопировать ссылку';
    } else {
        firstItem.innerHTML = '<i class="bi bi-plus-lg"></i> Добавить ссылку';
    }
    menu.style.display = 'block';
    const x = Math.min(event.clientX, window.innerWidth - 180);
    const y = Math.min(event.clientY, window.innerHeight - 120);
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
}

function hideSidebarContextMenu() {
    const menu = document.getElementById('sidebar-context-menu');
    if (menu) menu.style.display = 'none';
    sidebarContextTarget = null;
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('#sidebar-context-menu')) hideSidebarContextMenu();
    if (!e.target.closest('#project-item-context-menu')) hideProjectItemContextMenu();

    // Сбросить подсветку строки файла при клике вне строки
    if (!e.target.closest('.doc-item')) {
        document.querySelectorAll('.doc-item-highlighted').forEach(el => el.classList.remove('doc-item-highlighted'));
    }
});
document.addEventListener('scroll', (e) => {
    hideSidebarContextMenu();
    hideProjectItemContextMenu();
}, true);
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        hideSidebarContextMenu();
        hideProjectItemContextMenu();
    }
});

const projectItemContextMenu = document.getElementById('project-item-context-menu');
if (projectItemContextMenu) {
    projectItemContextMenu.addEventListener('click', (e) => {
        const item = e.target.closest('.project-item-context-item');
        if (!item || !projectItemContextTarget) return;
        const action = item.dataset.action;
        const { docId, itemId, item: itemData } = projectItemContextTarget;
        hideProjectItemContextMenu();
        if (action === 'copy-link') {
            copyProjectItemShareLink(docId, itemId);
        } else if (action === 'preview' && itemData) {
            openItemPreview(itemData);
        } else if (action === 'alexandrite' && itemData) {
            openItemInAlexandrite(itemData);
        } else if (action === 'download' && itemData) {
            window.location.href = getItemDownloadUrl(itemData);
        } else if (action === 'edit') {
            showEditItemModal(docId, itemData);
        } else if (action === 'delete') {
            deleteItem(docId, itemId);
        }
    });
}

const sidebarContextMenu = document.getElementById('sidebar-context-menu');
if (sidebarContextMenu) {
    sidebarContextMenu.addEventListener('click', (e) => {
    const item = e.target.closest('.sidebar-context-item');
    if (!item || !sidebarContextTarget) return;
    const action = item.dataset.action;
    const { type, id, url } = sidebarContextTarget;
    hideSidebarContextMenu();
    if (action === 'add-link') {
        if (type === 'block') {
            showAddLinkModal(id);
        } else if (type === 'link' && url) {
            const text = url;
            console.log('Trying to copy link:', text);
            const fallbackCopy = (txt) => {
                const ta = document.createElement('textarea');
                ta.value = txt;
                ta.setAttribute('readonly', '');
                ta.style.position = 'fixed';
                ta.style.top = '-9999px';
                ta.style.left = '-9999px';
                document.body.appendChild(ta);
                ta.focus();
                ta.setSelectionRange(0, txt.length);
                try {
                    const ok = document.execCommand('copy');
                    console.log('Fallback copy result:', ok);
                } catch (e) {
                    console.error('Fallback copy error:', e);
                }
                document.body.removeChild(ta);
            };
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text)
                    .then(() => console.log('Clipboard API copy success'))
                    .catch((err) => {
                        console.warn('Clipboard API failed, using fallback:', err);
                        fallbackCopy(text);
                    });
            } else {
                console.log('Clipboard API unavailable, using fallback');
                fallbackCopy(text);
            }
        }
    } else if (action === 'note') {
        openSidebarNoteModal(type, id);
    } else if (action === 'edit') {
        if (type === 'block') openEditBlockModal(id);
        else openEditLinkModal(id);
    } else if (action === 'delete') {
        if (type === 'block') deleteSidebarBlock(id);
        else deleteSidebarLink(id);
    }
});
}

// ── Редактирование блока ──

async function openEditBlockModal(blockId) {
    try {
        const blocks = await api(`${API_BASE}/sidebar/blocks`);
        const block = blocks.find(b => b.id === blockId);
        if (!block) return alert('Блок не найден');
        document.getElementById('edit-sidebar-block-id').value = blockId;
        document.getElementById('edit-sidebar-block-title').value = block.title || '';
        new bootstrap.Modal(document.getElementById('editSidebarBlockModal')).show();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function updateSidebarBlock() {
    const id = document.getElementById('edit-sidebar-block-id').value;
    const title = document.getElementById('edit-sidebar-block-title').value;
    if (!title.trim()) return alert('Введите название');
    try {
        await api(`${API_BASE}/sidebar/blocks/${id}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title})
        });
        bootstrap.Modal.getInstance(document.getElementById('editSidebarBlockModal')).hide();
        loadSidebars();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

// ── Редактирование ссылки ──

async function openEditLinkModal(linkId) {
    try {
        const blocks = await api(`${API_BASE}/sidebar/blocks`);
        let link = null;
        for (const block of blocks) {
            link = (block.links || []).find(l => l.id === linkId);
            if (link) break;
        }
        if (!link) return alert('Ссылка не найдена');
        document.getElementById('edit-sidebar-link-id').value = linkId;
        document.getElementById('edit-sidebar-link-title').value = link.title || '';
        document.getElementById('edit-sidebar-link-url').value = link.url || '';
        new bootstrap.Modal(document.getElementById('editSidebarLinkModal')).show();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function updateSidebarLink() {
    const id = document.getElementById('edit-sidebar-link-id').value;
    const title = document.getElementById('edit-sidebar-link-title').value;
    const url = document.getElementById('edit-sidebar-link-url').value;
    if (!title.trim() || !url.trim()) return alert('Заполните все поля');
    try {
        await api(`${API_BASE}/sidebar/links/${id}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title, url})
        });
        bootstrap.Modal.getInstance(document.getElementById('editSidebarLinkModal')).hide();
        loadSidebars();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

// ── Заметка ──

async function openSidebarNoteModal(type, id) {
    try {
        let note = '';
        if (type === 'block') {
            const blocks = await api(`${API_BASE}/sidebar/blocks`);
            const block = blocks.find(b => b.id === id);
            note = block?.note || '';
        } else {
            const blocks = await api(`${API_BASE}/sidebar/blocks`);
            for (const block of blocks) {
                const link = (block.links || []).find(l => l.id === id);
                if (link) { note = link.note || ''; break; }
            }
        }
        document.getElementById('sidebar-note-target-id').value = id;
        document.getElementById('sidebar-note-target-type').value = type;
        document.getElementById('sidebar-note-text').value = note;
        new bootstrap.Modal(document.getElementById('sidebarNoteModal')).show();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function saveSidebarNote() {
    const id = document.getElementById('sidebar-note-target-id').value;
    const type = document.getElementById('sidebar-note-target-type').value;
    const note = document.getElementById('sidebar-note-text').value;
    try {
        if (type === 'block') {
            await api(`${API_BASE}/sidebar/blocks/${id}`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({note})
            });
        } else {
            await api(`${API_BASE}/sidebar/links/${id}`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({note})
            });
        }
        bootstrap.Modal.getInstance(document.getElementById('sidebarNoteModal')).hide();
        loadSidebars();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

// ═══════════════════════════════════════════════════
// ПЛАНИРОВЩИК (из bd-arm)
// ═══════════════════════════════════════════════════

async function fillSchedulerTasks() {
    const select = document.getElementById('project-select');
    if (!select) return;
    try {
        const data = await api(`${API_BASE}/scheduler/tasks`);
        const tasks = data.tasks || [];
        if (!tasks.length) {
            select.innerHTML = '<option value="" disabled selected>-- Нет доступных тасок --</option>';
            return;
        }
        select.innerHTML = '<option value="" disabled selected>-- Выберите таск --</option>' +
            tasks.map(t => `<option value="${escapeHtml(t.key)}">${escapeHtml(t.name)}</option>`).join('');
    } catch (e) {
        select.innerHTML = '<option value="" disabled selected>-- Ошибка загрузки --</option>';
    }
}

function initScheduler() {
    const scheduleBtn = document.getElementById('schedule-btn');
    const refreshBtn = document.getElementById('refresh-atq');
    const removeBtn = document.getElementById('remove-btn');
    const statusEl = document.getElementById('status-message');
    const atqEl = document.getElementById('atq-output');
    const taskIdInput = document.getElementById('task-id');

    if (!scheduleBtn) return;

    const showStatus = (text, isError) => {
        if (!statusEl) return;
        statusEl.textContent = text;
        statusEl.className = 'scheduler-status mt-3 ' + (isError ? 'error' : 'success');
        setTimeout(() => { statusEl.textContent = ''; statusEl.className = 'scheduler-status mt-3'; }, 5000);
    };

    const refreshAtq = async () => {
        if (!atqEl) return;
        try {
            const data = await api(`${API_BASE}/scheduler/atq`);
            atqEl.textContent = data.output || 'Нет задач в очереди';
        } catch (error) {
            atqEl.textContent = 'Ошибка загрузки очереди';
        }
    };

    scheduleBtn.addEventListener('click', async () => {
        const project = document.getElementById('project-select').value;
        const datetime = document.getElementById('datetime').value;
        if (!project || !datetime) {
            showStatus('Заполните все поля', true);
            return;
        }
        try {
            const data = await api(`${API_BASE}/scheduler/schedule`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({project, datetime})
            });
            if (data.error) {
                showStatus(data.error, true);
            } else {
                showStatus(data.message || 'Задача успешно добавлена!', false);
            }
            refreshAtq();
        } catch (error) {
            showStatus(error.message, true);
        }
    });

    removeBtn.addEventListener('click', async () => {
        const taskId = taskIdInput.value.trim();
        if (!taskId) {
            showStatus('Введите ID задачи', true);
            return;
        }
        try {
            await api(`${API_BASE}/scheduler/remove-task`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: taskId})
            });
            showStatus(`Задача ${taskId} успешно удалена!`, false);
            taskIdInput.value = '';
            refreshAtq();
        } catch (error) {
            showStatus(error.message, true);
        }
    });

    refreshBtn.addEventListener('click', refreshAtq);
    refreshAtq();
}

// ═══════════════════════════════════════════════════
// КАЛЕНДАРЬ
// ═══════════════════════════════════════════════════

let calendarInstance = null;
let calendarEventsCache = [];

function initSchedulerTabs() {
    const tabEl = document.querySelectorAll('#schedulerTab button[data-bs-toggle="tab"]');
    tabEl.forEach(tab => {
        tab.addEventListener('shown.bs.tab', event => {
            const target = event.target.getAttribute('data-bs-target');
            if (target === '#calendar-pane' && !calendarInstance) {
                initCalendar();
            }
            if (target === '#calendar-pane') {
                loadCalendarEvents();
            }
            if (calendarInstance) {
                requestAnimationFrame(() => {
                    setTimeout(() => calendarInstance.updateSize(), 150);
                });
            }
        });
    });

    window.addEventListener('resize', () => {
        if (calendarInstance) calendarInstance.updateSize();
    });

}

function initCollapsibleBackupSections() {
    const titles = document.querySelectorAll('.collapsible-section-title');
    titles.forEach(title => {
        const key = title.dataset.collapseKey;
        const targetId = title.getAttribute('data-bs-target');
        const targetEl = document.querySelector(targetId);
        if (!targetEl) return;

        const defaultExpanded = title.dataset.collapseDefault === 'true';
        const saved = key ? localStorage.getItem(`collapse_${key}`) : null;
        const shouldShow = saved === null ? defaultExpanded : saved === 'true';
        const collapse = bootstrap.Collapse.getOrCreateInstance(targetEl, { toggle: false });
        if (shouldShow) {
            collapse.show();
            title.setAttribute('aria-expanded', 'true');
        } else {
            collapse.hide();
            title.setAttribute('aria-expanded', 'false');
        }

        targetEl.addEventListener('shown.bs.collapse', () => {
            title.setAttribute('aria-expanded', 'true');
            if (key) localStorage.setItem(`collapse_${key}`, 'true');
        });
        targetEl.addEventListener('hidden.bs.collapse', () => {
            title.setAttribute('aria-expanded', 'false');
            if (key) localStorage.setItem(`collapse_${key}`, 'false');
        });
    });
}

async function loadCalendarEvents() {
    try {
        const events = await api(`${API_BASE}/calendar/events`);
        calendarEventsCache = events || [];
        renderCalendarEventsList();
        if (calendarInstance) {
            calendarInstance.removeAllEvents();
            calendarEventsCache.forEach(e => {
                calendarInstance.addEvent({
                    id: String(e.id),
                    title: e.title,
                    start: e.start_date,
                    end: e.end_date,
                    allDay: e.all_day,
                    color: e.color,
                    extendedProps: { description: e.description, note: e.note }
                });
            });
        }
    } catch (e) {
        console.error('Calendar load error:', e);
        const container = document.getElementById('calendar-events-container');
        if (container) container.innerHTML = `<div class="alert alert-danger small">Ошибка загрузки событий</div>`;
    }
}

function renderCalendarEventsList() {
    const container = document.getElementById('calendar-events-container');
    if (!container) return;
    const sorted = [...calendarEventsCache].sort((a, b) => new Date(a.start_date) - new Date(b.start_date));
    if (!sorted.length) {
        container.innerHTML = `<div class="text-muted small text-center py-3">Нет событий</div>`;
        return;
    }
    const now = new Date();
    container.innerHTML = sorted.map(e => {
        const start = new Date(e.start_date);
        const isPast = start < now;
        const dateStr = start.toLocaleDateString('ru-RU');
        const timeStr = e.all_day ? 'весь день' : start.toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'});
        return `
        <div class="calendar-event-item ${isPast ? 'past' : ''}" onclick="editCalendarEvent(${e.id})">
            <div class="calendar-event-bar" style="background:${escapeHtml(e.color || '#a78bfa')}"></div>
            <div class="calendar-event-info">
                <div class="calendar-event-title">${escapeHtml(e.title)}</div>
                <div class="calendar-event-meta">${dateStr} · ${timeStr}</div>
            </div>
        </div>`;
    }).join('');
}

function initCalendar() {
    const calendarEl = document.getElementById('calendar');
    if (!calendarEl || typeof FullCalendar === 'undefined') return;
    calendarInstance = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'ru',
        firstDay: 1,
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,listWeek'
        },
        height: 520,
        eventClick: function(info) {
            editCalendarEvent(parseInt(info.event.id));
        },
        dateClick: function(info) {
            showCalendarEventModal(null, info.dateStr);
        },
        events: []
    });
    calendarInstance.render();
}

function showCalendarEventModal(eventId, dateStr) {
    const form = document.getElementById('calendar-event-form');
    const titleEl = document.getElementById('calendar-event-modal-title');
    const deleteBtn = document.getElementById('calendar-event-delete-btn');
    form.reset();
    if (eventId) {
        const event = calendarEventsCache.find(e => e.id === eventId);
        if (!event) return;
        titleEl.textContent = 'Редактировать событие';
        document.getElementById('calendar-event-id').value = event.id;
        document.getElementById('calendar-event-title').value = event.title || '';
        document.getElementById('calendar-event-description').value = event.description || '';
        document.getElementById('calendar-event-start').value = event.start_date ? event.start_date.slice(0, 16) : '';
        document.getElementById('calendar-event-end').value = event.end_date ? event.end_date.slice(0, 16) : '';
        document.getElementById('calendar-event-color').value = event.color || '#a78bfa';
        document.getElementById('calendar-event-all-day').checked = event.all_day || false;
        deleteBtn.style.display = 'inline-block';
    } else {
        titleEl.textContent = 'Новое событие';
        document.getElementById('calendar-event-id').value = '';
        document.getElementById('calendar-event-color').value = '#a78bfa';
        if (dateStr) {
            document.getElementById('calendar-event-start').value = dateStr + 'T09:00';
        }
        deleteBtn.style.display = 'none';
    }
    new bootstrap.Modal(document.getElementById('calendarEventModal')).show();
}

function editCalendarEvent(eventId) {
    showCalendarEventModal(eventId);
}

async function saveCalendarEvent() {
    const id = document.getElementById('calendar-event-id').value;
    const title = document.getElementById('calendar-event-title').value;
    const description = document.getElementById('calendar-event-description').value;
    const start = document.getElementById('calendar-event-start').value;
    const end = document.getElementById('calendar-event-end').value;
    const color = document.getElementById('calendar-event-color').value;
    const allDay = document.getElementById('calendar-event-all-day').checked;
    if (!title.trim() || !start) {
        alert('Введите название и дату начала');
        return;
    }
    const payload = { title, description, start_date: start, end_date: end || null, color, all_day: allDay };
    try {
        if (id) {
            await api(`${API_BASE}/calendar/events/${id}`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
        } else {
            await api(`${API_BASE}/calendar/events`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
        }
        bootstrap.Modal.getInstance(document.getElementById('calendarEventModal')).hide();
        loadCalendarEvents();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function deleteCalendarEvent() {
    const id = document.getElementById('calendar-event-id').value;
    if (!id || !confirm('Удалить событие?')) return;
    try {
        await api(`${API_BASE}/calendar/events/${id}`, { method: 'DELETE' });
        bootstrap.Modal.getInstance(document.getElementById('calendarEventModal')).hide();
        loadCalendarEvents();
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

// ═══════════════════════════════════════════════════
// БЭКАП / СИНХРОНИЗАЦИЯ
// ═══════════════════════════════════════════════════

async function loadBackupStats() {
    const localEl = document.getElementById('backup-local-stats');
    const yandexEl = document.getElementById('backup-yandex-stats');
    try {
        const data = await api(`${API_BASE}/backup/stats`);
        const ls = data.local;
        localEl.innerHTML = `
            <div class="row g-3">
                <div class="col-md-6">
                    <div class="backup-stat-row"><span>Проекты</span><span class="badge bg-purple">${ls.projects}</span></div>
                    <div class="backup-stat-row"><span>Разделы</span><span class="badge bg-purple">${ls.sections}</span></div>
                    <div class="backup-stat-row"><span>Группы</span><span class="badge bg-purple">${ls.documents}</span></div>
                    <div class="backup-stat-row"><span>Ссылки</span><span class="badge bg-info">${ls.links}</span></div>
                    <div class="backup-stat-row"><span>Файлы</span><span class="badge bg-primary">${ls.files}</span></div>
                    <div class="backup-stat-row"><span>Заметки</span><span class="badge bg-warning text-dark">${ls.notes}</span></div>
                </div>
                <div class="col-md-6">
                    <div class="backup-stat-row"><span>Заметки к ссылкам</span><span class="badge bg-warning text-dark">${ls.sidebar_link_notes}</span></div>
                    <div class="backup-stat-row"><span>Боковые блоки</span><span class="badge bg-brown">${ls.sidebar_blocks}</span></div>
                    <div class="backup-stat-row"><span>Боковые ссылки</span><span class="badge bg-brown">${ls.sidebar_links}</span></div>
                    <div class="backup-stat-row"><span>События календаря</span><span class="badge bg-success">${ls.calendar_events}</span></div>
                    <div class="backup-stat-row"><span>Общий размер файлов</span><span class="backup-stat-value backup-size-value">${formatSize(ls.total_files_size)}</span></div>
                </div>
            </div>
        `;

        const ys = data.yandex;
        if (ys.connected) {
            yandexEl.innerHTML = `
                <div class="backup-stat-row"><span>Статус</span><span class="badge bg-success backup-status-badge">Подключен</span></div>
                <div class="backup-stat-row"><span>Пользователь</span><span class="backup-stat-value">${escapeHtml(ys.info)}</span></div>
                <div class="backup-stat-row"><span>Использовано</span><span class="backup-stat-value">${escapeHtml(ys.used)} / ${escapeHtml(ys.total)}</span></div>
            `;
        } else {
            yandexEl.innerHTML = `
                <div class="backup-stat-row"><span>Статус</span><span class="badge bg-danger">Не подключен</span></div>
                <div class="backup-stat-row"><span class="backup-stat-value">${escapeHtml(ys.info)}</span></div>
            `;
        }
    } catch (e) {
        localEl.innerHTML = `<div class="alert alert-danger small">Ошибка загрузки статистики</div>`;
        yandexEl.innerHTML = `<div class="alert alert-danger small">Ошибка загрузки статистики</div>`;
    }
}

let _backupStatusTimer = null;
function setBackupStatus(text, isError) {
    const el = document.getElementById('backup-status');
    if (!el) return;
    if (_backupStatusTimer) {
        clearTimeout(_backupStatusTimer);
        _backupStatusTimer = null;
    }
    el.textContent = text;
    el.className = 'backup-status mt-3 ' + (isError ? 'error' : 'success');
    if (!isError) {
        _backupStatusTimer = setTimeout(() => { el.textContent = ''; el.className = 'backup-status mt-3'; }, 8000);
    }
}

function setBackupProgress(visible, percent = 0, text = '') {
    const container = document.getElementById('backup-progress');
    const bar = document.getElementById('backup-progress-bar');
    const label = document.getElementById('backup-progress-text');
    const percentEl = document.getElementById('backup-progress-percent');
    if (!container) return;
    container.style.display = visible ? 'block' : 'none';
    if (!visible) return;
    const p = Math.max(0, Math.min(100, Math.round(percent)));
    bar.style.width = p + '%';
    bar.setAttribute('aria-valuenow', p);
    if (label) label.textContent = text;
    if (percentEl) percentEl.textContent = p + '%';
}

function setAlexandriteBackupProgress(visible, percent = 0, text = '') {
    const container = document.getElementById('alexandrite-backup-progress');
    const bar = document.getElementById('alexandrite-backup-progress-bar');
    const label = document.getElementById('alexandrite-backup-progress-text');
    const percentEl = document.getElementById('alexandrite-backup-progress-percent');
    if (!container) return;
    container.style.display = visible ? 'block' : 'none';
    if (!visible) return;
    const p = Math.max(0, Math.min(100, Math.round(percent)));
    bar.style.width = p + '%';
    bar.setAttribute('aria-valuenow', p);
    if (label) label.textContent = text;
    if (percentEl) percentEl.textContent = p + '%';
}

function computeBackupPercent(data) {
    // Процент по количеству файлов, а не по объёму — визуально понятнее
    if (data.total && data.total > 0) {
        return Math.round((data.processed / data.total) * 100);
    }
    if (data.total_size && data.total_size > 0) {
        return Math.round((data.processed_size / data.total_size) * 100);
    }
    return 0;
}

function formatBackupProgressText(data, label) {
    const parts = [label];
    if (data.processed !== undefined && data.total) {
        parts.push(`${data.processed} из ${data.total}`);
    }
    if (data.current_file) {
        parts.push(data.current_file);
    }
    return parts.join(' · ');
}

function pollBackupJobStatus(jobId, kind) {
    const isArchive = kind === 'archive';
    const setProgress = isArchive ? setBackupProgress : setBackupProgress;
    const labelBase = isArchive ? 'Создание архива' : 'Синхронизация';
    const poll = async () => {
        try {
            const data = await api(`${API_BASE}/backup/job/${jobId}`);
            if (data.status === 'starting' || data.status === 'packing') {
                setBackupProgress(true, 0, data.status === 'packing' ? 'Упаковка файлов...' : 'Подготовка...');
                setBackupStatus(`${labelBase}: подготовка...`, false);
                setTimeout(poll, 1000);
            } else if (data.status === 'running' || data.status === 'uploading') {
                const percent = computeBackupPercent(data);
                const current = formatBackupProgressText(data, labelBase);
                setBackupProgress(true, percent, current);
                setBackupStatus(`${labelBase}: ${percent}%`, false);
                setTimeout(poll, 2000);
            } else if (data.status === 'completed') {
                setBackupProgress(false);
                if (isArchive) {
                    setBackupStatus(`Архив ${data.archive} создан и загружен на Яндекс.Диск.`, false);
                    loadBackupArchives();
                } else {
                    const s = data.stats || {};
                    setBackupStatus(
                        `Сохранено на Яндекс.Диск. БД: ${s.db_uploaded ? 'да' : 'нет'}, файлов загружено: ${s.files_uploaded}, пропущено: ${s.files_skipped}.`,
                        false
                    );
                }
                document.getElementById('sync-export-btn').disabled = false;
                document.getElementById('backup-create-btn').disabled = false;
            } else if (data.status === 'error') {
                setBackupProgress(false);
                setBackupStatus(`${labelBase}: ошибка — ${data.error || ''}`, true);
                document.getElementById('sync-export-btn').disabled = false;
                document.getElementById('backup-create-btn').disabled = false;
            }
        } catch (e) {
            setBackupProgress(false);
            setBackupStatus(`Ошибка ${labelBase.toLowerCase()}: ` + e.message, true);
            document.getElementById('sync-export-btn').disabled = false;
            document.getElementById('backup-create-btn').disabled = false;
        }
    };
    poll();
}

async function syncExport() {
    const btn = document.getElementById('sync-export-btn');
    btn.disabled = true;
    setBackupStatus('Запуск сохранения на Яндекс.Диск...', false);
    try {
        const res = await api(`${API_BASE}/backup/sync-export`, { method: 'POST' });
        pollBackupJobStatus(res.job_id, 'export');
    } catch (e) {
        setBackupStatus('Ошибка запуска синхронизации: ' + e.message, true);
        btn.disabled = false;
    }
}

async function syncImport() {
    if (!confirm('Загрузить данные с Яндекс.Диска?\nТекущие локальные данные будут заменены!')) return;
    const btn = document.getElementById('sync-import-btn');
    btn.disabled = true;
    setBackupStatus('Загрузка базы данных и файлов с Яндекс.Диска...', false);
    try {
        const res = await api(`${API_BASE}/backup/sync-import`, { method: 'POST' });
        const s = res.stats;
        setBackupStatus(
            `Загружено с Яндекс.Диска. Проектов: ${s.projects_restored}, групп: ${s.documents_restored}, элементов: ${s.document_items_restored}, ` +
            `файлов скачано: ${s.files_downloaded}, пропущено: ${s.files_skipped}.`,
            false
        );
        loadBackupStats();
        loadBackupArchives();
    } catch (e) {
        setBackupStatus('Ошибка загрузки: ' + e.message, true);
    } finally {
        btn.disabled = false;
    }
}

async function loadBackupArchives() {
    const tbody = document.querySelector('#backup-archives-table tbody');
    if (!tbody) return;
    try {
        const data = await api(`${API_BASE}/backup/archives`);
        const archives = data.archives || [];
        if (archives.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-muted small">Архивы не найдены</td></tr>`;
            return;
        }
        tbody.innerHTML = archives.map(a => `
            <tr>
                <td>${escapeHtml(a.name)}</td>
                <td>${formatSize(a.size)}</td>
                <td>${escapeHtml(a.modified || '-')}</td>
                <td class="text-end">
                    <button class="scheduler-btn scheduler-btn-green btn-sm" onclick="restoreArchive('${escapeHtml(a.name)}')">
                        <i class="bi bi-cloud-download"></i><span class="btn-text ms-1">Восстановить</span>
                    </button>
                    <button class="scheduler-btn scheduler-btn-red btn-sm ms-1" onclick="deleteArchive('${escapeHtml(a.name)}')">
                        <i class="bi bi-trash"></i><span class="btn-text ms-1">Удалить</span>
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        const msg = e.message && e.message.includes('не настроен')
            ? 'Яндекс.Диск не настроен'
            : 'Ошибка загрузки архивов';
        tbody.innerHTML = `<tr><td colspan="4" class="text-danger small">${escapeHtml(msg)}</td></tr>`;
    }
}

async function createArchive() {
    const btn = document.getElementById('backup-create-btn');
    btn.disabled = true;
    document.getElementById('sync-export-btn').disabled = true;
    setBackupStatus('Создание архива и загрузка на Яндекс.Диск...', false);
    try {
        const res = await api(`${API_BASE}/backup/create`, { method: 'POST' });
        pollBackupJobStatus(res.job_id, 'archive');
    } catch (e) {
        setBackupStatus('Ошибка создания архива: ' + e.message, true);
        btn.disabled = false;
        document.getElementById('sync-export-btn').disabled = false;
    }
}

async function restoreArchive(name) {
    if (!confirm(`Восстановить данные из архива ${name}?\nТекущие локальные данные будут заменены!`)) return;
    setBackupStatus('Восстановление из архива...', false);
    try {
        const res = await api(`${API_BASE}/backup/restore`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name}),
        });
        setBackupStatus(
            `Восстановлено из архива. Проектов: ${res.stats.projects_restored}, групп: ${res.stats.documents_restored}, элементов: ${res.stats.document_items_restored}.`,
            false
        );
        loadBackupStats();
        loadBackupArchives();
    } catch (e) {
        setBackupStatus('Ошибка восстановления: ' + e.message, true);
    }
}

async function deleteArchive(name) {
    if (!confirm(`Удалить архив ${name} с Яндекс.Диска?`)) return;
    try {
        await api(`${API_BASE}/backup/delete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name}),
        });
        setBackupStatus(`Архив ${name} удалён.`, false);
        loadBackupArchives();
    } catch (e) {
        setBackupStatus('Ошибка удаления: ' + e.message, true);
    }
}

// ═══════════════════════════════════════════════════
// БЭКАП / СИНХРОНИЗАЦИЯ ALEXANDRITE
// ═══════════════════════════════════════════════════

async function loadAlexandriteBackupStats() {
    const localEl = document.getElementById('alexandrite-backup-local-stats');
    if (!localEl) return;
    try {
        const data = await api(`${API_BASE}/backup/alexandrite/stats`);
        const ls = data.local;
        localEl.innerHTML = `
            <div class="backup-stat-row"><span>Папка</span><span class="backup-stat-value small text-truncate" style="max-width:60%" title="${escapeHtml(ls.path)}">${escapeHtml(ls.path)}</span></div>
            <div class="backup-stat-row"><span>Файлов</span><span class="badge bg-purple">${ls.files}</span></div>
            <div class="backup-stat-row"><span>Папок</span><span class="badge bg-brown">${ls.directories}</span></div>
            <div class="backup-stat-row"><span>Общий размер</span><span class="backup-stat-value backup-size-value">${formatSize(ls.total_size)}</span></div>
        `;
    } catch (e) {
        localEl.innerHTML = `<div class="alert alert-danger small">Ошибка загрузки статистики Alexandrite</div>`;
    }
}

function pollAlexandriteExportStatus(jobId) {
    const btn = document.getElementById('alexandrite-sync-export-btn');
    const poll = async () => {
        try {
            const data = await api(`${API_BASE}/backup/alexandrite/export-status/${jobId}`);
            if (data.status === 'starting') {
                setBackupStatus('Подготовка к загрузке папки Alexandrite...', false);
                setAlexandriteBackupProgress(true, 0, 'Подготовка...');
                setTimeout(poll, 1000);
            } else if (data.status === 'running') {
                const percent = computeBackupPercent(data);
                const current = formatBackupProgressText(data, 'Загрузка Alexandrite');
                setBackupStatus(`Загрузка Alexandrite: ${percent}%`, false);
                setAlexandriteBackupProgress(true, percent, current);
                setTimeout(poll, 2000);
            } else if (data.status === 'completed') {
                const failedText = data.failed ? `, не удалось: ${data.failed}` : '';
                setBackupStatus(`Готово. Загружено: ${data.uploaded}${failedText}.`, false);
                setAlexandriteBackupProgress(false);
                loadAlexandriteBackupStats();
                if (btn) btn.disabled = false;
            } else if (data.status === 'error') {
                setBackupStatus('Ошибка загрузки Alexandrite: ' + (data.error || ''), true);
                setAlexandriteBackupProgress(false);
                if (btn) btn.disabled = false;
            }
        } catch (e) {
            setBackupStatus('Ошибка получения статуса загрузки Alexandrite: ' + e.message, true);
            setAlexandriteBackupProgress(false);
            if (btn) btn.disabled = false;
        }
    };
    poll();
}

async function syncAlexandriteExport() {
    const btn = document.getElementById('alexandrite-sync-export-btn');
    btn.disabled = true;
    setBackupStatus('Запуск загрузки папки Alexandrite на Яндекс.Диск...', false);
    setAlexandriteBackupProgress(true, 0, 'Запуск...');
    try {
        const res = await api(`${API_BASE}/backup/alexandrite/export-async`, { method: 'POST' });
        pollAlexandriteExportStatus(res.job_id);
    } catch (e) {
        setBackupStatus('Ошибка запуска синхронизации Alexandrite: ' + e.message, true);
        setAlexandriteBackupProgress(false);
        btn.disabled = false;
    }
}

async function syncAlexandriteImport() {
    if (!confirm('Загрузить папку Alexandrite с Яндекс.Диска?\nТекущие локальные файлы Alexandrite будут заменены!')) return;
    const btn = document.getElementById('alexandrite-sync-import-btn');
    btn.disabled = true;
    setBackupStatus('Загрузка папки Alexandrite с Яндекс.Диска...', false);
    try {
        const res = await api(`${API_BASE}/backup/alexandrite/import`, { method: 'POST' });
        const s = res.stats;
        setBackupStatus(
            `Папка Alexandrite загружена с Яндекс.Диска. Файлов скачано: ${s.files_downloaded}, пропущено: ${s.files_skipped}.`,
            false
        );
        loadAlexandriteBackupStats();
        loadAlexandriteArchives();
    } catch (e) {
        setBackupStatus('Ошибка загрузки Alexandrite: ' + e.message, true);
    } finally {
        btn.disabled = false;
    }
}

async function createAlexandriteArchive() {
    const btn = document.getElementById('alexandrite-archive-btn');
    btn.disabled = true;
    setBackupStatus('Создание архива Alexandrite и загрузка на Яндекс.Диск...', false);
    try {
        const res = await api(`${API_BASE}/backup/alexandrite/archive`, { method: 'POST' });
        setBackupStatus(`Архив ${res.archive} создан и загружен на Яндекс.Диск.`, false);
        loadAlexandriteArchives();
    } catch (e) {
        setBackupStatus('Ошибка создания архива Alexandrite: ' + e.message, true);
    } finally {
        btn.disabled = false;
    }
}

async function loadAlexandriteArchives() {
    const tbody = document.querySelector('#alexandrite-archives-table tbody');
    if (!tbody) return;
    try {
        const data = await api(`${API_BASE}/backup/alexandrite/archives`);
        const archives = data.archives || [];
        if (archives.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-muted small">Архивы Alexandrite не найдены</td></tr>`;
            return;
        }
        tbody.innerHTML = archives.map(a => `
            <tr>
                <td>${escapeHtml(a.name)}</td>
                <td>${formatSize(a.size)}</td>
                <td>${escapeHtml(a.modified || '-')}</td>
                <td class="text-end">
                    <button class="scheduler-btn scheduler-btn-green btn-sm" onclick="restoreAlexandriteArchive('${escapeHtml(a.name)}')">
                        <i class="bi bi-cloud-download"></i><span class="btn-text ms-1">Восстановить</span>
                    </button>
                    <button class="scheduler-btn scheduler-btn-red btn-sm ms-1" onclick="deleteAlexandriteArchive('${escapeHtml(a.name)}')">
                        <i class="bi bi-trash"></i><span class="btn-text ms-1">Удалить</span>
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        const msg = e.message && e.message.includes('не настроен')
            ? 'Яндекс.Диск не настроен'
            : 'Ошибка загрузки архивов Alexandrite';
        tbody.innerHTML = `<tr><td colspan="4" class="text-danger small">${escapeHtml(msg)}</td></tr>`;
    }
}

async function restoreAlexandriteArchive(name) {
    if (!confirm(`Восстановить папку Alexandrite из архива ${name}?\nТекущие локальные файлы Alexandrite будут заменены!`)) return;
    setBackupStatus('Восстановление папки Alexandrite из архива...', false);
    try {
        const res = await api(`${API_BASE}/backup/alexandrite/restore`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name}),
        });
        setBackupStatus(
            `Папка Alexandrite восстановлена из архива. Файлов: ${res.stats.files}, папок: ${res.stats.directories}.`,
            false
        );
        loadAlexandriteBackupStats();
        loadAlexandriteArchives();
    } catch (e) {
        setBackupStatus('Ошибка восстановления Alexandrite: ' + e.message, true);
    }
}

async function deleteAlexandriteArchive(name) {
    if (!confirm(`Удалить архив Alexandrite ${name} с Яндекс.Диска?`)) return;
    try {
        await api(`${API_BASE}/backup/alexandrite/delete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name}),
        });
        setBackupStatus(`Архив Alexandrite ${name} удалён.`, false);
        loadAlexandriteArchives();
    } catch (e) {
        setBackupStatus('Ошибка удаления архива Alexandrite: ' + e.message, true);
    }
}

// ═══════════════════════════════════════════════════
// УТИЛИТЫ
// ═══════════════════════════════════════════════════

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.slice(0, len) + '…' : str;
}
