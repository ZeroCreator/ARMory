// ═══════════════════════════════════════════════════
// ОБЩАЯ ЛОГИКА DRAG-AND-DROP КАНБАНА
// ═══════════════════════════════════════════════════

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
