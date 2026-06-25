from __future__ import annotations

try:
    from .note_metadata import visible_field_names
except ImportError:
    from note_metadata import visible_field_names  # type: ignore


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
    visible_values = visible_note_field_values(note)
    if not visible_values:
        return {}
    text = str(selected_text or "")
    if not text:
        return visible_values
    first_field_name = next(iter(visible_values.keys()))
    return {first_field_name: text}


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
            "Extract lineage is added to the knowledge tree automatically. "
            "New extract cards are placed beneath their source parent when available."
        ),
    }


def parse_batch_qa_text(raw_text: str) -> list[dict[str, object]]:
    normalized = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = []
    current: list[str] = []
    for line in normalized.split("\n"):
        if not line.strip():
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)

    return [_parse_batch_qa_block(block) for block in blocks]


def _parse_batch_qa_block(lines: list[str]) -> dict[str, object]:
    question_lines: list[str] = []
    answer_lines: list[str] = []
    started_answer = False

    if not lines:
        return _invalid_batch_qa_row("", "", "Missing Q: line.")

    first_line = str(lines[0] or "")
    if not first_line.lstrip().startswith("Q:"):
        return _invalid_batch_qa_row("", "", "Block must start with Q:.")

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
        return _invalid_batch_qa_row(question, "", "Missing A: line.")
    if not question:
        return _invalid_batch_qa_row("", answer, "Question is empty.")
    if not answer:
        return _invalid_batch_qa_row(question, "", "Answer is empty.")
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
        "error": str(error or "").strip() or "Invalid Q/A block.",
    }
