#!/usr/bin/env python3
"""List remaining Python UI literals for translation review.

This is a review inventory, not an automatic code rewrite: Qt labels can also
contain user data, stable note-type names or parser examples. Inspect those
before translating. Source references and catalog parity are enforced separately
by compile_i18n.py. In addition to direct arguments, the inventory follows simple
local assignments and literal tuple/list loops. It does not execute code or
attempt to trace arbitrary helpers, object attributes, or embedded JavaScript.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re
import json
import sys

FIRST_ARGUMENT = {
    'QAction', 'QMenu', 'QDockWidget', 'QToolBar', 'QLabel', 'QPushButton', 'QCheckBox', 'QRadioButton',
    'QGroupBox', 'setWindowTitle', 'setText', 'setToolTip', 'setStatusTip',
    'setPlaceholderText', 'setAccessibleName', 'setAccessibleDescription',
    'addItem', 'addRow', 'addMenu', 'addAction', 'showInfo', 'showWarning', 'tooltip', 'askUser', 'setSuffix',
    'setPrefix', 'setHeaderLabels', 'addItems',
    '_build_button', '_info_icon', '_info_button', '_set_status',
}
STABLE_LABELS = {'PDF', 'EPUB', 'PDF / EPUB', 'Incremento', 'URL', 'HTML', 'CSS', 'OCR', 'A-factor'}


class _LiteralInventory(ast.NodeVisitor):
    """Track only syntactically known label values within a lexical scope."""

    def __init__(self, source: str, filename: str):
        self.source = source
        self.filename = filename
        self.bindings: dict[str, list[ast.expr]] = {}
        self.rows: list[dict] = []

    def _values(self, expression: ast.expr) -> list[ast.expr]:
        if isinstance(expression, ast.Name):
            return self.bindings.get(expression.id, [])
        return [expression]

    def _bind(self, target: ast.expr, values: list[ast.expr]) -> None:
        if isinstance(target, ast.Name):
            self.bindings[target.id] = values
        elif isinstance(target, (ast.Tuple, ast.List)):
            for index, child in enumerate(target.elts):
                column = [
                    value
                    for row in values
                    if isinstance(row, (ast.Tuple, ast.List)) and len(row.elts) == len(target.elts)
                    for value in self._values(row.elts[index])
                ]
                self._bind(child, column)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        values = self._values(node.value)
        for target in node.targets:
            self._bind(target, values)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
            self._bind(node.target, self._values(node.value))

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.visit(node.args)
        for decorator in node.decorator_list:
            self.visit(decorator)
        if node.returns is not None:
            self.visit(node.returns)
        previous = self.bindings
        self.bindings = previous.copy()
        # Arguments are runtime data, even if a global has the same name.
        for argument in ast.walk(node.args):
            if isinstance(argument, ast.arg):
                self.bindings.pop(argument.arg, None)
        for statement in node.body:
            self.visit(statement)
        self.bindings = previous

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in [*node.bases, *node.keywords, *node.decorator_list]:
            self.visit(expression)
        previous = self.bindings
        self.bindings = previous.copy()
        for statement in node.body:
            self.visit(statement)
        self.bindings = previous

    def visit_For(self, node: ast.For | ast.AsyncFor) -> None:
        self.visit(node.iter)
        previous = self.bindings
        self.bindings = previous.copy()
        rows = [
            value
            for sequence in self._values(node.iter)
            if isinstance(sequence, (ast.Tuple, ast.List))
            for item in sequence.elts
            for value in self._values(item)
        ]
        self._bind(node.target, rows)
        for statement in node.body:
            self.visit(statement)
        self.bindings = previous
        for statement in node.orelse:
            self.visit(statement)

    visit_AsyncFor = visit_For

    def _text_values(self, expression: ast.expr, seen: frozenset[int] = frozenset()):
        if id(expression) in seen:
            return
        seen = seen | {id(expression)}
        for value in self._values(expression):
            if isinstance(value, (ast.Tuple, ast.List)):
                for child in value.elts:
                    yield from self._text_values(child, seen)
            elif isinstance(value, ast.Constant) and isinstance(value.value, str):
                yield value, value.value
            elif isinstance(value, ast.JoinedStr):
                yield value, ast.get_source_segment(self.source, value) or ''

    def visit_Call(self, node: ast.Call) -> None:
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
        arguments = node.args[:1] if name in FIRST_ARGUMENT else node.args[1:2] if name == 'addTab' else []
        owner = node.func.value.id if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) else ''
        if owner in {'QFileDialog', 'QInputDialog', 'QMessageBox'}:
            # Parent comes first, then title and prompt/default path/filter.
            arguments = node.args[1:]
        if name == '_confirm':
            arguments = node.args.copy()
        arguments += [kw.value for kw in node.keywords if kw.arg in {'title', 'label', 'text', 'message', 'tooltip_text', 'tip', 'empty_message'}]
        for argument in arguments:
            for value, text in self._text_values(argument):
                if text in STABLE_LABELS or not re.search(r'[A-Za-z]{2}', text):
                    continue
                self.rows.append({'file': self.filename, 'line': value.lineno, 'sink': name, 'text': text})
        self.generic_visit(node)


def inventory(root: Path) -> list[dict]:
    rows = []
    for path in [root / '__init__.py', *sorted((root / 'frontend').glob('*.py')), *sorted((root / 'backend').glob('*.py'))]:
        if not path.is_file():
            continue
        source = path.read_text(encoding='utf-8')
        visitor = _LiteralInventory(source, str(path.relative_to(root)))
        visitor.visit(ast.parse(source))
        rows.extend(visitor.rows)
    unique = {(row['file'], row['line'], row['sink'], row['text']): row for row in rows}
    return sorted(unique.values(), key=lambda row: (row['file'], row['line']))


def check_inventory(root: Path, exceptions: list[dict]) -> None:
    approved = {
        (row['file'], row['sink'], row['text'])
        for row in exceptions if str(row.get('reason', '')).strip()
    }
    unreviewed = [row for row in inventory(root) if (row['file'], row['sink'], row['text']) not in approved]
    if unreviewed:
        raise ValueError('Untranslated or unreviewed UI literals:\n' + '\n'.join(
            f"{row['file']}:{row['line']}: {row['text']!r}" for row in unreviewed
        ))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--check', action='store_true', help='Reject UI literals without a documented exact-text exemption.')
    args = parser.parse_args()
    if args.check:
        exceptions = json.loads((args.repo_root / 'scripts/i18n_literal_exceptions.json').read_text(encoding='utf-8'))
        try:
            check_inventory(args.repo_root, exceptions)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        print('All inspected UI literals are translated or explicitly classified.')
        return
    rows = inventory(args.repo_root)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"{row['file']}:{row['line']}: {row['text']!r}")
        print(f'{len(rows)} UI literals require review.')


if __name__ == '__main__':
    main()
