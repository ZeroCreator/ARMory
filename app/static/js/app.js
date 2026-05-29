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

// ═══════════════════════════════════════════════════
// Category helpers
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
// PROJECTS
// ═══════════════════════════════════════════════════

async function loadProjects() {
    const container = document.getElementById('projects-list');
    try {
        const projects = await api(`${API_BASE}/projects`);
        if (!projects.length) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="bi bi-folder"></i>
                    <p>Проектов пока нет. Создайте первый проект!</p>
                </div>`;
            return;
        }
        container.innerHTML = projects.map((p, idx) => `
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
        initProjectSortable();
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Ошибка загрузки: ${e.message}</div>`;
    }
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
// PROJECT DETAIL
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
// SECTIONS
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
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Ошибка загрузки: ${e.message}</div>`;
    }
}

function renderSection(section, idx) {
    const collapsed = isSectionCollapsed(PROJECT_ID, section.id);
    const docsHtml = (section.documents || []).map((d, iidx) => renderGroup(d, iidx)).join('');
    const descHtml = section.description ? `<div class="section-desc small">${escapeHtml(section.description)}</div>` : '';
    return `
        <div class="section-card mb-4 fade-in" data-id="${section.id}">
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
        <div class="doc-group mb-3 fade-in" data-id="${doc.id}">
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
        : `<button class="btn btn-sm btn-outline-primary" onclick='event.stopPropagation(); openItemPreview(${JSON.stringify({...item, category: cat, document_id: doc.id}).replace(/'/g, "&#39;")})'><i class="bi bi-eye"></i></button>`;
    const downloadBtn = (isLink || isNote)
        ? ''
        : `<a href="${API_BASE}/projects/${PROJECT_ID}/documents/${doc.id}/items/${item.id}/download" class="btn btn-sm btn-outline-success"><i class="bi bi-download"></i></a>`;

    return `
        <div class="doc-item d-flex align-items-center gap-2 py-2 ${idx > 0 ? 'border-top' : ''}">
            <div class="doc-item-icon ${cat}"><i class="bi ${iconClass}"></i></div>
            <div class="doc-item-info flex-fill">
                <div class="doc-item-title d-flex align-items-center gap-2">
                    ${titleHtml}
                    <span class="doc-category ${cat}">${escapeHtml(label)}</span>
                </div>
                <div class="doc-item-meta">${subtitle}</div>
            </div>
            <div class="doc-item-actions d-flex gap-1">
                <button class="btn btn-sm btn-outline-secondary" onclick='event.stopPropagation(); showEditItemModal(${doc.id}, ${JSON.stringify(item).replace(/'/g, "&#39;")})'><i class="bi bi-pencil"></i></button>
                ${previewBtn}
                ${downloadBtn}
                <button class="btn btn-sm btn-outline-danger" onclick="event.stopPropagation(); deleteItem(${doc.id}, ${item.id})"><i class="bi bi-trash"></i></button>
            </div>
        </div>`;
}

// ═══════════════════════════════════════════════════
// SECTION CRUD
// ═══════════════════════════════════════════════════

