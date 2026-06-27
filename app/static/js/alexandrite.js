// ═══════════════════════════════════════════════════
// alexandrite — файловое хранилище заметок
// ═══════════════════════════════════════════════════

let alexandriteRoot = '';
let alexandriteHoverTimeout = null;
let alexandriteBrowseCurrent = '';
let alexandriteCurrentFile = null;   // относительный путь текущего файла
let alexandriteCurrentContent = '';  // текущее содержимое файла
let alexandriteEditMode = false;     // true — редактирование, false — просмотр
let alexandriteCreateFileFolder = ''; // папка, в которой создаётся файл через контекстное меню
let alexandriteCreateFolderParent = ''; // родительская папка для создания подпапки
let alexandriteContextFolder = null;  // целевая папка контекстного меню
let alexandriteContextFile = null;    // целевой файл контекстного меню
let alexandriteOpenOnLoad = null;     // путь файла для автоматического открытия из query string

async function loadAlexandriteRoots() {
    try {
        const roots = await api(`${API_BASE}/alexandrite/roots`);
        if (roots.length && roots[0].exists && !alexandriteRoot) {
            await setAlexandriteRoot(roots[0].path);
        }
    } catch (e) {
        console.error('Failed to load roots:', e);
    }
}

async function setAlexandriteRoot(forcedRoot) {
    const root = forcedRoot;
    if (!root) return;

    alexandriteRoot = root;
    localStorage.setItem('alexandrite_root', root);
    document.getElementById('alexandrite-current-root').textContent = root;

    const modalEl = document.getElementById('alexandriteRootModal');
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();

    await loadAlexandriteTree();
}

async function loadAlexandriteTree() {
    const container = document.getElementById('alexandrite-tree');
    if (!alexandriteRoot) {
        container.innerHTML = `<div class="text-muted small text-center py-3">Выберите папку</div>`;
        return;
    }
    container.innerHTML = `<div class="text-muted small text-center py-3">Загрузка...</div>`;
    try {
        const data = await api(`${API_BASE}/alexandrite/tree?root=${encodeURIComponent(alexandriteRoot)}`);
        alexandriteRoot = data.root; // нормализованный путь
        document.getElementById('alexandrite-current-root').textContent = data.root;
        renderAlexandriteTree(data.tree, container);
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger m-2">Ошибка загрузки: ${e.message}</div>`;
    }
}

function renderAlexandriteTree(items, container, level = 0) {
    if (!items || items.length === 0) {
        if (level === 0) {
            container.innerHTML = `<div class="text-muted small text-center py-3">Папка пуста</div>`;
        }
        return;
    }

    const ul = document.createElement('ul');
    ul.className = level === 0 ? 'alexandrite-tree-list' : 'alexandrite-tree-children';

    items.forEach(item => {
        const li = document.createElement('li');
        li.className = 'alexandrite-tree-item';
        li.dataset.path = item.path;
        li.dataset.type = item.type;

        const isDir = item.type === 'directory';
        const hasChildren = isDir && item.children && item.children.length > 0;
        const icon = isDir
            ? (hasChildren ? 'bi-folder-fill' : 'bi-folder')
            : getFileIcon(item.name);

        li.innerHTML = `
            <div class="alexandrite-tree-row" style="padding-left: ${level * 16}px">
                ${isDir ? `<i class="bi bi-chevron-right alexandrite-tree-toggle ${hasChildren ? '' : 'invisible'}"></i>` : '<span class="alexandrite-tree-spacer"></span>'}
                <i class="bi ${icon} alexandrite-tree-icon"></i>
                <span class="alexandrite-tree-title">${escapeHtml(item.name)}</span>
            </div>
        `;

        const row = li.querySelector('.alexandrite-tree-row');

        if (isDir) {
            row.addEventListener('click', (e) => {
                if (e.target.closest('.alexandrite-tree-toggle')) {
                    e.stopPropagation();
                }
                li.classList.toggle('expanded');
            });
            row.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                showAlexandriteFolderContextMenu(e, item.path);
            });
            if (hasChildren) {
                const childrenContainer = document.createElement('div');
                childrenContainer.className = 'alexandrite-tree-children-wrap';
                renderAlexandriteTree(item.children, childrenContainer, level + 1);
                li.appendChild(childrenContainer);
            }
        } else {
            row.addEventListener('mouseenter', () => {
                clearTimeout(alexandriteHoverTimeout);
                alexandriteHoverTimeout = setTimeout(() => previewAlexandriteFile(item.path), 150);
            });
            row.addEventListener('mouseleave', () => {
                clearTimeout(alexandriteHoverTimeout);
            });
            row.addEventListener('click', () => previewAlexandriteFile(item.path));
            row.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                showAlexandriteFileContextMenu(e, item.path);
            });
        }

        ul.appendChild(li);
    });

    container.innerHTML = '';
    container.appendChild(ul);

    if (alexandriteOpenOnLoad && level === 0) {
        revealAndOpenAlexandriteFile(alexandriteOpenOnLoad);
    }
}

