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


def test_multi_filter_selects_multiple_values(browser):
    page = browser.new_page()
    try:
        page.set_content('''
            <label for="filter-status">Статус</label>
            <select id="filter-status" data-multi-filter>
                <option value="">Все</option>
                <option value="todo">К выполнению</option>
                <option value="testing">Тестирование</option>
            </select>
        ''')
        page.add_script_tag(path=str(STATIC_ROOT / "multi_filter.js"))

        page.locator("#filter-status-button").click()
        page.locator('#filter-status-option-0').check()
        page.locator('#filter-status-option-1').check()

        assert page.evaluate("getFilterValues('filter-status')") == ["todo", "testing"]
        assert page.locator("#filter-status-button").inner_text() == "К выполнению, Тестирование"

        page.locator("#filter-status-button").click()
        assert page.locator(".multi-filter-menu").get_attribute("hidden") == ""
        page.locator("#filter-status-button").click()
        page.keyboard.press("Escape")
        assert page.locator(".multi-filter-menu").get_attribute("hidden") == ""
    finally:
        page.close()
