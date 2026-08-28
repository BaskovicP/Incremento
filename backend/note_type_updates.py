"""Explicit, non-mutating discovery of Incremento note-type updates.

Anki cannot merge some note-type schema changes during a normal sync.  This
module keeps detection separate from mutation so the UI can explain a pending
update and obtain the user's consent before touching the collection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class NoteTypeUpdateRequired(RuntimeError):
    """Raised when code tries to update an existing note type without consent."""


class NoteTypeApplyError(RuntimeError):
    """Report a failed explicit update and any types already saved before it."""

    def __init__(
        self,
        note_type: str,
        applied: tuple[str, ...],
        cause: Exception,
    ) -> None:
        self.note_type = str(note_type)
        self.applied = tuple(applied)
        self.cause = cause
        super().__init__(
            f"Could not update {self.note_type}: {cause}"
        )


@dataclass(frozen=True)
class NoteTypeSpec:
    name: str
    fields: tuple[str, ...]
    question_template: str
    answer_template: str
    normalize_field_ordinals: bool = False


@dataclass(frozen=True)
class PendingNoteTypeUpdate:
    note_type: str
    changes: tuple[str, ...]


def _model_fields(model: Any) -> list[dict]:
    try:
        fields = model.get("flds", [])
    except Exception:
        try:
            fields = model["flds"]
        except Exception:
            fields = []
    return fields if isinstance(fields, list) else []


def _model_templates(model: Any) -> list[dict]:
    try:
        templates = model.get("tmpls", [])
    except Exception:
        try:
            templates = model["tmpls"]
        except Exception:
            templates = []
    return templates if isinstance(templates, list) else []


def _field_ordinals_need_repair(fields: list[dict]) -> bool:
    seen: set[int] = set()
    for field in fields:
        if not isinstance(field, dict):
            return True
        ordinal = field.get("ord")
        if not isinstance(ordinal, int) or ordinal < 0 or ordinal in seen:
            return True
        seen.add(ordinal)
    return False


def inspect_note_type(model: Any, spec: NoteTypeSpec) -> tuple[str, ...]:
    """Return required changes without mutating the model or collection."""
    fields = _model_fields(model)
    existing_fields = {
        str(field.get("name") or "").strip()
        for field in fields
        if isinstance(field, dict)
    }
    missing = [field for field in spec.fields if field not in existing_fields]
    changes: list[str] = []
    if missing:
        changes.append("add fields: " + ", ".join(missing))

    if spec.normalize_field_ordinals and _field_ordinals_need_repair(fields):
        changes.append("repair field order")

    templates = _model_templates(model)
    if not templates or not isinstance(templates[0], dict):
        changes.append("restore the card template")
    else:
        template = templates[0]
        if (
            str(template.get("qfmt") or "") != spec.question_template
            or str(template.get("afmt") or "") != spec.answer_template
        ):
            changes.append("update the card template")
    return tuple(changes)


def ensure_note_type(
    col,
    spec: NoteTypeSpec,
    *,
    allow_existing_update: bool = False,
) -> bool:
    """Create a missing type, or update an existing type only with consent.

    Creating a type happens only from an explicit content-creation action.
    Existing types are never changed unless the migration coordinator passes
    ``allow_existing_update=True``.
    """
    models = col.models
    model = models.by_name(spec.name)
    if model is None:
        model = models.new(spec.name)
        for field_name in spec.fields:
            field = models.new_field(field_name)
            models.add_field(model, field)
        template = models.new_template("Card 1")
        template["qfmt"] = spec.question_template
        template["afmt"] = spec.answer_template
        models.add_template(model, template)
        models.add(model)
        return True

    changes = inspect_note_type(model, spec)
    if not changes:
        return False
    if not allow_existing_update:
        raise NoteTypeUpdateRequired(
            f"The {spec.name} card format needs an explicit Incremento update. "
            "Open Incremento > Utils > Card Format Updates before continuing."
        )

    fields = _model_fields(model)
    existing_fields = {
        str(field.get("name") or "").strip()
        for field in fields
        if isinstance(field, dict)
    }
    for field_name in spec.fields:
        if field_name in existing_fields:
            continue
        field = models.new_field(field_name)
        models.add_field(model, field)
        existing_fields.add(field_name)

    if spec.normalize_field_ordinals:
        for ordinal, field in enumerate(_model_fields(model)):
            if isinstance(field, dict):
                field["ord"] = ordinal

    templates = _model_templates(model)
    if not templates or not isinstance(templates[0], dict):
        template = models.new_template("Card 1")
        template["qfmt"] = spec.question_template
        template["afmt"] = spec.answer_template
        models.add_template(model, template)
    else:
        templates[0]["qfmt"] = spec.question_template
        templates[0]["afmt"] = spec.answer_template

    models.update_dict(model)
    return True


def incremento_note_type_specs() -> tuple[NoteTypeSpec, ...]:
    """Return all Incremento-owned note-type specifications lazily."""
    try:
        from . import epub_manager, local_file_manager, pdf_manager
        from . import video_manager, web_manager, writing_manager
    except ImportError:
        import epub_manager  # type: ignore
        import local_file_manager  # type: ignore
        import pdf_manager  # type: ignore
        import video_manager  # type: ignore
        import web_manager  # type: ignore
        import writing_manager  # type: ignore

    return (
        pdf_manager.pdf_note_type_spec(),
        epub_manager.epub_note_type_spec(),
        video_manager.video_note_type_spec(),
        web_manager.web_note_type_spec(),
        writing_manager.writing_note_type_spec(),
        local_file_manager.local_file_note_type_spec(),
    )


def detect_incremento_note_type_updates(col) -> tuple[PendingNoteTypeUpdate, ...]:
    """Inspect existing Incremento note types without creating or saving any."""
    pending: list[PendingNoteTypeUpdate] = []
    for spec in incremento_note_type_specs():
        model = col.models.by_name(spec.name)
        if model is None:
            # Do not create unused note types at startup.
            continue
        changes = inspect_note_type(model, spec)
        if changes:
            pending.append(PendingNoteTypeUpdate(spec.name, changes))
    return tuple(pending)


def apply_incremento_note_type_updates(
    col,
    updates: tuple[PendingNoteTypeUpdate, ...] | list[PendingNoteTypeUpdate],
) -> tuple[str, ...]:
    """Apply the exact currently pending types after explicit user consent."""
    requested = {str(update.note_type) for update in updates}
    applied: list[str] = []
    for spec in incremento_note_type_specs():
        if spec.name not in requested or col.models.by_name(spec.name) is None:
            continue
        try:
            changed = ensure_note_type(col, spec, allow_existing_update=True)
        except Exception as exc:
            raise NoteTypeApplyError(spec.name, tuple(applied), exc) from exc
        if changed:
            applied.append(spec.name)
    return tuple(applied)
