"""Exercise the tree browser's visible layout in a clean, headless Qt process."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_selected_node_shows_compact_tree_browser_layout(tmp_path, theme):
    script = textwrap.dedent(
        """
        import sys
        import types
        from aqt.qt import QApplication, QLabel, QPushButton
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QPalette

        app = QApplication([])
        dark = sys.argv[2] == 'dark'
        palette = app.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('#242424' if dark else '#f5f5f5'))
        palette.setColor(QPalette.ColorRole.Base, QColor('#242424' if dark else '#ffffff'))
        palette.setColor(QPalette.ColorRole.WindowText, QColor('#f2f2f2' if dark else '#202020'))
        palette.setColor(QPalette.ColorRole.Text, QColor('#f2f2f2' if dark else '#202020'))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor('#f2f2f2' if dark else '#202020'))
        palette.setColor(QPalette.ColorRole.Mid, QColor('#101010' if dark else '#c0c0c0'))
        app.setPalette(palette)
        sys.path[:0] = ['frontend', 'backend']
        for name, attrs in {
            'knowledge_tree_priority_dialog': {
                'KnowledgeTreePriorityDialog': object,
                'OP_FADE_CHILDREN': 'fade', 'OP_FOCUS_BRANCH': 'focus',
                'OP_LINEAR_SPREAD': 'linear', 'OP_RANDOMIZE': 'randomize',
                'OP_SET_SELECTED': 'selected', 'OP_SHIFT_SUBTREE': 'shift',
            },
            'knowledge_tree_postpone_dialog': {
                'KnowledgeTreePostponeDialog': object,
                'resolve_current_browser_card_ids': lambda: [],
            },
            'knowledge_tree_subset_dialog': {'KnowledgeTreeSubsetDialog': object},
        }.items():
            module = types.ModuleType(name)
            module.__dict__.update(attrs)
            sys.modules[name] = module

        import knowledge_tree_dialog as tree
        tree.KnowledgeTreeDialog.reload = lambda self, **kwargs: None

        class Note:
            def note_type(self):
                return {'flds': [{'name': 'Front'}, {'name': 'Back'}, {'name': 'Incremento_Source_Title'}]}

            def __getitem__(self, name):
                return {'Front': '<b>Question</b>', 'Back': 'Full answer',
                        'Incremento_Source_Title': 'Reference'}[name]

        class Card:
            def note(self):
                return Note()

        tree.mw = types.SimpleNamespace(col=types.SimpleNamespace(get_card=lambda _id: Card()))
        dialog = tree.KnowledgeTreeDialog(sys.argv[1], profile='TestProfile')
        dialog._refresh_selection_ui()
        assert [action.text() for action in dialog._add_btn.menu().actions()] == [
            'Add Root Topic', 'Add Root Item'
        ]
        dialog._selected_pdf_target = lambda **kwargs: None
        rows = [
            {'card_id': 1, 'title': 'Root', 'node_kind': 'topic', 'priority': 80, 'parent_card_id': None},
            {'card_id': 2, 'title': 'Child', 'node_kind': 'item', 'priority': 10, 'parent_card_id': 1},
        ]
        dialog._rows_cache = rows
        dialog._row_by_card_id = {row['card_id']: row for row in rows}
        root = dialog._item_for_row(rows[0])
        child = dialog._item_for_row(rows[1])
        root.addChild(child)
        dialog._tree.addTopLevelItem(root)
        child.setSelected(True)
        dialog._tree.setCurrentItem(child)
        dialog.show()
        app.processEvents()

        assert [button.text() for button in dialog._toolbar_buttons] == ['Study', 'Add', 'Refresh']
        assert [action.text() for action in dialog._add_btn.menu().actions()] == [
            'Add Topic Child', 'Add Item Child'
        ]
        assert dialog._search_edit.parent().objectName() == 'KnowledgeToolbar'
        assert [dialog._tabs.tabText(i) for i in range(dialog._tabs.count())] == ['Workspace', 'Search']
        assert dialog._workspace_summary.text() == '2 cards · 1 branch'
        assert 'Root › Child' in dialog._breadcrumb.text()
        assert not dialog._add_btn.icon().isNull()
        text_color = dialog.palette().color(QPalette.ColorRole.Text)
        for button in (dialog._study_btn, dialog._add_btn, dialog._refresh_btn):
            assert button.iconSize() == QSize(18, 18), button.text()
            icon = button.icon().pixmap(18, 18).toImage()
            opaque = [icon.pixelColor(x, y) for x in range(icon.width())
                      for y in range(icon.height()) if icon.pixelColor(x, y).alpha() >= 220]
            assert opaque, button.text()
            assert all(max(abs(pixel.red() - text_color.red()),
                           abs(pixel.green() - text_color.green()),
                           abs(pixel.blue() - text_color.blue())) <= 20
                       for pixel in opaque), button.text()

        add_image = dialog._add_btn.grab().toImage()
        arrow_ys = [y for y in range(add_image.height())
                    for x in range(add_image.width() - 17, add_image.width() - 2)
                    if max(abs(add_image.pixelColor(x, y).red() - text_color.red()),
                           abs(add_image.pixelColor(x, y).green() - text_color.green()),
                           abs(add_image.pixelColor(x, y).blue() - text_color.blue())) <= 30]
        assert arrow_ys
        assert max(abs(min(arrow_ys) - add_image.height() // 2),
                   abs(max(arrow_ys) - add_image.height() // 2)) <= 6
        dialog._add_btn.click()
        app.processEvents()
        assert dialog._add_btn.menu().isVisible()
        dialog._add_btn.menu().hide()
        assert isinstance(dialog._tree.itemDelegateForColumn(1), tree._PriorityDelegate)
        assert child.data(1, tree._ROLE_PRIORITY_VALUE) == 10
        assert dialog._kind_badge.text() == 'Item'
        assert dialog._priority_badge.text() == 'Priority 10'
        assert dialog._selection_text.text() == 'Question\\n\\nFull answer'
        assert dialog._meta_card_id.text() == '2'
        assert dialog._meta_source.text() == 'Reference'
        assert dialog._inspect_btn.isEnabled() and dialog._more_btn.isEnabled()

        def luminance(color):
            components = [color.redF(), color.greenF(), color.blueF()]
            linear = [component / 12.92 if component <= 0.04045
                      else ((component + 0.055) / 1.055) ** 2.4
                      for component in components]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        background = luminance(dialog.palette().color(QPalette.ColorRole.Base))
        for label in dialog.findChildren(QLabel):
            if label.objectName() not in {'KnowledgeHint', 'KnowledgeMeta', 'KnowledgeBreadcrumb'}:
                continue
            foreground = luminance(label.palette().color(QPalette.ColorRole.WindowText))
            contrast = (max(background, foreground) + 0.05) / (min(background, foreground) + 0.05)
            assert contrast >= 4.5, (label.objectName(), label.text(), contrast)

        placeholder = luminance(dialog._search_edit.palette().color(QPalette.ColorRole.PlaceholderText))
        placeholder_contrast = (max(background, placeholder) + 0.05) / (min(background, placeholder) + 0.05)
        assert placeholder_contrast >= 4.5, ('search placeholder', placeholder_contrast)

        close_button = next(button for button in dialog.findChildren(QPushButton)
                            if button.text() == 'Close')
        for button in (dialog._study_btn, close_button):
            image = button.icon().pixmap(18, 18).toImage()
            pixels = [image.pixelColor(x, y) for x in range(image.width())
                      for y in range(image.height()) if image.pixelColor(x, y).alpha() >= 200]
            assert pixels, button.text()
            icon_luminance = sum(luminance(pixel) for pixel in pixels) / len(pixels)
            icon_contrast = (max(background, icon_luminance) + 0.05) / (min(background, icon_luminance) + 0.05)
            assert icon_contrast >= 4.5, (button.text(), icon_contrast)

        shown = []
        dialog._show_context_menu = lambda pos, *, global_pos=None: shown.append(global_pos)
        dialog._more_btn.click()
        assert len(shown) == 1 and shown[0] is not None
        dialog._search_edit.textEdited.emit('query')
        assert dialog._tabs.currentIndex() == 1
        assert dialog._tabs.widget(0).isHidden() and dialog._tabs.widget(1).isVisible()
        dialog._tree.blockSignals(True)
        root.setText(0, 'A long root title ' * 30)
        child.setText(0, 'A long child title ' * 30)
        dialog._tree.blockSignals(False)
        dialog.resize(500, 720)
        app.processEvents()
        dialog._update_breadcrumb()
        assert '…' in dialog._breadcrumb.text()
        assert 'A long root title' in dialog._breadcrumb.toolTip()
        dialog._tree.grab()
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), theme],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
