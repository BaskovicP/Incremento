"""The optional study presentation leaves normal Anki review intact."""
from tests.test_study_navigation_qt import run_scene


def test_disabled_workspace_does_not_add_review_ui_or_start_resource_queries():
    run_scene('''
        ui.reset(); pending.clear(); scripts.clear()
        ui.load_addon_config=lambda *a: dict(study_workspace_enabled=False)
        ui.reviewer_shown()
        assert not pending and not ui._review_token and ui._window is None
        assert web.toPlainText()=='Original question' and web.isEnabled() and bottom.isEnabled()
        assert mw.reviewer.auto_advance_enabled and mw.reviewer.state=='question'
        assert scripts==[ui.reviewer_navigation_clear_script()]
        scripts.clear(); mw.reviewer.state='answer'; web.setPlainText('Original answer')
        ui.reviewer_shown()
        assert not pending and web.toPlainText()=='Original answer'
        assert scripts==[ui.reviewer_navigation_clear_script()]
    ''')


def test_disabling_an_active_visit_restores_the_same_card_and_drops_late_results():
    run_scene('''
        ui.show_resources(); w=ui._window; drain(); click(w,'video'); drain()
        assert not web.isEnabled() and w.player is not None
        ui.check_reviewer_resources(force=True); old=pending.pop(0)
        token=ui._review_token
        ui.load_addon_config=lambda *a: dict(study_workspace_enabled=False)
        ui.apply_settings(dict(study_workspace_enabled=False))
        assert w.visit.closed and ui._window is None and not ui._review_token
        assert web.isVisible() and bottom.isVisible() and web.isEnabled() and bottom.isEnabled()
        assert web.toPlainText()=='Original question' and mw.reviewer.state=='question'
        assert mw.reviewer.card.id==41 and mw.reviewer.auto_advance_enabled
        count=len(scripts)
        old.success(dict(documents=[document],recordings=[recording]))
        bridge('book',token=token)
        assert len(scripts)==count and ui._window is None
        assert scripts[-1]==ui.reviewer_navigation_clear_script()
    ''')


def test_reenabling_adds_the_workspace_without_replacing_or_answering_the_card():
    run_scene('''
        config=dict(study_workspace_enabled=False)
        ui.load_addon_config=lambda *a: config
        ui.apply_settings(config)
        config['study_workspace_enabled']=True
        ui.apply_settings(config); drain()
        assert ui._review_token and 'incremento-study-navigation' in scripts[-1]
        assert ui._window is None and web.toPlainText()=='Original question'
        assert mw.reviewer.card.id==41 and mw.reviewer.state=='question' and web.isEnabled()
    ''')


def test_normal_card_mode_keeps_explicit_resources_available_and_unchanged_saves_do_not_close_them():
    run_scene('''
        config=dict(study_workspace_enabled=False)
        ui.load_addon_config=lambda *a: config
        ui.apply_settings(config)
        ui.show_resources(); w=ui._window; drain(); click(w,'book'); drain()
        assert w.reader is not None and not ui._review_token
        reader=w.reader
        ui.apply_settings(config)
        assert ui._window is w and not w.visit.closed and w.reader is reader
        click(w,'card')
        assert web.isVisible() and web.toPlainText()=='Original question'
        assert not ui._review_token and scripts[-1]==ui.reviewer_navigation_clear_script()
        w.close()
    ''')
