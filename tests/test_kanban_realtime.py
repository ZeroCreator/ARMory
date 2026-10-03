from pathlib import Path
import shutil

import pytest
from playwright.sync_api import sync_playwright


STATIC_ROOT = Path(__file__).resolve().parents[1] / "app" / "static" / "js"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=shutil.which("google-chrome") or shutil.which("chromium"),
            headless=True,
        )
        yield browser
        browser.close()


@pytest.fixture(params=["project", "global"])
def board_page(browser, request):
    page = browser.new_page()
    page.set_content('<div id="kanban-board"></div>')
    page.add_script_tag(content="""
        const API_BASE = '/api';
        const PROJECT_ID = 1;
        window.EventSource = class extends EventTarget {
            constructor() { super(); window.eventSource = this; }
            close() {}
        };
        window.emitKanbanEvent = data => {
            const event = new Event('kanban');
            event.data = JSON.stringify(data);
            window.eventSource.dispatchEvent(event);
        };
        window.fullReloads = 0;
        window.apiCalls = 0;
        async function api() {
            window.apiCalls++;
            return structuredClone(window.nextTask);
        }
    """)
    page.add_script_tag(path=str(STATIC_ROOT / "kanban_common.js"))
    script = "kanban.js" if request.param == "project" else "kanban_global.js"
    page.add_script_tag(path=str(STATIC_ROOT / script))
    page.evaluate("""kind => {
        window.boardKind = kind;
        loadKanbanBoard = () => { window.fullReloads++; };
        const board = document.getElementById('kanban-board');
        for (const [id, name] of [[1, 'first'], [2, 'second']]) {
            const column = document.createElement('div');
            column.className = 'kanban-column';
            column.innerHTML = `<span class="kanban-column-count"></span>
                <div class="kanban-column-body" data-status-id="${id}" data-column-name="${name}"></div>`;
            board.append(column);
        }
        window.nextTask = {
            id: 1, project_id: 1, status_id: 1, status: {name: 'first'},
            title: '<task-title>', priority: 'medium', attachments: [],
        };
        kanbanData.tasks = [structuredClone(window.nextTask)];
        board.querySelector('.kanban-column-body').innerHTML = renderTaskCard(window.nextTask);
        updateKanbanColumnCounts();
        window.originalCard = board.querySelector('.kanban-card');
        window.originalTitle = board.querySelector('.kanban-card-title');
        window.originalColumn = board.querySelector('.kanban-column');
        window.originalCard.classList.add('kanban-card-highlighted');
        if (kind === 'project') connectKanbanEvents(1);
        else connectGlobalKanbanEvents();
    }""", request.param)
    yield page
    page.close()


def test_agent_move_and_time_events_preserve_board_and_card(board_page):
    page = board_page
    page.evaluate("""() => {
        window.nextTask.status_id = 2;
        window.nextTask.status = {name: 'second'};
        emitKanbanEvent({type: 'task_changed', project_id: 1, task_id: 1});
    }""")
    page.wait_for_function("window.originalCard.parentElement.dataset.columnName === 'second'")
    assert page.evaluate("""() => {
        const board = document.getElementById('kanban-board');
        return board.querySelector('.kanban-card') === window.originalCard &&
            board.querySelector('.kanban-card-title') === window.originalTitle &&
            board.querySelector('.kanban-column') === window.originalColumn &&
            !window.originalCard.classList.contains('kanban-card-new') &&
            window.originalCard.classList.contains('kanban-card-highlighted') &&
            Array.from(board.querySelectorAll('.kanban-column-count')).map(el => el.textContent).join() === '0,1';
    }""")
    page.evaluate("""() => {
        window.mutations = [];
        window.observer = new MutationObserver(records => window.mutations.push(...records));
        window.observer.observe(document.getElementById('kanban-board'), {subtree: true, childList: true, attributes: true});
        window.nextTask.work_seconds = 60;
        emitKanbanEvent({type: 'task_time_changed', project_id: 1, task_id: 1});
    }""")
    page.wait_for_function("kanbanData.tasks[0].work_seconds === 60")
    assert page.evaluate("window.fullReloads === 0 && window.mutations.length === 0")
    page.evaluate("""() => {
        window.nextTask.work_seconds = 120;
        emitKanbanEvent({type: 'task_time_changed', project_id: 1, task_id: 1});
    }""")
    page.wait_for_function("kanbanData.tasks[0].work_seconds === 120")
    assert page.evaluate("window.fullReloads === 0 && window.mutations.length === 0")


def test_external_edit_keeps_card_and_local_drag_ignores_echo(board_page):
    page = board_page
    page.evaluate("""() => {
        window.nextTask.title = '<updated-title>';
        window.nextTask.is_closed = true;
        emitKanbanEvent({type: 'task_changed', project_id: 1, task_id: 1});
    }""")
    page.wait_for_function("document.querySelector('.kanban-card-title').textContent.includes('<updated-title>')")
    assert page.evaluate("""() => {
        const card = document.querySelector('.kanban-card');
        return card === window.originalCard && card.classList.contains('kanban-card-closed') &&
            !card.classList.contains('kanban-card-new') && window.fullReloads === 0;
    }""")
    api_calls = page.evaluate("window.apiCalls")
    page.evaluate("""() => {
        markKanbanReloadIgnored();
        emitKanbanEvent({type: 'task_changed', project_id: 1, task_id: 1});
    }""")
    assert page.evaluate("window.apiCalls") == api_calls


def test_new_task_still_appears_and_structure_events_reload_board(board_page):
    page = board_page
    page.evaluate("""() => {
        window.nextTask = {...window.nextTask, id: 2};
        emitKanbanEvent({type: 'task_changed', project_id: 1, task_id: 2});
    }""")
    page.wait_for_function('document.querySelector(\'.kanban-card[data-id="2"]\')?.classList.contains("kanban-card-new")')
    assert page.locator('.kanban-card').count() == 2
    page.wait_for_function('!document.querySelector(\'.kanban-card[data-id="2"]\').classList.contains("kanban-card-new")')
    page.evaluate("emitKanbanEvent({type: 'board_changed', project_id: 1})")
    assert page.evaluate("window.fullReloads") == 1
