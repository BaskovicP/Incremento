from __future__ import annotations

from typing import Callable

from aqt import mw
from aqt.qt import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
    qconnect,
)
from aqt.utils import showInfo, tooltip

try:
    from aqt import dialogs
except Exception:
    dialogs = None

try:
    from ..backend.knowledge_tree import (
        NODE_KIND_TOPIC,
        build_subset_review_rows,
        get_card_metadata,
        normalize_node_kind,
    )
    from ..backend.knowledge_tree_postpone import SCOPE_CURRENT_BROWSER
    from .session_launcher import learnFunction
except ImportError:
    from knowledge_tree import (  # type: ignore
        NODE_KIND_TOPIC,
        build_subset_review_rows,
        get_card_metadata,
        normalize_node_kind,
    )
    from knowledge_tree_postpone import SCOPE_CURRENT_BROWSER  # type: ignore
    from session_launcher import learnFunction  # type: ignore

try:
    from .knowledge_tree_postpone_dialog import KnowledgeTreePostponeDialog
except ImportError:
    from knowledge_tree_postpone_dialog import KnowledgeTreePostponeDialog  # type: ignore


class _SortItem(QTableWidgetItem):
    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)
        a = self.data(Qt.ItemDataRole.UserRole)
        b = other.data(Qt.ItemDataRole.UserRole)
        if a is not None and b is not None:
            try:
                return a < b
            except Exception:
                pass
        return self.text().lower() < other.text().lower()


