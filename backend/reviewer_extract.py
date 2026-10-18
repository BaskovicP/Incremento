from __future__ import annotations
try:
    from .i18n import t
except ImportError:
    from backend.i18n import t


try:
    from .note_metadata import (
        INCREMENTO_METADATA_FIELDS, INCREMENTO_SOURCE_LINK_FIELD,
        is_extract_source_field, is_source_url_field, visible_field_names,
    )
except ImportError:
    from note_metadata import (  # type: ignore
        INCREMENTO_METADATA_FIELDS, INCREMENTO_SOURCE_LINK_FIELD,
        is_extract_source_field, is_source_url_field, visible_field_names,
    )


def visible_note_field_values(note) -> dict[str, str]:
    note_type = note.note_type() or {}
    visible_fields = visible_field_names(
        [field.get("name") for field in list(note_type.get("flds") or [])]
    )
    values: dict[str, str] = {}
    for field_name in visible_fields:
        try:
            values[field_name] = str(note[field_name] or "")
        except Exception:
            values[field_name] = ""
    return values


def initial_extract_field_values(note, selected_text: str) -> dict[str, str]:
    """Keep content empty while retaining the current topic's source fields."""
    return {
        name: value for name, value in visible_note_field_values(note).items()
        if is_extract_source_field(name)
    }


def extract_source_field_values(
    note, metadata: dict | None, source_field_values: dict | None = None,
) -> dict[str, str]:
    """Project provenance into existing draft fields without changing note types."""
    metadata = metadata or {}
    source_fields = {
        str(name).strip().casefold(): str(value or "")
        for name, value in dict(source_field_values or {}).items()
        if is_extract_source_field(name)
    }
    values = {}
    for field in list((note.note_type() or {}).get("flds") or []):
        name = str((field or {}).get("name") or "")
        if name in INCREMENTO_METADATA_FIELDS:
            values[name] = str(metadata.get(name) or "")
        elif is_extract_source_field(name):
            # Preserve rich Source/Sources citations rather than replacing their
            # titles, multiple links and formatting with the canonical plain URL.
            source_value = source_fields.get(name.strip().casefold())
            if not source_value:
                source_value = next((
                    value for source_name, value in source_fields.items()
                    if value and is_source_url_field(source_name) == is_source_url_field(name)
                ), "")
            values[name] = source_value or str(metadata.get(INCREMENTO_SOURCE_LINK_FIELD) or "")
    return values


def has_extract_content(note) -> bool:
    return any(
        value.strip() for name, value in visible_note_field_values(note).items()
        if not is_extract_source_field(name)
    )


def extract_default_notetype_name(
    *,
    selected_text: str,
    configured_notetype: str,
    parent_notetype: str,
    available_notetype_names: list[str],
) -> str:
    if not str(selected_text or "").strip():
        return str(parent_notetype or "").strip()
    candidate = str(configured_notetype or "").strip()
    if candidate and candidate in list(available_notetype_names or []):
        return candidate
    return str(parent_notetype or "").strip()


def knowledge_tree_link_state(parent_in_tree: bool) -> dict[str, object]:
    return {
        "enabled": False,
        "checked": True,
        "tooltip": (
            t('backend_extract_tree_help')
        ),
    }


def parse_batch_qa_text(raw_text: str) -> list[dict[str, object]]:
    normalized = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    has_labels = any(
        line.lstrip().startswith(("Q:", "A:"))
        for line in lines
        if line.strip()
    )
    if not has_labels:
        values = [line.strip() for line in lines if line.strip()]
        rows: list[dict[str, object]] = []
        for index in range(0, len(values), 2):
            question = values[index]
            if index + 1 >= len(values):
                rows.append(
                    _invalid_batch_qa_row(
                        question,
                        "",
                        t("backend_extract_missing_answer_line"),
                    )
                )
                continue
            rows.append(
                {
                    "question": question,
                    "answer": values[index + 1],
                    "valid": True,
                    "error": "",
                }
            )
        return rows

    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if not line.strip():
            if current:
                blocks.append(current)
                current = []
            continue
        if line.lstrip().startswith("Q:") and current:
            blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)

    return [_parse_batch_qa_block(block) for block in blocks]


def _parse_batch_qa_block(lines: list[str]) -> dict[str, object]:
    question_lines: list[str] = []
    answer_lines: list[str] = []
    started_answer = False

    if not lines:
        return _invalid_batch_qa_row("", "", t('backend_extract_missing_question'))

    first_line = str(lines[0] or "")
    if not first_line.lstrip().startswith("Q:"):
        return _invalid_batch_qa_row("", "", t('backend_extract_question_first'))

    for index, raw_line in enumerate(lines):
        line = str(raw_line or "")
        if index == 0:
            question_lines.append(line.split("Q:", 1)[1])
            continue
        if not started_answer and line.lstrip().startswith("A:"):
            started_answer = True
            answer_lines.append(line.split("A:", 1)[1])
            continue
        if started_answer:
            answer_lines.append(line)
        else:
            question_lines.append(line)

    question = "\n".join(question_lines).strip()
    answer = "\n".join(answer_lines).strip()
    if not started_answer:
        return _invalid_batch_qa_row(question, "", t('backend_extract_missing_answer'))
    if not question:
        return _invalid_batch_qa_row("", answer, t('backend_extract_question_empty'))
    if not answer:
        return _invalid_batch_qa_row(question, "", t('backend_extract_answer_empty'))
    return {
        "question": question,
        "answer": answer,
        "valid": True,
        "error": "",
    }


def _invalid_batch_qa_row(question: str, answer: str, error: str) -> dict[str, object]:
    return {
        "question": str(question or "").strip(),
        "answer": str(answer or "").strip(),
        "valid": False,
        "error": str(error or "").strip() or t('backend_extract_invalid_block'),
    }
