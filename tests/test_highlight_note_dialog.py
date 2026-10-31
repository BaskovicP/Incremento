"""Exercise the actual Qt editor in a clean, offscreen process."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_annotation_editor_formats_selection_roundtrips_lists_and_rejects_unsafe_links(tmp_path):
    result = subprocess.run([sys.executable, '-c', dedent('''
        import sys
        from pathlib import Path
        sys.path.extend([str(Path.cwd() / 'backend'), str(Path.cwd() / 'frontend')])
        from aqt.qt import QApplication, QTextCursor, QMimeData
        from frontend.highlight_note_dialog import HighlightNoteDialog
        app = QApplication([])
        dialog = HighlightNoteDialog(None, title='Note', excerpt='<b>literal source</b>', current_note='Rice theorem')
        editor = dialog._editor
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        for name in ('bold', 'italic', 'underline', 'strike'):
            dialog._actions[name].trigger()
        assert '<b>' in dialog.note_html() and '<i>' in dialog.note_html()
        assert '<u>' in dialog.note_html() and '<s>' in dialog.note_html()
        assert dialog.note_text() == 'Rice theorem'
        dialog._set_link('https://example.com/theorem')
        assert 'href="https://example.com/theorem"' in dialog.note_html()
        before = dialog.note_html()
        try:
            dialog._set_link('javascript:alert(1)')
            raise AssertionError('Unsafe URL was accepted')
        except ValueError:
            pass
        assert dialog.note_html() == before
        reopened = HighlightNoteDialog(None, title='Note', excerpt='', current_note=dialog.note_text(), current_note_html=before)
        assert reopened.note_html() == before
        cursor = reopened._editor.textCursor()
        cursor.setPosition(2)
        reopened._editor.setTextCursor(cursor)
        reopened._set_link('https://example.com/updated')
        assert reopened.note_text() == 'Rice theorem'
        assert 'https://example.com/updated' in reopened.note_html()
        assert 'https://example.com/theorem' not in reopened.note_html()
        cursor.setPosition(2)
        reopened._editor.setTextCursor(cursor)
        reopened._set_link('')
        assert '<a ' not in reopened.note_html()
        reopened._editor.selectAll()
        reopened._actions['clear'].trigger()
        assert '<b>' not in reopened.note_html() and '<a ' not in reopened.note_html()
        editor.setPlainText('First\\nSecond')
        editor.selectAll()
        dialog._actions['clear'].trigger()
        dialog._actions['bullets'].trigger()
        assert dialog.note_html() == '<ul><li>First</li><li>Second</li></ul>'
        dialog._actions['numbers'].trigger()
        assert dialog.note_html() == '<ol><li>First</li><li>Second</li></ol>'
        assert dialog.note_text() == 'First\\nSecond'
        editor.setPlainText('<b>old literal</b>')
        assert dialog.note_text() == '<b>old literal</b>'
        assert '&lt;b&gt;old literal&lt;/b&gt;' in dialog.note_html()
        editor.clear()
        mime = QMimeData()
        mime.setHtml('<b>pasted</b><img src="file:///tmp/private"><a href="javascript:bad()"> link</a>')
        editor.insertFromMimeData(mime)
        assert '<b>pasted</b>' in dialog.note_html()
        assert 'file:' not in dialog.note_html() and 'javascript:' not in dialog.note_html()
        from frontend import highlight_note_dialog as ui
        messages = []
        ui.showInfo = lambda message, **kwargs: messages.append(message)
        editor.setPlainText('x' * 65537)
        dialog.accept()
        assert dialog.result() == 0 and len(editor.toPlainText()) == 65537
        assert len(messages) == 1
        dialog.close()
        reopened.close()
    ''')], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_pasted_image_is_compact_resizable_undoable_and_reopens_with_caption():
    result = subprocess.run([sys.executable, '-c', dedent('''
        import base64, sys
        from pathlib import Path
        sys.path.extend([str(Path.cwd() / 'backend'), str(Path.cwd() / 'frontend')])
        from aqt.qt import QApplication, QImage, QMimeData, QTextCursor
        from frontend.highlight_note_dialog import HighlightNoteDialog
        from backend.annotation_notes import image_info
        app = QApplication([])
        dialog = HighlightNoteDialog(None, title='Note', excerpt='landmark', current_note='')
        editor = dialog._editor
        image = QImage(2400, 1600, QImage.Format.Format_RGB32)
        image.fill(0xff409060)
        mime = QMimeData()
        mime.setImageData(image)
        assert editor.canInsertFromMimeData(mime)
        editor.insertFromMimeData(mime)
        markup = dialog.note_html()
        assert '<img ' in markup and dialog.note_text() == ''
        source = markup.split('src="', 1)[1].split('"', 1)[0]
        data, width, height = image_info(source)
        assert len(data) <= 80 * 1024 and max(width, height) <= 960
        assert 'width="320"' in markup
        dialog._image_width.setValue(160)
        assert 'width="160"' in dialog.note_html()
        editor.undo()
        assert 'width="320"' in dialog.note_html()
        editor.redo()
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.insertPlainText('A landmark')
        saved = dialog.note_html()
        editor.selectAll()
        dialog._actions['clear'].trigger()
        assert '<img ' in dialog.note_html(), 'Clear formatting must preserve images'
        editor.undo()
        reopened = HighlightNoteDialog(None, title='Note', excerpt='', current_note=dialog.note_text(), current_note_html=saved)
        assert reopened.note_html() == saved
        assert not reopened._editor.document().isEmpty()
        before = reopened.note_html()
        hostile = QMimeData()
        hostile.setHtml('<img src="file:///tmp/private"><img src="https://example.com/tracker">')
        reopened._editor.insertFromMimeData(hostile)
        assert reopened.note_html() == before
        editor.moveCursor(QTextCursor.MoveOperation.Start)
        dialog._remove_image()
        assert '<img ' not in dialog.note_html() and dialog.note_text() == 'A landmark'
        editor.undo()
        assert '<img ' in dialog.note_html()
        # Cancel never changes the annotation's persisted value.
        reopened.reject()
        assert reopened.result() == 0
        dialog.close()
    ''')], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_pasted_local_image_url_imports_bitmap_instead_of_exposing_path(tmp_path):
    image_path = tmp_path / 'CleanShot example.png'
    result = subprocess.run([sys.executable, '-c', dedent(f'''
        import sys
        from pathlib import Path
        sys.path.extend([str(Path.cwd() / 'backend'), str(Path.cwd() / 'frontend')])
        from aqt.qt import QApplication, QImage, QMimeData, QUrl
        from frontend.highlight_note_dialog import HighlightNoteDialog
        from backend.annotation_notes import image_info
        app = QApplication([])
        path = Path({str(image_path)!r})
        image = QImage(1200, 800, QImage.Format.Format_RGB32)
        image.fill(0xff409060)
        assert image.save(str(path), 'PNG')
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        assert mime.hasUrls() and not mime.hasImage()
        dialog = HighlightNoteDialog(None, title='Note', excerpt='landmark', current_note='')
        editor = dialog._editor
        assert editor.canInsertFromMimeData(mime)
        editor.insertFromMimeData(mime)
        markup = dialog.note_html()
        assert '<img ' in markup
        assert 'file:' not in markup and str(path) not in editor.toPlainText()
        source = markup.split('src="', 1)[1].split('"', 1)[0]
        data, width, height = image_info(source)
        assert data and max(width, height) <= 960
        dialog.close()
    ''')], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_photo_paste_reencodes_metadata_and_full_note_rejection_preserves_document():
    result = subprocess.run([sys.executable, '-c', dedent('''
        import random, sys
        from pathlib import Path
        sys.path.extend([str(Path.cwd() / 'backend'), str(Path.cwd() / 'frontend')])
        from aqt.qt import QApplication, QImage, QMimeData
        from frontend import highlight_note_dialog as ui
        from backend.annotation_notes import image_info
        app = QApplication([])
        messages = []
        ui.showInfo = lambda message, **kwargs: messages.append(message)
        dialog = ui.HighlightNoteDialog(None, title='Note', excerpt='', current_note='Caption')
        raw = random.Random(42).randbytes(1200 * 800 * 3)
        image = QImage(raw, 1200, 800, 3600, QImage.Format.Format_RGB888).convertToFormat(QImage.Format.Format_ARGB32)
        image.setText('PrivateMetadata', 'must not survive encoding')
        mime = QMimeData()
        mime.setImageData(image)
        editor = dialog._editor
        editor.insertFromMimeData(mime)
        source = dialog.note_html().split('src="', 1)[1].split('"', 1)[0]
        data, width, height = image_info(source)
        assert source.startswith('data:image/jpeg;base64,')
        assert len(data) <= 80 * 1024 and max(width, height) <= 960
        assert b'must not survive' not in data
        # A tiny transparent image exercises the PNG path and the image-count budget.
        image = QImage(10, 10, QImage.Format.Format_ARGB32)
        image.fill(0x804488cc)
        mime.setImageData(image)
        for _ in range(3):
            editor.insertFromMimeData(mime)
        before = dialog.note_html()
        assert before.count('<img ') == 4
        editor.insertFromMimeData(mime)
        assert dialog.note_html() == before and len(messages) == 1
        editor.selectAll()
        editor.insertFromMimeData(mime)
        assert dialog.note_html().count('<img ') == 1 and dialog.note_text() == ''
        assert len(messages) == 1
        editor.undo()
        assert dialog.note_html() == before
        dialog.close()
    ''')], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_image_handles_drag_proportionally_or_stretch_and_roundtrip_one_undo_step():
    result = subprocess.run([sys.executable, '-c', dedent('''
        import re, sys
        from pathlib import Path
        sys.path.extend([str(Path.cwd() / 'backend'), str(Path.cwd() / 'frontend')])
        from aqt.qt import QApplication, QImage, QMimeData, QPoint, Qt, QToolButton
        from PyQt6.QtTest import QTest
        from frontend.highlight_note_dialog import HighlightNoteDialog
        app = QApplication([])
        dialog = HighlightNoteDialog(None, title='Note', excerpt='landmark', current_note='')
        dialog.show()
        editor = dialog._editor
        image = QImage(600, 300, QImage.Format.Format_RGB32)
        image.fill(0xff409060)
        mime = QMimeData()
        mime.setImageData(image)
        editor.insertFromMimeData(mime)
        app.processEvents()
        handles = {button.objectName().rsplit('-', 1)[1]: button
                   for button in editor.findChildren(QToolButton)
                   if button.objectName().startswith('annotation-image-resize-')}
        assert set(handles) == {'right', 'bottom', 'corner'}, 'Show discoverable image resize handles'
        assert all(button.isVisible() and button.accessibleName() for button in handles.values())
        def dimensions():
            match = re.search(r'width="(\\d+)" height="(\\d+)"', dialog.note_html())
            return tuple(map(int, match.groups()))
        def drag(name, dx, dy, modifiers=Qt.KeyboardModifier.NoModifier):
            handle = handles[name]
            start = handle.rect().center()
            target = handle.mapToGlobal(start) + QPoint(dx, dy)
            QTest.mousePress(handle, Qt.MouseButton.LeftButton, modifiers, start)
            for fraction in (.5, 1):
                point = handle.mapFromGlobal(target - QPoint(round(dx * (1-fraction)), round(dy * (1-fraction))))
                QTest.mouseMove(handle, point)
                app.processEvents()
            QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, modifiers, handle.mapFromGlobal(target))
            app.processEvents()
        before = dialog.note_html()
        assert dimensions() == (320, 160)
        drag('corner', 80, 40)
        assert dimensions() == (400, 200)
        editor.undo()
        assert dialog.note_html() == before, 'One Undo must undo the whole drag'
        editor.redo()
        assert dimensions() == (400, 200)
        drag('right', -100, 0)
        assert dimensions() == (300, 200), 'An edge handle should stretch only its own dimension'
        stretched = dialog.note_html()
        reopened = HighlightNoteDialog(None, title='Note', excerpt='', current_note='', current_note_html=stretched)
        assert reopened.note_html() == stretched, 'Distortion must survive saving and reopening'
        drag('corner', 40, -50, Qt.KeyboardModifier.ShiftModifier)
        assert dimensions() == (340, 150), 'Shift-corner dragging should allow free stretching'
        drag('bottom', 0, 30)
        assert dimensions() == (340, 180)
        committed = dialog.note_html()
        handle = handles['corner']
        start = handle.rect().center()
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(handle, start + QPoint(25, 25))
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=handle.rect().center())
        assert dialog.note_html() == committed, 'Escape should cancel an unfinished drag'
        assert dialog.isVisible(), 'Escape during resizing should not close the note editor'
        QTest.keyClick(handles['right'], Qt.Key.Key_Right)
        assert dimensions() == (345, 180), 'Resize handles should also support arrow keys'
        assert re.search(r'src="([^"]+)"', dialog.note_html())[1] == re.search(r'src="([^"]+)"', before)[1]
        editor.setPlainText('Only text')
        app.processEvents()
        assert not any(button.isVisible() for button in handles.values())
        image = QImage(500, 1000, QImage.Format.Format_RGB32)
        image.fill(0xff409060)
        mime.setImageData(image)
        editor.insertFromMimeData(mime)
        app.processEvents()
        assert all(button.isVisible() for button in handles.values()), 'Portrait images must start with reachable handles'
        reopened.close()
        dialog.close()
    ''')], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_clicking_right_half_of_adjacent_images_selects_the_clicked_image():
    result = subprocess.run([sys.executable, '-c', dedent('''
        import sys
        from pathlib import Path
        sys.path.extend([str(Path.cwd() / 'backend'), str(Path.cwd() / 'frontend')])
        from aqt.qt import QApplication, QImage, QMimeData, QPoint, Qt, QTextCursor
        from PyQt6.QtTest import QTest
        from frontend.highlight_note_dialog import HighlightNoteDialog
        app = QApplication([])
        dialog = HighlightNoteDialog(None, title='Note', excerpt='', current_note='')
        dialog.show()
        editor = dialog._editor
        # Existing inline annotations may contain adjacent images; new pastes
        # deliberately use separate image paragraphs.
        source = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAD0lEQVR4nGP4z8DA8J8BAAf/Af8Bf4mnAAAAAElFTkSuQmCC'
        image = f'<img src="{source}" width="100" height="60" alt="">'
        editor.setHtml('<p>' + image * 2 + '</p>')
        editor.moveCursor(QTextCursor.MoveOperation.End)
        app.processEvents()
        second = editor._image_rect()
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton,
                         pos=QPoint(round(second.x() - 20), round(second.center().y())))
        assert editor.image_cursor().selectionStart() == 0, 'Image handles must belong to the image actually clicked'
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton,
                         pos=QPoint(round(second.x() + 80), round(second.center().y())))
        assert editor.image_cursor().selectionStart() == 1
        dialog.close()
    ''')], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_image_placement_wraps_real_text_keeps_handles_and_supports_caption_navigation():
    result = subprocess.run([sys.executable, '-c', dedent('''
        import sys
        from pathlib import Path
        sys.path.extend([str(Path.cwd() / 'backend'), str(Path.cwd() / 'frontend')])
        from aqt.qt import QApplication, QImage, QMimeData, QPoint, Qt, QTextCursor
        from PyQt6.QtTest import QTest
        from frontend.highlight_note_dialog import HighlightNoteDialog
        app = QApplication([])
        caption = 'A landmark with a recognisable outline. ' * 12
        dialog = HighlightNoteDialog(None, title='Note', excerpt='', current_note=caption.strip())
        dialog.show()
        editor = dialog._editor
        image = QImage(300, 180, QImage.Format.Format_RGB32)
        image.fill(0xff409060)
        mime = QMimeData()
        mime.setImageData(image)
        editor.insertFromMimeData(mime)
        app.processEvents()
        assert dialog._image_placement.currentData() == 'block', 'New images should start on their own line'
        assert '<p align="center"><img ' in dialog.note_html()
        original = dialog.note_html()
        def placement(value):
            dialog._image_placement.setCurrentIndex(dialog._image_placement.findData(value))
            app.processEvents()
        placement('left')
        assert 'style="float:left"' in dialog.note_html()
        image_cursor = editor.image_cursor()
        image_rect = editor._image_rect()
        text = QTextCursor(editor.document())
        text.setPosition(image_cursor.selectionEnd())
        text_rect = editor.cursorRect(text)
        assert text_rect.x() >= image_rect.right() - 1 and text_rect.y() < image_rect.bottom()
        wrapped = dialog.note_html()
        editor.undo()
        assert dialog.note_html() == original, 'Placement is one Undo step'
        editor.redo()
        assert dialog.note_html() == wrapped
        placement('right')
        rect = editor._image_rect()
        assert rect.x() > editor.viewport().width() / 2, (rect, editor.viewport().width(), dialog._image_placement.currentData())
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
        assert editor.image_cursor() is not None, 'A floating image remains directly selectable'
        assert all(handle.isVisible() for handle in editor._image_handles.values())
        handle = editor._image_handles['right']
        assert abs(handle.geometry().center().x() - rect.left()) < 3, 'A right-aligned image resizes from its free left edge'
        start = handle.rect().center()
        target = handle.mapToGlobal(start) - QPoint(20, 0)
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(handle, handle.mapFromGlobal(target))
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=handle.mapFromGlobal(target))
        assert 'width="320"' in dialog.note_html() and 'style="float:right"' in dialog.note_html()
        saved = dialog.note_html()
        dialog.resize(420, 640)
        app.processEvents()
        assert dialog._image_wrap_hint.isVisible(), 'Explain narrow text columns without changing the saved layout'
        assert dialog.note_html() == saved
        dialog.resize(640, 600)
        app.processEvents()
        reopened = HighlightNoteDialog(None, title='Note', excerpt='', current_note=dialog.note_text(), current_note_html=saved)
        assert reopened.note_html() == saved
        assert reopened._image_placement.currentData() == 'right'
        placement('block')
        dialog._write_around_image(above=True)
        editor.insertPlainText('Above 😀')
        assert dialog.note_text().startswith('Above')
        cursor = editor.document().find('\\ufffc')
        editor.setTextCursor(cursor)
        dialog._write_around_image(above=True)
        editor.insertPlainText(' continued')
        assert dialog.note_text().startswith('Above 😀 continued'), 'Caption navigation must preserve non-BMP text'
        cursor = editor.document().find('\\ufffc')
        editor.setTextCursor(cursor)
        dialog._write_around_image(above=False)
        editor.insertPlainText('Below ')
        assert 'Below A landmark' in dialog.note_text()
        assert caption.strip() in dialog.note_text()
        assert '<p align="center"><img ' in dialog.note_html()
        reopened.close()
        dialog.close()
    ''')], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_wrapped_note_preview_keeps_the_following_section_below_the_image():
    result = subprocess.run([sys.executable, '-c', dedent('''
        import sys
        from pathlib import Path
        sys.path.extend([str(Path.cwd() / 'backend'), str(Path.cwd() / 'frontend')])
        from aqt.qt import QApplication, QTextBrowser
        from backend.annotation_notes import note_display_html
        app = QApplication([])
        source = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAD0lEQVR4nGP4z8DA8J8BAAf/Af8Bf4mnAAAAAElFTkSuQmCC'
        markup = f'<p><img src="{source}" width="120" height="80" alt="" style="float:right">Caption</p>'
        view = QTextBrowser()
        view.resize(500, 400)
        view.setHtml(note_display_html({'note': 'Caption', 'note_html': markup}) + '<p>Following section</p>')
        view.show()
        app.processEvents()
        cursor = view.document().find('Following section')
        assert view.cursorRect(cursor).top() >= 80, 'A wrapped note must not wrap the next note or section beside its image'
        view.close()
    ''')], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_own_line_image_alignment_changes_position_and_survives_undo_caption_navigation_and_reopen():
    result = subprocess.run([sys.executable, '-c', dedent('''
        import sys
        from pathlib import Path
        sys.path.extend([str(Path.cwd() / 'backend'), str(Path.cwd() / 'frontend')])
        from aqt.qt import QApplication, QImage, QMimeData
        from frontend.highlight_note_dialog import HighlightNoteDialog
        app = QApplication([])
        dialog = HighlightNoteDialog(None, title='Note', excerpt='', current_note='Caption')
        dialog.show()
        editor = dialog._editor
        image = QImage(200, 100, QImage.Format.Format_RGB32)
        image.fill(0xff409060)
        mime = QMimeData()
        mime.setImageData(image)
        editor.insertFromMimeData(mime)
        app.processEvents()
        assert dialog._image_alignment_controls.isVisible()
        assert dialog._image_alignment_buttons['center'].isChecked()
        centered = dialog.note_html()
        for alignment in ('left', 'center', 'right'):
            dialog._image_alignment_buttons[alignment].click()
            app.processEvents()
            assert dialog._image_alignment_buttons[alignment].isChecked()
            assert dialog._image_placement.currentData() == 'block'
            assert f'<p align="{alignment}"><img ' in dialog.note_html()
            rect = editor._image_rect()
            if alignment == 'left':
                assert rect.x() < 12
            elif alignment == 'right':
                assert rect.right() > editor.viewport().width() - 12
                assert abs(editor._image_handles['right'].geometry().center().x() - rect.left()) < 3
            else:
                assert abs(rect.center().x() - editor.viewport().width() / 2) < 12
            saved = dialog.note_html()
            reopened = HighlightNoteDialog(None, title='Note', excerpt='', current_note=dialog.note_text(), current_note_html=saved)
            assert reopened.note_html() == saved
            assert reopened._image_alignment_buttons[alignment].isChecked()
            assert reopened._image_placement.currentData() == 'block'
            reopened._write_around_image(above=True)
            assert f'<p align="{alignment}"><img ' in reopened.note_html(), 'Adding the first paragraph above an image must preserve alignment'
            reopened.close()
        dialog._image_alignment_buttons['left'].click()
        left_aligned = dialog.note_html()
        editor.undo()
        assert '<p align="right"><img ' in dialog.note_html()
        editor.redo()
        assert dialog.note_html() == left_aligned
        dialog._write_around_image(above=False)
        assert '<p align="left"><img ' in dialog.note_html(), 'Caption navigation must keep the chosen image alignment'
        editor.insertPlainText('New ')
        assert dialog.note_text() == 'New Caption'
        editor.setTextCursor(editor.document().find('\\ufffc'))
        dialog._image_placement.setCurrentIndex(dialog._image_placement.findData('inline'))
        app.processEvents()
        assert not dialog._image_alignment_controls.isVisible(), 'Own-line alignment belongs only to own-line images'
        dialog.close()
    ''')], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_modeless_annotation_editor_allows_reader_selection_and_keeps_failed_or_stale_drafts():
    result = subprocess.run([sys.executable, '-c', dedent('''
        import sys
        from pathlib import Path
        sys.path.extend([str(Path.cwd() / 'backend'), str(Path.cwd() / 'frontend')])
        from aqt.qt import QApplication, QPoint, QTextEdit, Qt
        from PyQt6.QtTest import QTest
        from frontend.highlight_note_dialog import HighlightNoteDialog
        app = QApplication([])
        reader = QTextEdit()
        reader.setPlainText('Original passage and more text to copy')
        reader.show()
        active = [True]
        writes = []
        failure = ['Cannot save yet']
        def save(dialog):
            if failure[0]:
                return failure[0]
            writes.append((dialog.note_text(), dialog.note_html()))
        key = ('synthetic', 'pdf', 7, 'h')
        dialog = HighlightNoteDialog.show_for_annotation(reader, key=key, title='Note', excerpt='Original passage',
            current_note='Original note', current_note_html='', is_current=lambda: active[0], save=save)
        app.processEvents()
        assert QApplication.activeModalWidget() is None
        assert dialog.windowModality() == Qt.WindowModality.NonModal
        assert reader.isEnabled()
        QTest.mouseDClick(reader.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(20, 10))
        assert reader.textCursor().selectedText() == 'Original', 'The underlying reader must accept real text-selection clicks'
        dialog._editor.setPlainText('Draft kept while browsing')
        reader.selectAll()
        assert reader.textCursor().selectedText() == 'Original passage and more text to copy'
        reopened = HighlightNoteDialog.show_for_annotation(reader, key=key, title='Note', excerpt='Original passage',
            current_note='Original note', current_note_html='', is_current=lambda: active[0], save=save)
        assert reopened is dialog and reopened.note_text() == 'Draft kept while browsing'
        active[0] = False
        dialog.accept()
        assert writes == [] and dialog.isVisible() and dialog._save_status.isVisible()
        assert dialog.note_text() == 'Draft kept while browsing'
        active[0] = True
        dialog.accept()
        assert writes == [] and dialog.isVisible() and dialog._save_status.text() == 'Cannot save yet'
        failure[0] = ''
        dialog.accept()
        assert writes[0][0] == 'Draft kept while browsing'
        assert not dialog.isVisible()
        again = HighlightNoteDialog.show_for_annotation(reader, key=key, title='Note', excerpt='Original passage',
            current_note='Saved note', current_note_html='', is_current=lambda: True, save=save)
        assert again is not dialog
        again._editor.setPlainText('Cancelled draft')
        again.reject()
        assert len(writes) == 1
        reader.close()
    ''')], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
