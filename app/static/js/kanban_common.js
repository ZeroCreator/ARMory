// ═══════════════════════════════════════════════════
// ОБЩАЯ ЛОГИКА DRAG-AND-DROP KANBANА
// ═══════════════════════════════════════════════════

function setKanbanFilterSidebarOpen(isOpen) {
    const sidebar = document.getElementById('kanban-filter-sidebar');
    const openButton = document.getElementById('kanban-filter-open');
    const backdrop = document.getElementById('kanban-filter-backdrop');
    if (!sidebar) return;

    const appLayout = sidebar.closest('.kanban-app-layout');
    const desktopLayout = window.matchMedia('(min-width: 1920px)').matches;
    const wasVisible = sidebar.classList.contains('is-open') ||
        (desktopLayout && !appLayout?.classList.contains('kanban-filters-hidden'));
    sidebar.classList.toggle('is-open', isOpen);
    appLayout?.classList.toggle('kanban-filters-hidden', !isOpen);
    if (backdrop) backdrop.hidden = !isOpen;
    if (openButton) openButton.hidden = isOpen && !desktopLayout;
    document.querySelectorAll('.kanban-filter-toggle-button').forEach(button => {
        button.setAttribute('aria-expanded', String(isOpen));
    });

    if (isOpen) {
        sidebar.querySelector('.kanban-filter-close')?.focus({ preventScroll: true });
    } else if (wasVisible && openButton?.getClientRects().length) {
        openButton?.focus({ preventScroll: true });
    }
}

function toggleKanbanFilterSidebar() {
    const sidebar = document.getElementById('kanban-filter-sidebar');
    if (!sidebar) return;
    const desktopLayout = window.matchMedia('(min-width: 1920px)').matches;
    const appLayout = sidebar.closest('.kanban-app-layout');
    const isOpen = desktopLayout
        ? !appLayout?.classList.contains('kanban-filters-hidden')
        : sidebar.classList.contains('is-open');
    setKanbanFilterSidebarOpen(!isOpen);
}

function kanbanTaskMatchesTextSearch(task, extraValues = []) {
    const query = document.getElementById('filter-text-search')?.value.trim().toLocaleLowerCase('ru-RU') || '';
    if (!query) return true;

    const searchableValues = [];
    const collectValues = (value) => {
        if (value === null || value === undefined) return;
        if (Array.isArray(value)) {
            value.forEach(collectValues);
        } else if (typeof value === 'object') {
            Object.values(value).forEach(collectValues);
        } else {
            searchableValues.push(String(value));
        }
    };

    collectValues(task);
    collectValues(extraValues);
    return searchableValues.join(' ').toLocaleLowerCase('ru-RU').includes(query);
}

function applyKanbanTextSearch() {
    if (typeof kanbanData === 'undefined' || typeof renderBoard !== 'function') return;
    renderBoard(kanbanData);
    if (typeof initKanbanSortable === 'function') initKanbanSortable();
}

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && document.getElementById('kanban-filter-sidebar')?.classList.contains('is-open')) {
        setKanbanFilterSidebarOpen(false);
    }
});

if (window.matchMedia('(min-width: 1920px)').matches) {
    document.querySelectorAll('.kanban-filter-toggle-button').forEach(button => {
        button.setAttribute('aria-expanded', 'true');
    });
}

window.addEventListener('resize', () => {
    const sidebar = document.getElementById('kanban-filter-sidebar');
    const openButton = document.getElementById('kanban-filter-open');
    if (!sidebar || !openButton) return;

    const desktopLayout = window.matchMedia('(min-width: 1920px)').matches;
    const appLayout = sidebar.closest('.kanban-app-layout');
    if (desktopLayout) {
        sidebar.classList.remove('is-open');
        document.getElementById('kanban-filter-backdrop').hidden = true;
        openButton.hidden = false;
        document.querySelectorAll('.kanban-filter-toggle-button').forEach(button => {
            button.setAttribute('aria-expanded', String(!appLayout?.classList.contains('kanban-filters-hidden')));
        });
    } else {
        const isOpen = sidebar.classList.contains('is-open');
        openButton.hidden = isOpen;
        document.querySelectorAll('.kanban-filter-toggle-button').forEach(button => {
            button.setAttribute('aria-expanded', String(isOpen));
        });
    }
});

function isKanbanTouchDevice() {
    return window.matchMedia('(pointer: coarse)').matches ||
        ('ontouchstart' in window) ||
        (navigator.maxTouchPoints > 0);
}

class KanbanDragController {
    constructor(options) {
        this.options = Object.assign({
            boardSelector: '#kanban-board',
            group: 'kanban-tasks',
            draggable: '.kanban-card',
            animation: 0,
            delay: 0,
            scroll: false,
            swapThreshold: 0.65,
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
        }, options);

        this.sortables = [];
        this.dragging = false;
    }

    get board() {
        return document.querySelector(this.options.boardSelector);
    }

    init() {
        this.sortables.forEach(s => s.destroy());
        this.sortables = [];

        if (isKanbanTouchDevice()) {
            this.dragging = false;
            return;
        }

        const bodies = this.board
            ? this.board.querySelectorAll('.kanban-column-body')
            : document.querySelectorAll('.kanban-column-body');

        bodies.forEach(body => {
            const sortable = Sortable.create(body, {
                group: this.options.group,
                animation: this.options.animation,
                delay: this.options.delay,
                scroll: this.options.scroll,
                swapThreshold: this.options.swapThreshold,
                draggable: this.options.draggable,
                ghostClass: this.options.ghostClass,
                dragClass: this.options.dragClass,
                onStart: () => this._onDragStart(),
                onEnd: (evt) => this._onDragEnd(evt),
            });
            this.sortables.push(sortable);
        });
    }

    handleCardClick(taskId, callback) {
        if (this.dragging) {
            this.dragging = false;
            return;
        }
        callback(taskId);
    }

    _onDragStart() {
        this.dragging = true;
        if (this.board) {
            this.board.classList.add('kanban-dragging');
        }
    }

    _onDragEnd(evt) {
        if (this.board) {
            this.board.classList.remove('kanban-dragging');
        }
        setTimeout(() => { this.dragging = false; }, 150);

        const taskId = parseInt(evt.item.dataset.id, 10);
        const fromColumn = this.options.getColumnId(evt.from);
        const toColumn = this.options.getColumnId(evt.to);
        const targetBody = evt.to;

        if (this.options.onUpdateCounts) {
            this.options.onUpdateCounts();
        }

        if (this.options.isSameColumn ? this.options.isSameColumn(fromColumn, toColumn) : fromColumn === toColumn) {
            const taskIds = Array.from(evt.to.querySelectorAll('.kanban-card'))
                .map(card => parseInt(card.dataset.id, 10));
            if (this.options.onSameColumnReorder) {
                this.options.onSameColumnReorder(taskIds, toColumn, targetBody);
            }
            return;
        }

        if (this.options.onCrossColumnMove) {
            this.options.onCrossColumnMove(taskId, toColumn, targetBody);
        }
    }
}
