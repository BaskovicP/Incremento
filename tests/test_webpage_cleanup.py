"""Exercise removal and recovery on an inert page in a disposable browser."""

import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest


def test_cleanup_removes_only_clicked_elements_and_undo_reset_restore_original_styles(tmp_path):
    from webpage_browser import browser_runtime, _runtime_dir
    runtime = browser_runtime()
    if runtime is None:
        pytest.skip("Optional browser component is not installed")
    script = dedent('''
        import sys
        sys.path[:0] = [sys.argv[1], 'frontend']
        from playwright.sync_api import sync_playwright
        from webpage_cleanup import CLEANUP_SCRIPT
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page = browser.new_page()
            page.set_content('<nav style="color:red"><span>Clutter</span></nav><main><h1>Article</h1><section>Keep comments</section></main>')
            page.evaluate(CLEANUP_SCRIPT)
            page.locator('nav span').click(modifiers=['Shift'])
            assert not page.locator('nav').is_visible()
            assert page.locator('main section').is_visible()
            page.evaluate('incrementoCleanup.undo()')
            assert page.locator('nav').get_attribute('style') == 'color:red'
            page.locator('nav span').click()
            page.locator('main section').click()
            page.evaluate('incrementoCleanup.reset()')
            assert page.locator('nav span').is_visible()
            assert page.locator('main section').is_visible()
            page.locator('nav span').click(modifiers=['Shift'])
            page.evaluate('incrementoCleanup.finish()')
            assert page.locator('[data-incremento-zap-overlay]').count() == 0
            assert not page.locator('nav').is_visible()
            assert page.locator('main').is_visible()
            browser.close()
    ''')
    result = subprocess.run([runtime[0], '-c', script, str(_runtime_dir() / 'packages'), runtime[1]],
                            env=dict(os.environ), capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


def test_zap_outline_keyboard_undo_and_serialization_leave_no_tool_artifacts(tmp_path):
    from webpage_browser import browser_runtime, _runtime_dir
    runtime = browser_runtime()
    if runtime is None:
        pytest.skip('Optional browser component is not installed')
    script = dedent('''
        import sys
        sys.path[:0] = [sys.argv[1], 'frontend']
        from playwright.sync_api import sync_playwright
        from webpage_cleanup import CLEANUP_SCRIPT
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page = browser.new_page()
            page.set_content('<nav id="nav" style="color:red"><span>Clutter</span></nav><main><h1>Article</h1><section>Keep comments</section></main>')
            page.evaluate(CLEANUP_SCRIPT)
            before = page.locator('nav').bounding_box()
            page.keyboard.down('Shift')
            page.locator('nav span').hover()
            overlay = page.locator('[data-incremento-zap-overlay]')
            assert overlay.is_visible()
            assert page.locator('nav').bounding_box() == before
            assert overlay.evaluate('(e) => getComputedStyle(e).borderTopColor') == 'rgb(227, 75, 85)'
            assert overlay.bounding_box()['width'] == before['width']
            page.keyboard.up('Shift')
            page.locator('nav span').hover()
            child_width = page.locator('nav span').bounding_box()['width']
            page.keyboard.down('Shift')
            assert overlay.bounding_box()['width'] == before['width']
            page.keyboard.up('Shift')
            assert overlay.bounding_box()['width'] == child_width
            page.locator('nav span').click(modifiers=['Shift'])
            assert page.locator('nav').count() == 0
            assert page.evaluate('incrementoCleanup.state().count') == 1
            page.keyboard.press('Control+z')
            assert page.locator('nav').get_attribute('style') == 'color:red'
            page.locator('nav span').hover()
            page.keyboard.press('Delete')
            assert page.locator('nav span').count() == 0
            page.evaluate('incrementoCleanup.reset()')
            page.keyboard.press('Escape')
            assert page.evaluate('incrementoCleanup.state().enabled') is False
            page.locator('nav span').click()
            assert page.locator('nav span').count() == 1
            page.evaluate('incrementoCleanup.setEnabled(true)')
            page.locator('nav span').click(modifiers=['Shift'])
            exported = page.evaluate('incrementoCleanup.serialize()')
            assert '<!DOCTYPE html>' in exported
            assert 'Clutter' not in exported and 'Article' in exported
            assert 'incremento-zap' not in exported
            page.evaluate('incrementoCleanup.undo()')
            assert page.locator('nav span').is_visible()
            browser.close()
    ''')
    result = subprocess.run([runtime[0], '-c', script, str(_runtime_dir() / 'packages'), runtime[1]],
                            capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
