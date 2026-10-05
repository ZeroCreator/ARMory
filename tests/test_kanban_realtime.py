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


@pytest.mark.parametrize("is_global", [False, True])
def test_time_status_column_updates_via_shared_events_and_keeps_totals_aligned(browser, is_global):
    page = browser.new_page()
    try:
        page.set_content('''
            <button id="task-time-export-xlsx"></button>
            <div id="task-time-context-menu"></div>
            <table><tbody id="task-time-table-body"></tbody><tfoot id="task-time-table-foot"></tfoot></table>
        ''')
        page.add_script_tag(content=f"const IS_GLOBAL = {str(is_global).lower()}; const PROJECT_ID = IS_GLOBAL ? null : 1;")
        page.add_script_tag(path=str(STATIC_ROOT / "tasks_time.js"))
        page.evaluate('''() => {
            window.timeReloads = 0;
            loadTaskTimeData = () => {
                window.timeReloads++;
                renderTaskTimeTable([window.nextTimeTask]);
            };
            window.nextTimeTask = {
                id: 1, project_id: 1, title: '<task-title>', status: {name: 'Тестирование'},
                estimated_minutes: 30, testing_seconds: 120, actual_seconds: 120,
                time_tracking_status: 'running',
            };
            renderTaskTimeTable([window.nextTimeTask]);
        }''')
        expected_columns = 10 if is_global else 9
        status_index = 4 if is_global else 3
        assert page.locator('#task-time-table-body td').count() == expected_columns
        assert page.locator('#task-time-table-body td').nth(status_index).inner_text() == 'В работе'
        for status, label in [('paused', 'Остановлено'), ('completed', 'Завершено'), ('running', 'В работе')]:
            page.evaluate('''status => {
                window.nextTimeTask.time_tracking_status = status;
                window.dispatchEvent(new CustomEvent('armory:kanban', {
                    detail: {type: 'task_time_changed', project_id: 1, task_id: 1},
                }));
            }''', status)
            assert page.locator('#task-time-table-body td').nth(status_index).inner_text() == label
            assert page.locator('#task-time-table-body td').nth(status_index - 1).inner_text() == 'Тестирование'
        assert page.locator('#task-time-table-foot td').first.get_attribute('colspan') == str(status_index + 1)
        assert page.locator('#task-time-table-foot td').nth(1).inner_text() == '30 мин'
        page.evaluate("window.dispatchEvent(new Event('armory:events-connected'))")
        assert page.evaluate('window.timeReloads') == 4
        page.evaluate("window.dispatchEvent(new CustomEvent('armory:kanban', {detail: {type: 'task_time_changed', project_id: 2}}))")
        assert page.evaluate('window.timeReloads') == (5 if is_global else 4)
        page.evaluate('renderTaskTimeTable([])')
        assert page.locator('#task-time-table-body td').get_attribute('colspan') == str(expected_columns)
    finally:
        page.close()


def test_zero_time_deviation_is_displayed_as_dash(browser):
    page = browser.new_page()
    try:
        page.set_content('''
            <button id="task-time-export-xlsx"></button>
            <div id="task-time-context-menu"></div>
            <table><tbody id="task-time-table-body"></tbody><tfoot id="task-time-table-foot"></tfoot></table>
        ''')
        page.add_script_tag(content="const IS_GLOBAL = false; const PROJECT_ID = 1;")
        page.add_script_tag(path=str(STATIC_ROOT / "tasks_time.js"))
        page.evaluate('''() => renderTaskTimeTable([{
            id: 1, project_id: 1, title: '<task-title>', status_id: 2,
            status: {name: 'Тестирование'}, estimated_minutes: 30,
            actual_seconds: 30 * 60, work_seconds: 30 * 60,
            testing_seconds: 0, time_tracking_status: 'completed',
        }])''')
        assert page.locator('#task-time-table-body td').last.inner_text() == '—'
        assert page.locator('#task-time-table-foot td').last.inner_text() == '—'
    finally:
        page.close()