function revealAndOpenAlexandriteFile(path) {
    if (!path) return;

    // Сначала ищем точное совпадение по data-path
    let selector = `.alexandrite-tree-item[data-type="file"]`;
    let exactItem = null;
    try {
        exactItem = document.querySelector(`${selector}[data-path="${CSS.escape(path)}"]`);
    } catch (e) {
        // Fallback для старых браузеров без CSS.escape
        const escaped = path.replace(/"/g, '\\"');
        exactItem = document.querySelector(`${selector}[data-path="${escaped}"]`);
    }

    if (exactItem) {
        revealAlexandriteTreeItem(exactItem);
        previewAlexandriteFile(path);
        alexandriteOpenOnLoad = null;
        return;
    }

    // Если точного совпадения нет — ищем по имени файла
    const basename = path.split('/').pop();
    const items = document.querySelectorAll(selector);
    for (const item of items) {
        if (item.dataset.path && item.dataset.path.split('/').pop() === basename) {
            revealAlexandriteTreeItem(item);
            previewAlexandriteFile(item.dataset.path);
            alexandriteOpenOnLoad = null;
            return;
        }
    }

    console.warn('Alexandrite: файл не найден в дереве', path);
    alexandriteOpenOnLoad = null;
}

function revealAlexandriteTreeItem(item) {
    // Развернуть все родительские папки
    let parent = item.closest('.alexandrite-tree-children-wrap')?.closest('.alexandrite-tree-item');
    while (parent) {
        parent.classList.add('expanded');
        parent = parent.closest('.alexandrite-tree-children-wrap')?.closest('.alexandrite-tree-item');
    }

    document.querySelectorAll('.alexandrite-tree-row.active').forEach(el => el.classList.remove('active'));
    const row = item.querySelector(':scope > .alexandrite-tree-row');
    if (row) {
        row.classList.add('active');
        row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function getFileIcon(name) {
    const ext = name.split('.').pop().toLowerCase();
    const map = {
        md: 'bi-file-earmark-text',
        txt: 'bi-file-earmark-text',
        py: 'bi-file-earmark-code',
        js: 'bi-file-earmark-code',
        ts: 'bi-file-earmark-code',
        html: 'bi-file-earmark-code',
        css: 'bi-file-earmark-code',
        json: 'bi-file-earmark-code',
        yaml: 'bi-file-earmark-code',
        yml: 'bi-file-earmark-code',
        jpg: 'bi-file-earmark-image',
        jpeg: 'bi-file-earmark-image',
        png: 'bi-file-earmark-image',
        gif: 'bi-file-earmark-image',
        svg: 'bi-file-earmark-image',
        webp: 'bi-file-earmark-image',
        pdf: 'bi-file-earmark-pdf',
    };
    return map[ext] || 'bi-file-earmark';
}

async function previewAlexandriteFile(path) {
    if (!alexandriteRoot) return;
    alexandriteCurrentFile = path;
    alexandriteEditMode = false;

    const empty = document.getElementById('alexandrite-empty');
    const preview = document.getElementById('alexandrite-preview');
    const title = document.getElementById('alexandrite-preview-title');
    const meta = document.getElementById('alexandrite-preview-meta');
    const body = document.getElementById('alexandrite-preview-body');

    empty.style.display = 'none';
    preview.style.display = 'block';
    title.textContent = path.split('/').pop();
    meta.textContent = 'Загрузка...';
    body.innerHTML = '';
    updateAlexandriteModeButtons();

    try {
        const data = await api(`${API_BASE}/alexandrite/file?root=${encodeURIComponent(alexandriteRoot)}&path=${encodeURIComponent(path)}`);
        meta.textContent = data.mime_type || '';

        if (data.type === 'text') {
            alexandriteCurrentContent = data.content;
            renderAlexandritePreview();
        } else if (data.type === 'image') {
            alexandriteCurrentContent = '';
            const img = document.createElement('img');
            img.src = data.content;
            img.alt = data.name;
            img.className = 'alexandrite-image-preview';
            body.appendChild(img);
            hideAlexandriteEditControls();
        } else {
            alexandriteCurrentContent = '';
            body.innerHTML = `<div class="empty-state py-5"><i class="bi bi-file-earmark-lock"></i><p>${escapeHtml(data.message || 'Невозможно отобразить файл')}</p></div>`;
            hideAlexandriteEditControls();
        }
    } catch (e) {
        body.innerHTML = `<div class="alert alert-danger">Ошибка загрузки: ${e.message}</div>`;
    }
}

function hideAlexandriteEditControls() {
    document.getElementById('alexandrite-mode-view').style.display = 'none';
    document.getElementById('alexandrite-mode-edit').style.display = 'none';
    document.getElementById('alexandrite-save-btn').style.display = 'none';
}

function updateAlexandriteModeButtons() {
    const viewBtn = document.getElementById('alexandrite-mode-view');
    const editBtn = document.getElementById('alexandrite-mode-edit');
    const saveBtn = document.getElementById('alexandrite-save-btn');

    if (!alexandriteCurrentFile) {
        hideAlexandriteEditControls();
        return;
    }

    const ext = alexandriteCurrentFile.split('.').pop().toLowerCase();
    const editable = ext === 'md' || ext === 'txt';

    viewBtn.style.display = editable ? 'inline-block' : 'none';
    editBtn.style.display = editable ? 'inline-block' : 'none';
    saveBtn.style.display = alexandriteEditMode && editable ? 'inline-block' : 'none';

    viewBtn.classList.toggle('active', !alexandriteEditMode);
    editBtn.classList.toggle('active', alexandriteEditMode);
}

function renderAlexandritePreview() {
    const body = document.getElementById('alexandrite-preview-body');
    body.innerHTML = '';

    if (!alexandriteCurrentFile) return;
    const ext = alexandriteCurrentFile.split('.').pop().toLowerCase();

    if (alexandriteEditMode) {
        body.classList.add('editing');
        const textarea = document.createElement('textarea');
        textarea.className = 'form-control alexandrite-editor';
        textarea.id = 'alexandrite-editor';
        textarea.value = alexandriteCurrentContent;
        body.appendChild(textarea);
        textarea.focus();
    } else {
        body.classList.remove('editing');
    }

    if (ext === 'md' && !alexandriteEditMode) {
        const article = document.createElement('article');
        article.className = 'alexandrite-markdown';
        article.innerHTML = marked.parse(alexandriteCurrentContent);
        body.appendChild(article);
    } else {
        const pre = document.createElement('pre');
        pre.className = 'alexandrite-text-preview';
        const code = document.createElement('code');
        code.textContent = alexandriteCurrentContent;
        pre.appendChild(code);
        body.appendChild(pre);
    }
}

function setAlexandriteViewMode() {
    if (!alexandriteEditMode) return;
    alexandriteEditMode = false;
    updateAlexandriteModeButtons();
    renderAlexandritePreview();
}

function setAlexandriteEditMode() {
    if (alexandriteEditMode) return;
    alexandriteEditMode = true;
    updateAlexandriteModeButtons();
    renderAlexandritePreview();
}

async function saveAlexandriteFile() {
    if (!alexandriteCurrentFile || !alexandriteRoot) return;
    const textarea = document.getElementById('alexandrite-editor');
    if (!textarea) return;

    const content = textarea.value;
    try {
        await api(`${API_BASE}/alexandrite/file?root=${encodeURIComponent(alexandriteRoot)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: alexandriteCurrentFile, content }),
        });
        alexandriteCurrentContent = content;
        setAlexandriteViewMode();
        showToast('Файл сохранён');
    } catch (e) {
        showToast(`Ошибка сохранения: ${e.message}`, 'danger');
    }
}

async function deleteAlexandriteFile() {
    if (!alexandriteCurrentFile || !alexandriteRoot) return;
    if (!confirm(`Удалить файл «${alexandriteCurrentFile.split('/').pop()}»?`)) return;

    try {
        await api(`${API_BASE}/alexandrite/file?root=${encodeURIComponent(alexandriteRoot)}&path=${encodeURIComponent(alexandriteCurrentFile)}`, {
            method: 'DELETE',
        });
        alexandriteCurrentFile = null;
        alexandriteCurrentContent = '';
        document.getElementById('alexandrite-preview').style.display = 'none';
        document.getElementById('alexandrite-empty').style.display = 'flex';
        await loadAlexandriteTree();
        showToast('Файл удалён');
    } catch (e) {
        showToast(`Ошибка удаления: ${e.message}`, 'danger');
    }
}

// ═══════════════════════════════════════════════════
// Контекстное меню папки
// ═══════════════════════════════════════════════════
function showAlexandriteFolderContextMenu(event, folderPath) {
    hideAlexandriteFolderContextMenu();
    hideAlexandriteFileContextMenu();
    alexandriteContextFolder = folderPath;
    const menu = document.getElementById('alexandrite-folder-context-menu');
    menu.style.display = 'block';
    menu.style.left = `${event.clientX}px`;
    menu.style.top = `${event.clientY}px`;
}

function hideAlexandriteFolderContextMenu() {
    const menu = document.getElementById('alexandrite-folder-context-menu');
    if (menu) menu.style.display = 'none';
    alexandriteContextFolder = null;
}

function showAlexandriteFileContextMenu(event, filePath) {
    hideAlexandriteFileContextMenu();
    hideAlexandriteFolderContextMenu();
    alexandriteContextFile = filePath;
    const menu = document.getElementById('alexandrite-file-context-menu');
    menu.style.display = 'block';
    menu.style.left = `${event.clientX}px`;
    menu.style.top = `${event.clientY}px`;
}

function hideAlexandriteFileContextMenu() {
    const menu = document.getElementById('alexandrite-file-context-menu');
    if (menu) menu.style.display = 'none';
    alexandriteContextFile = null;
}

// ═══════════════════════════════════════════════════
// Создание файла
// ═══════════════════════════════════════════════════
function showCreateFileModal(folderPath = '') {
    alexandriteCreateFileFolder = folderPath;
    const modal = new bootstrap.Modal(document.getElementById('alexandriteCreateFileModal'));
    document.getElementById('alexandrite-create-file-name').value = '';
    document.getElementById('alexandrite-create-file-type').value = '.md';
    modal.show();
}

async function createAlexandriteFile() {
    if (!alexandriteRoot) {
        showToast('Сначала выберите папку', 'warning');
        return;
    }
    const nameInput = document.getElementById('alexandrite-create-file-name');
    const typeSelect = document.getElementById('alexandrite-create-file-type');
    const name = nameInput.value.trim();
    if (!name) {
        showToast('Введите имя файла', 'warning');
        return;
    }

    let filename = name.endsWith('.md') || name.endsWith('.txt') ? name : name + typeSelect.value;
    if (!filename.endsWith('.md') && !filename.endsWith('.txt')) {
        showToast('Разрешены только .md и .txt файлы', 'warning');
        return;
    }

    const fullPath = alexandriteCreateFileFolder ? `${alexandriteCreateFileFolder}/${filename}` : filename;

    try {
        await api(`${API_BASE}/alexandrite/file?root=${encodeURIComponent(alexandriteRoot)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: fullPath, content: '' }),
        });
        const modalEl = document.getElementById('alexandriteCreateFileModal');
        bootstrap.Modal.getInstance(modalEl).hide();
        alexandriteCreateFileFolder = '';
        await loadAlexandriteTree();
        await previewAlexandriteFile(fullPath);
        setAlexandriteEditMode();
        showToast('Файл создан');
    } catch (e) {
        alexandriteCreateFileFolder = '';
        showToast(`Ошибка создания: ${e.message}`, 'danger');
    }
}

// ═══════════════════════════════════════════════════
// Создание папки
// ═══════════════════════════════════════════════════
function showCreateFolderModal(parentPath = '') {
    alexandriteCreateFolderParent = parentPath;
    const modal = new bootstrap.Modal(document.getElementById('alexandriteCreateFolderModal'));
    document.getElementById('alexandrite-create-folder-name').value = '';
    modal.show();
}

async function createAlexandriteFolder() {
    if (!alexandriteRoot) {
        showToast('Сначала выберите папку', 'warning');
        return;
    }
    const nameInput = document.getElementById('alexandrite-create-folder-name');
    const name = nameInput.value.trim();
    if (!name) {
        showToast('Введите имя папки', 'warning');
        return;
    }

    const fullPath = alexandriteCreateFolderParent ? `${alexandriteCreateFolderParent}/${name}` : name;

    try {
        await api(`${API_BASE}/alexandrite/directory?root=${encodeURIComponent(alexandriteRoot)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: fullPath }),
        });
        const modalEl = document.getElementById('alexandriteCreateFolderModal');
        bootstrap.Modal.getInstance(modalEl).hide();
        alexandriteCreateFolderParent = '';
        await loadAlexandriteTree();
        showToast('Папка создана');
    } catch (e) {
        alexandriteCreateFolderParent = '';
        showToast(`Ошибка создания папки: ${e.message}`, 'danger');
    }
}

async function renameAlexandriteFolder(folderPath) {
    if (!alexandriteRoot || !folderPath) return;
    const currentName = folderPath.split('/').pop();
    const newName = prompt('Новое имя папки:', currentName);
    if (!newName || newName.trim() === currentName) return;

    try {
        await api(`${API_BASE}/alexandrite/directory?root=${encodeURIComponent(alexandriteRoot)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: folderPath, new_name: newName.trim() }),
        });
        await loadAlexandriteTree();
        showToast('Папка переименована');
    } catch (e) {
        showToast(`Ошибка переименования: ${e.message}`, 'danger');
    }
}

