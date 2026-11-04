"""Small per-reader coverage adapter; all supplemental writes run in a worker."""
import re

try:
    from ..backend.reader_coverage import record_coverage, coverage_summary
    from ..backend.i18n import t
except ImportError:
    from backend.reader_coverage import record_coverage, coverage_summary
    from backend.i18n import t


class CoverageTracker:
    def __init__(self, addon_dir, profile, kind, card_id, filename, *, run, current, visible, reply, lengths=()):
        self.args = (addon_dir, profile, kind, card_id, filename)
        self.run, self.current, self.visible, self.reply = run, current, visible, reply
        self.lengths = tuple(lengths)
        self.total = 0
        self.pending, self.seen = [], {}
        self.running = False
        self.latest = None
        self.refresh_pending = False

    def receive(self, data, *, mode='view'):
        if (not self.current() or not self.visible() or not isinstance(data, dict)
                or type(data.get('cardId')) is not int or data['cardId'] != self.args[3]
                or mode not in ('view', 'mark', 'unmark')):
            return False
        position, start, end = (data.get(key) for key in ('position', 'start', 'end'))
        if any(type(n) is not int for n in (position, start, end)):
            return False
        if self.args[2] == 'pdf':
            total = data.get('totalPages', self.total)
            if type(total) is not int or not 1 <= total <= 1_000_000 or position != 0:
                return False
            self.total, maximum = total, total
        else:
            if not 0 <= position < len(self.lengths):
                return False
            maximum = max(1, self.lengths[position])
        if not 0 <= start < end <= maximum or len(self.pending) >= 1024:
            return False
        if mode == 'view' and any(lo <= start and hi >= end for lo, hi in self.seen.get(position, [])):
            if self.latest is not None:
                self.reply(self.latest)
            return True
        if mode == 'view':
            try:
                from ..backend.reader_coverage import merge_ranges
            except ImportError:
                from backend.reader_coverage import merge_ranges
            self.seen[position] = merge_ranges([*self.seen.get(position, []), [start, end]])
        self.pending.append(dict(position=position, start=start, end=end, marked=mode == 'mark', remove=mode == 'unmark'))
        self._dispatch()
        return True

    def refresh(self):
        self.refresh_pending = True
        self._dispatch()

    def _dispatch(self):
        if self.running or (not self.pending and not self.refresh_pending) or not self.current():
            return
        batch, self.pending, self.running = self.pending, [], True
        self.refresh_pending = False
        total = self.total
        def work():
            for sample in batch:
                record_coverage(*self.args, **sample)
            return coverage_summary(*self.args, total=total, lengths=self.lengths)
        def done(future):
            self.running = False
            if not self.current():
                return
            try:
                result = future.result()
            except Exception:
                self.seen.clear()
                self.reply({'error': True})
            else:
                self.latest = result
                self.reply(result)
            self._dispatch()
        try:
            self.run(work, done, uses_collection=False)
        except Exception:
            self.running = False
            self.seen.clear()


def install_pdf_tracker(owner, addon_dir, profile, card_id, filename, *, mw, current, view):
    run = getattr(getattr(mw, 'taskman', None), 'run_in_background', None)
    if run is None:
        return None
    args = (addon_dir, profile, 'pdf', card_id, filename)
    previous = getattr(owner, '_coverage_tracker', None)
    if previous is not None and previous.args == args and previous.current():
        previous.refresh()
        return previous
    def reply(value):
        import json
        view.page().runJavaScript('window.incrementoReceiveCoverage?.(' + json.dumps(value) + ');')
    tracker = CoverageTracker(*args, run=run, current=current,
                              visible=lambda: view.isVisible(), reply=reply)
    owner._coverage_tracker = tracker
    return tracker


def install_epub_tracker(owner, addon_dir, profile, card_id, filename, *, mw, current, view, lengths):
    run = getattr(getattr(mw, 'taskman', None), 'run_in_background', None)
    if run is None:
        return None
    args = (addon_dir, profile, 'epub', card_id, filename)
    previous = getattr(owner, '_coverage_tracker', None)
    if previous is not None and previous.args == args and previous.lengths == tuple(lengths) and previous.current():
        previous.refresh()
        return previous
    def reply(value):
        label = getattr(owner, '_coverage_label', None)
        if label is not None:
            label.setText(coverage_label(value))
            label.show()
    tracker = CoverageTracker(*args, run=run, current=current,
        visible=lambda: view.isVisible(), reply=reply, lengths=lengths)
    owner._coverage_tracker = tracker
    return tracker


def coverage_label(summary):
    if summary.get('error'):
        return t('reader_coverage_unavailable')
    def percent(key):
        value = summary.get(key)
        return f'{float(value):.1f}'.rstrip('0').rstrip('.') if value is not None else '—'
    return t('reader_coverage_summary', viewed=percent('viewed_percent'), marked=percent('marked_percent'))


def add_coverage_actions(menu, tracker, location, *, owner=None, current=lambda: True):
    if tracker is None:
        return
    def send(mode, **sample):
        if current():
            tracker.receive({'cardId': tracker.args[3], **sample}, mode=mode)
    if tracker.args[2] == 'pdf':
        page = location['page']
        for label, mode in (('reader_mark_page_read', 'mark'), ('reader_mark_page_unread', 'unmark')):
            menu.addAction(t(label)).triggered.connect(
                lambda checked=False, mode=mode: send(mode, position=0, start=page - 1, end=page))
        def mark_range():
            if not current() or not tracker.total:
                return
            from aqt.qt import QInputDialog
            text, accepted = QInputDialog.getText(owner, t('reader_mark_range_read'), t('reader_page_range_prompt'), text=str(page))
            match = re.fullmatch(r'\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*', text) if accepted else None
            if match:
                start, end = int(match[1]), int(match[2] or match[1])
                if 1 <= start <= end <= tracker.total:
                    send('mark', position=0, start=start - 1, end=end)
        menu.addAction(t('reader_mark_range_read')).triggered.connect(mark_range)
    else:
        section = location['section']
        passage = location.get('readRange') or location.get('coverage') or location.get('passage') or {}
        start, end = passage.get('start'), passage.get('end')
        if type(start) is int and type(end) is int and start < end:
            for label, mode in (('reader_mark_passage_read', 'mark'), ('reader_mark_passage_unread', 'unmark')):
                menu.addAction(t(label)).triggered.connect(lambda checked=False, mode=mode:
                    send(mode, position=section, start=start, end=end))
        if 0 <= section < len(tracker.lengths):
            menu.addAction(t('reader_mark_section_read')).triggered.connect(lambda checked=False:
                send('mark', position=section, start=0, end=max(1, tracker.lengths[section])))