@pytest.mark.parametrize("phase", ["work", "testing"])
def test_time_controls_start_stop_and_lock_on_agent_events(browser, phase):
    page = browser.new_page()
    try:
        page.set_content('''
            <button id="task-time-export-xlsx"></button><div id="task-time-context-menu"></div>
            <table id="task-time-table"><tbody id="task-time-table-body"></tbody><tfoot id="task-time-table-foot"></tfoot></table>
        ''')
        template = (STATIC_ROOT.parents[1] / "templates" / "tasks_time.html").read_text()
        page.add_style_tag(content=template.split('<style>', 1)[1].split('</style>', 1)[0])
        page.add_style_tag(content='#task-time-table td { min-width: 180px; }')
        page.add_script_tag(content="const IS_GLOBAL = true; const PROJECT_ID = null;")
        page.add_script_tag(path=str(STATIC_ROOT / "tasks_time.js"))
        page.evaluate('''() => {
            timeStatuses = {1: [{id: 1, name: 'В работе'}, {id: 2, name: 'Тестирование'}, {id: 3, name: '<status-name>'}]};
            timeTasks = [{id: 1, project_id: 1, title: '<task-title>', status_id: 1, status: {name: 'В работе'}, time_tracking_status: 'completed'}];
            displayedTimeTasks = timeTasks;
            window.controlRequests = [];
            window.fetch = async (url, options) => {
                const body = options.body ? JSON.parse(options.body) : null;
                controlRequests.push({url, method: options.method, body});
                const task = timeTasks[0];
                if (url.endsWith('/start')) {
                    task.time_tracking_status = 'running'; task.manual_time_phase = body.phase;
                } else if (url.endsWith('/pause')) {
                    task.time_tracking_status = 'paused'; task.manual_time_phase = null;
                } else {
                    task.status_id = body.status_id;
                }
                return {ok: true};
            };
            loadTaskTimeData = async () => renderTaskTimeTable(timeTasks);
            renderTaskTimeTable(timeTasks);
        }''')
        status = page.locator('.task-time-status')
        timers = page.locator('.task-time-timer')
        timer = timers.nth(0 if phase == 'work' else 1)
        other = timers.nth(1 if phase == 'work' else 0)
        assert status.locator('option').count() == 3
        assert status.is_enabled()
        assert status.evaluate("element => getComputedStyle(element).color") == 'rgb(33, 37, 41)'
        assert status.evaluate("element => getComputedStyle(element).backgroundColor") == 'rgb(248, 249, 250)'
        for cell in page.locator('.task-time-effort').all():
            geometry = cell.evaluate('''element => {
                const cell = element.getBoundingClientRect();
                const value = element.firstElementChild.getBoundingClientRect();
                const button = element.lastElementChild.getBoundingClientRect();
                return {left: value.left - cell.left, right: cell.right - button.right,
                    center: (value.top + value.bottom - button.top - button.bottom) / 2};
            }''')
            assert abs(geometry['left']) < 1
            assert abs(geometry['right']) < 1
            assert abs(geometry['center']) < 1
        assert timer.get_attribute('aria-label') == 'запустить таймер'
        timer.click()
        assert timer.get_attribute('aria-label') == 'остановить таймер'
        assert 'task-time-timer-danger' in timer.get_attribute('class')
        assert status.is_disabled()
        assert status.evaluate("element => getComputedStyle(element).color") == 'rgb(33, 37, 41)'
        assert other.is_disabled()
        assert other.locator('..').get_attribute('title') == 'ручной таймер не доступен'
        timer.click()
        assert timer.get_attribute('aria-label') == 'запустить таймер'
        assert status.is_enabled()
        status.select_option('3')
        assert page.evaluate('controlRequests') == [
            {'url': '/api/tasks/1/time/manual/start', 'method': 'POST', 'body': {'phase': phase}},
            {'url': '/api/tasks/1/time/manual/pause', 'method': 'POST', 'body': None},
            {'url': '/api/tasks/1/time/status', 'method': 'PATCH', 'body': {'status_id': 3}},
        ]
        page.evaluate('''() => {
            timeTasks[0].time_tracking_status = 'running';
            window.dispatchEvent(new CustomEvent('armory:kanban', {detail: {type: 'task_time_changed', project_id: 1}}));
        }''')
        assert status.is_disabled()
        for index in range(2):
            assert timers.nth(index).is_disabled()
            assert 'task-time-timer-secondary' in timers.nth(index).get_attribute('class')
        page.evaluate('''() => {
            timeTasks[0].time_tracking_status = 'completed';
            window.dispatchEvent(new CustomEvent('armory:kanban', {detail: {type: 'task_time_changed', project_id: 1}}));
        }''')
        assert status.is_enabled()
        assert timers.nth(0).is_enabled()
        assert timers.nth(1).is_enabled()
    finally:
        page.close()


@pytest.mark.parametrize("container_id", ["projects-list", "task-time-table"])
def test_shared_sse_forwards_time_events_without_opening_another_stream(browser, container_id):
    page = browser.new_page()
    try:
        page.set_content(f'<div id="{container_id}"></div>')
        page.add_script_tag(content='''
            const API_BASE = '/api';
            window.streamCount = 0;
            window.URL = class {
                constructor() { this.searchParams = new URLSearchParams(); }
            };
            window.EventSource = class extends EventTarget {
                constructor() { super(); window.streamCount++; window.sharedStream = this; }
                close() {}
            };
            window.addEventListener('armory:kanban', event => {window.lastTimeEvent = event.detail;});
            window.addEventListener('armory:events-connected', () => {window.connected = true;});
        ''')
        source = (STATIC_ROOT / 'app.js').read_text()
        start = source.index('let unreadEventSource = null;')
        end = source.index('async function loadUnreadCountsAndUpdateBells()', start)
        page.add_script_tag(content='let dailyNewsDate = null;\n' + source[start:end])
        page.evaluate('''() => {
            startUnreadStream();
            startUnreadStream();
            window.sharedStream.dispatchEvent(new Event('open'));
            const event = new Event('kanban');
            event.data = JSON.stringify({type: 'task_time_changed', project_id: 1, task_id: 2});
            window.sharedStream.dispatchEvent(event);
        }''')
        assert page.evaluate('window.streamCount') == 1
        assert page.evaluate('window.connected') is True
        assert page.evaluate('window.lastTimeEvent') == {'type': 'task_time_changed', 'project_id': 1, 'task_id': 2}
    finally:
        page.close()