class KnowledgeTreeSubsetDialog(QDialog):
    _CARD_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 1
    _COLUMNS = [
        "#",
        "Title",
        "Kind",
        "Priority",
        "Interval",
        "Next Review",
        "Last Review",
        "Reps",
        "Lapses",
        "A-Factor",
        "Deck",
        "Note Type",
        "Card ID",
    ]

    def __init__(
        self,
        addon_dir: str,
        *,
        profile: str,
        root_card_id: int,
        reveal_in_tree: Callable[[int], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._profile = profile
        self._root_card_id = int(root_card_id)
        self._reveal_in_tree = reveal_in_tree
        self._all_rows: list[dict] = []
        self._visible_rows: list[dict] = []

        root_meta = get_card_metadata(
            self._root_card_id,
            addon_dir=self._addon_dir,
            profile=self._profile,
        ) or {}
        self._root_title = str(root_meta.get("title") or f"Card {self._root_card_id}")

        self.setWindowTitle(f"Subset Review — {self._root_title}")
        self.resize(1280, 760)
        self._apply_style()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        hero = QFrame(self)
        hero.setObjectName("SubsetSection")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(12, 12, 12, 12)
        hero_layout.setSpacing(6)

        title = QLabel("Subset Elements")
        title.setObjectName("SubsetTitle")
        hero_layout.addWidget(title)

        self._summary_label = QLabel("")
        self._summary_label.setObjectName("SubsetMeta")
        self._summary_label.setWordWrap(True)
        hero_layout.addWidget(self._summary_label)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(10)
        controls.addWidget(QLabel("Scope:"))
        self._scope_group = QButtonGroup(self)
        self._scope_subtree = QRadioButton("Whole subtree")
        self._scope_node_only = QRadioButton("Selected node only")
        self._scope_group.addButton(self._scope_subtree)
        self._scope_group.addButton(self._scope_node_only)
        self._scope_subtree.setChecked(True)
        controls.addWidget(self._scope_subtree)
        controls.addWidget(self._scope_node_only)
        controls.addSpacing(16)
        controls.addWidget(QLabel("Filter:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter by title, deck, or note type")
        controls.addWidget(self._filter_edit, 1)
        hero_layout.addLayout(controls)
        outer.addWidget(hero)

        self._table = QTableWidget(0, len(self._COLUMNS), self)
        self._table.setHorizontalHeaderLabels(self._COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        header = self._table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(11, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(12, QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self._table, 1)

        self._footer_label = QLabel("")
        self._footer_label.setObjectName("SubsetHint")
        self._footer_label.setWordWrap(True)
        outer.addWidget(self._footer_label)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self._browser_btn = QPushButton("Open In Browser")
        self._reveal_btn = QPushButton("Reveal In Tree")
        self._study_btn = QPushButton("Study Subset")
        self._postpone_btn = QPushButton("Postpone Subset")
        self._close_btn = QPushButton("Close")
        actions.addWidget(self._browser_btn)
        actions.addWidget(self._reveal_btn)
        actions.addStretch(1)
        actions.addWidget(self._study_btn)
        actions.addWidget(self._postpone_btn)
        actions.addWidget(self._close_btn)
        outer.addLayout(actions)

        qconnect(self._scope_subtree.toggled, lambda checked: self._reload_rows() if checked else None)
        qconnect(self._scope_node_only.toggled, lambda checked: self._reload_rows() if checked else None)
        qconnect(self._filter_edit.textChanged, lambda _text: self._apply_filter())
        qconnect(self._table.itemSelectionChanged, self._refresh_actions)
        qconnect(self._browser_btn.clicked, self._open_in_browser)
        qconnect(self._reveal_btn.clicked, self._reveal_selected_in_tree)
        qconnect(self._study_btn.clicked, self._study_subset)
        qconnect(self._postpone_btn.clicked, self._postpone_subset)
        qconnect(self._close_btn.clicked, self.accept)

        self._reload_rows()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QFrame#SubsetSection {
              background: palette(base);
              border: 1px solid rgba(128,128,128,0.20);
              border-radius: 10px;
            }
            QLabel#SubsetTitle {
              font-size: 16px;
              font-weight: 700;
            }
            QLabel#SubsetMeta {
              color: palette(text);
              font-size: 12px;
              font-weight: 500;
            }
            QLabel#SubsetHint {
              color: palette(text);
              font-size: 12px;
              font-weight: 500;
            }
            QTableWidget {
              border: 1px solid rgba(128,128,128,0.20);
              border-radius: 10px;
              alternate-background-color: rgba(128,128,128,0.05);
            }
            """
        )

    def _include_descendants(self) -> bool:
        return bool(self._scope_subtree.isChecked())

    def _reload_rows(self) -> None:
        self._all_rows = build_subset_review_rows(
            self._addon_dir,
            self._profile,
            self._root_card_id,
            include_descendants=self._include_descendants(),
        )
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._filter_edit.text().strip().lower()
        if not query:
            self._visible_rows = list(self._all_rows)
        else:
            self._visible_rows = [
                row
                for row in self._all_rows
                if query in str(row.get("title") or "").lower()
                or query in str(row.get("deck_name") or "").lower()
                or query in str(row.get("note_type_name") or "").lower()
                or query in str(row.get("node_kind") or "").lower()
            ]
        self._populate_table()

    def _set_cell(
        self,
        row_index: int,
        column: int,
        text: str,
        *,
        sort_key=None,
        card_id: int | None = None,
    ) -> None:
        item = _SortItem(text)
        item.setData(Qt.ItemDataRole.UserRole, sort_key)
        if card_id is not None:
            item.setData(self._CARD_ID_ROLE, int(card_id))
        self._table.setItem(row_index, column, item)

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._visible_rows))

        for row_index, row in enumerate(self._visible_rows):
            priority = row.get("priority")
            priority_text = "" if priority is None else f"{float(priority):.0f}"
            a_factor = row.get("a_factor")
            a_factor_text = "" if a_factor is None else f"{float(a_factor):.3f}".rstrip("0").rstrip(".")
            kind = "Topic" if normalize_node_kind(row.get("node_kind") or NODE_KIND_TOPIC) == NODE_KIND_TOPIC else "Item"

            self._set_cell(
                row_index,
                0,
                str(row.get("row_number") or row_index + 1),
                sort_key=int(row.get("tree_index") or row_index),
                card_id=int(row.get("card_id") or 0),
            )
            self._set_cell(
                row_index,
                1,
                str(row.get("display_title") or row.get("title") or ""),
                sort_key=str(row.get("title") or "").lower(),
            )
            self._set_cell(row_index, 2, kind, sort_key=kind)
            self._set_cell(row_index, 3, priority_text, sort_key=(float(priority) if priority is not None else 9999.0))
            self._set_cell(row_index, 4, str(int(row.get("interval") or 0)), sort_key=int(row.get("interval") or 0))
            self._set_cell(row_index, 5, str(row.get("next_review") or ""), sort_key=float(row.get("next_review_sort") or float("inf")))
            self._set_cell(row_index, 6, str(row.get("last_review") or ""), sort_key=float(row.get("last_review_sort") or float("-inf")))
            self._set_cell(row_index, 7, str(int(row.get("reps") or 0)), sort_key=int(row.get("reps") or 0))
            self._set_cell(row_index, 8, str(int(row.get("lapses") or 0)), sort_key=int(row.get("lapses") or 0))
            self._set_cell(row_index, 9, a_factor_text, sort_key=(float(a_factor) if a_factor is not None else 9999.0))
            self._set_cell(row_index, 10, str(row.get("deck_name") or ""), sort_key=str(row.get("deck_name") or "").lower())
            self._set_cell(row_index, 11, str(row.get("note_type_name") or ""), sort_key=str(row.get("note_type_name") or "").lower())
            self._set_cell(row_index, 12, str(int(row.get("card_id") or 0)), sort_key=int(row.get("card_id") or 0))

        self._table.setSortingEnabled(True)
        self._update_summary()
        self._refresh_actions()

    def _update_summary(self) -> None:
        total_rows = len(self._all_rows)
        visible_rows = len(self._visible_rows)
        scope_text = "whole subtree" if self._include_descendants() else "selected node only"
        self._summary_label.setText(
            f"{self._root_title} · {total_rows} card{'s' if total_rows != 1 else ''} in {scope_text}."
        )
        if visible_rows == total_rows:
            self._footer_label.setText(
                "Select one or more rows to study or postpone only that selection. "
                "If nothing is selected, actions operate on all visible rows."
            )
        else:
            self._footer_label.setText(
                f"Filter active: showing {visible_rows} of {total_rows} card"
                f"{'' if total_rows == 1 else 's'} in this subset."
            )

    def _selected_row_indexes(self) -> list[int]:
        selection_model = self._table.selectionModel()
        if selection_model is None:
            return []
        indexes = sorted({index.row() for index in selection_model.selectedRows()})
        return [index for index in indexes if 0 <= index < len(self._visible_rows)]

    def _card_id_for_table_row(self, row_index: int) -> int | None:
        item = self._table.item(row_index, 0)
        if item is None:
            return None
        value = item.data(self._CARD_ID_ROLE)
        return None if value is None else int(value)

    def _selected_card_ids(self) -> list[int]:
        card_ids: list[int] = []
        seen: set[int] = set()
        for index in self._selected_row_indexes():
            card_id = self._card_id_for_table_row(index)
            if card_id is None or card_id in seen:
                continue
            seen.add(card_id)
            card_ids.append(card_id)
        return card_ids

    def _visible_card_ids(self) -> list[int]:
        return [int(row["card_id"]) for row in self._visible_rows]

    def _active_card_ids(self) -> list[int]:
        selected = self._selected_card_ids()
        return selected if selected else self._visible_card_ids()

    def _refresh_actions(self) -> None:
        has_visible = bool(self._visible_rows)
        has_selection = bool(self._selected_row_indexes())
        self._browser_btn.setEnabled(has_selection)
        self._reveal_btn.setEnabled(has_selection and self._reveal_in_tree is not None)
        self._study_btn.setEnabled(has_visible)
        self._postpone_btn.setEnabled(has_visible)

    def _open_in_browser(self) -> None:
        card_ids = self._selected_card_ids()
        if not card_ids:
            return
        if dialogs is None or mw is None:
            showInfo("Could not open Anki Browser from the subset view.")
            return
        query = " OR ".join(f"cid:{card_id}" for card_id in card_ids)
        try:
            browser = dialogs.open("Browser", mw)
            browser.search_for(query)
        except Exception as exc:
            showInfo(f"Could not open the Browser for this subset:\n{exc}")

    def _reveal_selected_in_tree(self) -> None:
        if self._reveal_in_tree is None:
            return
        card_ids = self._selected_card_ids()
        if not card_ids:
            return
        try:
            self._reveal_in_tree(int(card_ids[0]))
            tooltip("Revealed the selected card in the knowledge tree.")
        except Exception as exc:
            showInfo(f"Could not reveal this card in the knowledge tree:\n{exc}")

    def _study_scope_title(self, card_ids: list[int]) -> str:
        if len(card_ids) == len(self._all_rows) and self._include_descendants():
            return self._root_title
        return f"{self._root_title} subset"

    def _study_subset(self) -> None:
        card_ids = self._active_card_ids()
        if not card_ids:
            showInfo("No cards are available in this subset.")
            return
        try:
            learnFunction(
                branch_scope={
                    "root_card_id": self._root_card_id,
                    "root_title": self._study_scope_title(card_ids),
                    "card_ids": list(card_ids),
                }
            )
        except Exception as exc:
            showInfo(f"Could not open the subset study session:\n{exc}")

    def _postpone_subset(self) -> None:
        card_ids = self._active_card_ids()
        if not card_ids:
            showInfo("No cards are available in this subset.")
            return
        dlg = KnowledgeTreePostponeDialog(
            self._addon_dir,
            profile=self._profile,
            branch_root_card_id=self._root_card_id,
            browser_card_ids=card_ids,
            browser_scope_name="Current subset",
            initial_scope=SCOPE_CURRENT_BROWSER,
            parent=self,
        )
        if dlg.exec():
            self._reload_rows()