async function deleteAlexandriteFolder(folderPath) {
    if (!alexandriteRoot || !folderPath) return;
    const name = folderPath.split('/').pop();
    if (!confirm(`Удалить папку «${name}» и всё её содержимое?`)) return;

    try {
        await api(`${API_BASE}/alexandrite/directory?root=${encodeURIComponent(alexandriteRoot)}&path=${encodeURIComponent(folderPath)}`, {
            method: 'DELETE',
        });
        await loadAlexandriteTree();
        showToast('Папка удалена');
    } catch (e) {
        showToast(`Ошибка удаления: ${e.message}`, 'danger');
    }
}

async function renameAlexandriteFile(filePath) {
    if (!alexandriteRoot || !filePath) return;
    const currentName = filePath.split('/').pop();
    const newName = prompt('Новое имя файла:', currentName);
    if (!newName || newName.trim() === currentName) return;

    try {
        await api(`${API_BASE}/alexandrite/file?root=${encodeURIComponent(alexandriteRoot)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: filePath, new_name: newName.trim() }),
        });
        if (alexandriteCurrentFile === filePath) {
            alexandriteCurrentFile = null;
            alexandriteCurrentContent = '';
            document.getElementById('alexandrite-preview').style.display = 'none';
            document.getElementById('alexandrite-empty').style.display = 'flex';
        }
        await loadAlexandriteTree();
        showToast('Файл переименован');
    } catch (e) {
        showToast(`Ошибка переименования: ${e.message}`, 'danger');
    }
}

async function deleteAlexandriteFileFromContext(filePath) {
    if (!filePath) return;
    const name = filePath.split('/').pop();
    if (!confirm(`Удалить файл «${name}»?`)) return;

    try {
        await api(`${API_BASE}/alexandrite/file?root=${encodeURIComponent(alexandriteRoot)}&path=${encodeURIComponent(filePath)}`, {
            method: 'DELETE',
        });
        if (alexandriteCurrentFile === filePath) {
            alexandriteCurrentFile = null;
            alexandriteCurrentContent = '';
            document.getElementById('alexandrite-preview').style.display = 'none';
            document.getElementById('alexandrite-empty').style.display = 'flex';
        }
        await loadAlexandriteTree();
        showToast('Файл удалён');
    } catch (e) {
        showToast(`Ошибка удаления: ${e.message}`, 'danger');
    }
}

// ═══════════════════════════════════════════════════
// Файловый браузер для выбора корневой папки
// ═══════════════════════════════════════════════════
async function showAlexandriteRootModal() {
    const modal = new bootstrap.Modal(document.getElementById('alexandriteRootModal'));
    // Начинаем с корня файловой системы, чтобы можно было выбрать любую папку
    alexandriteBrowseCurrent = '/';
    await loadAlexandriteBrowse(alexandriteBrowseCurrent);
    modal.show();
}

async function loadAlexandriteBrowse(path) {
    const list = document.getElementById('alexandrite-browser-list');
    const currentInput = document.getElementById('alexandrite-browser-current');
    const upBtn = document.getElementById('alexandrite-browser-up');
    list.innerHTML = '<div class="text-muted small text-center py-3">Загрузка...</div>';

    try {
        const url = `${API_BASE}/alexandrite/browse${path ? '?path=' + encodeURIComponent(path) : ''}`;
        const data = await api(url);
        alexandriteBrowseCurrent = data.current;
        currentInput.value = data.current;
        upBtn.disabled = !data.parent;
        upBtn.dataset.parent = data.parent || '';

        if (!data.items.length) {
            list.innerHTML = '<div class="text-muted small text-center py-3">Нет доступных папок</div>';
            return;
        }

        const ul = document.createElement('ul');
        ul.className = 'list-group list-group-flush alexandrite-browser-items';

        data.items.forEach(item => {
            const li = document.createElement('li');
            li.className = 'list-group-item alexandrite-browser-item d-flex justify-content-between align-items-center';

            const nameSpan = document.createElement('span');
            nameSpan.className = 'alexandrite-browser-name';
            nameSpan.innerHTML = `<i class="bi bi-folder-fill me-2"></i><span>${escapeHtml(item.name)}</span>`;
            nameSpan.addEventListener('click', () => enterAlexandriteBrowseDir(item.path));

            const selectBtn = document.createElement('button');
            selectBtn.type = 'button';
            selectBtn.className = 'btn btn-sm btn-outline-primary';
            selectBtn.textContent = 'Выбрать';
            selectBtn.addEventListener('click', () => selectAlexandriteBrowseDir(item.path));

            li.appendChild(nameSpan);
            li.appendChild(selectBtn);
            ul.appendChild(li);
        });

        list.innerHTML = '';
        list.appendChild(ul);
    } catch (e) {
        list.innerHTML = `<div class="alert alert-danger m-2">Ошибка загрузки: ${escapeHtml(e.message)}</div>`;
    }
}

function enterAlexandriteBrowseDir(path) {
    loadAlexandriteBrowse(path);
}

function selectAlexandriteBrowseDir(path) {
    setAlexandriteRoot(path);
}

function selectAlexandriteBrowseCurrent() {
    setAlexandriteRoot(alexandriteBrowseCurrent);
}

function goAlexandriteBrowseUp() {
    const upBtn = document.getElementById('alexandrite-browser-up');
    const parent = upBtn.dataset.parent;
    if (parent) {
        loadAlexandriteBrowse(parent);
    }
}

// ═══════════════════════════════════════════════════
// Toast-уведомления
// ═══════════════════════════════════════════════════
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

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('alexandrite-tree')) {
        const params = new URLSearchParams(window.location.search);
        const rootParam = params.get('root');
        const openPath = params.get('open');
        if (openPath) {
            alexandriteOpenOnLoad = openPath;
        }

        if (rootParam) {
            // Внешняя ссылка на конкретную папку (например, из хранилища проекта)
            alexandriteRoot = rootParam;
            document.getElementById('alexandrite-current-root').textContent = rootParam;
            loadAlexandriteTree();
        } else {
            const saved = localStorage.getItem('alexandrite_root');
            if (saved) {
                alexandriteRoot = saved;
                document.getElementById('alexandrite-current-root').textContent = saved;
                loadAlexandriteTree();
            }
            loadAlexandriteRoots();
        }

        // Обработчики контекстного меню папки
        const folderMenu = document.getElementById('alexandrite-folder-context-menu');
        if (folderMenu) {
            folderMenu.addEventListener('click', (e) => {
                const item = e.target.closest('.sidebar-context-item');
                if (!item) return;
                const action = item.dataset.action;
                const folder = alexandriteContextFolder;
                hideAlexandriteFolderContextMenu();
                if (action === 'add-file' && folder) {
                    showCreateFileModal(folder);
                } else if (action === 'add-folder' && folder) {
                    showCreateFolderModal(folder);
                } else if (action === 'rename' && folder) {
                    renameAlexandriteFolder(folder);
                } else if (action === 'delete' && folder) {
                    deleteAlexandriteFolder(folder);
                }
            });
        }

        const fileMenu = document.getElementById('alexandrite-file-context-menu');
        if (fileMenu) {
            fileMenu.addEventListener('click', (e) => {
                const item = e.target.closest('.sidebar-context-item');
                if (!item) return;
                const action = item.dataset.action;
                const file = alexandriteContextFile;
                hideAlexandriteFileContextMenu();
                if (action === 'rename' && file) {
                    renameAlexandriteFile(file);
                } else if (action === 'delete' && file) {
                    deleteAlexandriteFileFromContext(file);
                }
            });
        }

        document.addEventListener('click', (e) => {
            if (!e.target.closest('#alexandrite-folder-context-menu')) {
                hideAlexandriteFolderContextMenu();
            }
            if (!e.target.closest('#alexandrite-file-context-menu')) {
                hideAlexandriteFileContextMenu();
            }
        });
        document.addEventListener('scroll', () => {
            hideAlexandriteFolderContextMenu();
            hideAlexandriteFileContextMenu();
        }, true);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                hideAlexandriteFolderContextMenu();
                hideAlexandriteFileContextMenu();
            }
        });
    }
});