async function createSection() {
    const form = document.getElementById('section-form');
    const data = Object.fromEntries(new FormData(form));
    if (!data.name.trim()) return alert('Введите название раздела');
    const params = new URLSearchParams({name: data.name});
    if (data.description) params.append('description', data.description);
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/sections`, {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: params
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
    const params = new URLSearchParams({name});
    if (description) params.append('description', description);
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/sections/${sectionId}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: params
        });
        bootstrap.Modal.getInstance(document.getElementById('editSectionModal')).hide();
        loadSections(PROJECT_ID);
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function deleteSection(sectionId) {
    if (!confirm('Удалить раздел? Группы из этого раздела перейдут в "Без раздела".')) return;
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
// GROUP CRUD
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
    const data = Object.fromEntries(new FormData(form));
    if (!data.title.trim()) return alert('Введите название группы');
    const params = new URLSearchParams({title: data.title});
    if (data.description) params.append('description', data.description);
    if (data.section_id) params.append('section_id', data.section_id);
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/documents`, {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: params
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
    const params = new URLSearchParams({title});
    if (description) params.append('description', description);
    params.append('section_id', sectionId);
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/documents/${docId}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: params
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
// ITEM CRUD
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
    f.doc_id.value = docId;
    f.item_id.value = item.id;
    f.title.value = item.title || '';
    const urlWrap = document.getElementById('edit-item-url-wrap');
    const contentWrap = document.getElementById('edit-item-content-wrap');
    if (item.item_type === 'link') {
        urlWrap.classList.remove('d-none');
        contentWrap.classList.add('d-none');
        f.url.value = item.url || '';
        f.content.value = '';
    } else if (item.item_type === 'note') {
        urlWrap.classList.add('d-none');
        contentWrap.classList.remove('d-none');
        f.url.value = '';
        f.content.value = item.content || '';
    } else {
        urlWrap.classList.add('d-none');
        contentWrap.classList.add('d-none');
        f.url.value = '';
        f.content.value = '';
    }
    new bootstrap.Modal(document.getElementById('editItemModal')).show();
}

async function updateItem() {
    const f = document.getElementById('edit-item-form');
    const docId = f.doc_id.value;
    const itemId = f.item_id.value;
    const data = new URLSearchParams();
    data.append('title', f.title.value);
    if (!f.url.parentElement.classList.contains('d-none')) {
        data.append('url', f.url.value);
    }
    if (!f.content.parentElement.classList.contains('d-none')) {
        data.append('content', f.content.value);
    }
    try {
        await api(`${API_BASE}/projects/${PROJECT_ID}/documents/${docId}/items/${itemId}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: data
        });
        bootstrap.Modal.getInstance(document.getElementById('editItemModal')).hide();
        loadSections(PROJECT_ID);
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

// ═══════════════════════════════════════════════════
// PREVIEW
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

async function openItemPreview(item) {
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

    const cat = item.category || detectCategoryFromItem(item);

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
            if (item.item_type === 'file' && ['word', 'spreadsheet', 'presentation', 'archive'].includes(cat)) {
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

function previewError() {
    const content = document.getElementById('preview-content');
    content.innerHTML = `
        <div class="empty-state py-5">
            <i class="bi bi-exclamation-triangle"></i>
            <p>Не удалось загрузить предпросмотр</p>
        </div>`;
}

// ═══════════════════════════════════════════════════
// SIDEBARS
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

function renderSidebarBlocks(position, blocks) {
    const container = document.getElementById(`sidebar-${position}-blocks`);
    if (!container) return;
    if (!blocks || !blocks.length) {
        container.innerHTML = `<div class="text-muted small text-center py-3">Нет блоков</div>`;
        return;
    }
    container.innerHTML = blocks.map(block => {
        const blockNote = block.note ? `<span class="sidebar-note-badge" onclick="event.stopPropagation(); openSidebarNoteModal('block', ${block.id})" title="${escapeHtml(block.note)}"><i class="bi bi-sticky"></i></span>` : '';
        return `
        <div class="sidebar-block fade-in" data-id="${block.id}" data-type="block" oncontextmenu="handleSidebarContextMenu(event, 'block', ${block.id}, '${escapeHtml(block.title).replace(/'/g, "\\'")}')">
            <div class="sidebar-block-header">
                <div class="sidebar-block-title-wrap">
                    <h4 class="sidebar-block-title">${escapeHtml(block.title)}</h4>
                </div>
                ${blockNote}
                <div class="sidebar-drag-handle" title="Переместить блок" onclick="event.stopPropagation()"><i class="bi bi-grip-vertical"></i></div>
            </div>
            <ul class="sidebar-link-list" data-block-id="${block.id}">
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
// SIDEBAR SORTABLE
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
// SIDEBAR CONTEXT MENU
// ═══════════════════════════════════════════════════

let sidebarContextTarget = null;

function handleSidebarContextMenu(event, type, id, title) {
    event.preventDefault();
    event.stopPropagation();
    sidebarContextTarget = { type, id, title };
    const menu = document.getElementById('sidebar-context-menu');
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
});
document.addEventListener('scroll', hideSidebarContextMenu, true);
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideSidebarContextMenu();
});

document.getElementById('sidebar-context-menu').addEventListener('click', (e) => {
    const item = e.target.closest('.sidebar-context-item');
    if (!item || !sidebarContextTarget) return;
    const action = item.dataset.action;
    const { type, id } = sidebarContextTarget;
    hideSidebarContextMenu();
    if (action === 'add-link') {
        if (type === 'block') showAddLinkModal(id);
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

// ── Edit Block ──

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

// ── Edit Link ──

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

// ── Note ──

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
// SCHEDULER (from bd-arm)
// ═══════════════════════════════════════════════════

async function fillSchedulerProjects() {
    const select = document.getElementById('project-select');
    if (!select) return;
    // Фиксированные проекты как в bd-arm
    select.innerHTML =
        '<option value="" disabled selected>-- Выберите проект --</option>' +
        '<option value="Dogma">Dogma</option>' +
        '<option value="TrendAgent">TrendAgent</option>';
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
            await api(`${API_BASE}/scheduler/schedule`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({project, datetime})
            });
            showStatus('Задача успешно добавлена!', false);
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
// UTILS
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
