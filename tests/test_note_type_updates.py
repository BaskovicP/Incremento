import copy

import note_type_updates as ntu


class _Models:
    def __init__(self, models=None):
        self._models = dict(models or {})
        self.updated = []
        self.added = []

    def by_name(self, name):
        return self._models.get(name)

    def new(self, name):
        return {"name": name, "flds": [], "tmpls": []}

    def new_field(self, name):
        return {"name": name, "ord": None}

    def add_field(self, model, field):
        field["ord"] = len(model["flds"])
        model["flds"].append(field)

    def new_template(self, name):
        return {"name": name, "qfmt": "", "afmt": ""}

    def add_template(self, model, template):
        model["tmpls"].append(template)

    def add(self, model):
        self._models[model["name"]] = model
        self.added.append(model["name"])

    def update_dict(self, model):
        self.updated.append(model["name"])


class _Collection:
    def __init__(self, models=None):
        self.models = _Models(models)


def _spec():
    return ntu.NoteTypeSpec(
        name="Incremento Example",
        fields=("Title", "Source"),
        question_template="{{Title}}",
        answer_template="{{Source}}",
        normalize_field_ordinals=True,
    )


def test_inspection_reports_changes_without_mutating_model():
    model = {
        "name": "Incremento Example",
        "flds": [{"name": "Title", "ord": None}],
        "tmpls": [{"qfmt": "old", "afmt": "old"}],
    }
    original = copy.deepcopy(model)

    changes = ntu.inspect_note_type(model, _spec())

    assert changes == (
        "add fields: Source",
        "repair field order",
        "update the card template",
    )
    assert model == original


def test_existing_note_type_refuses_implicit_schema_update():
    model = {
        "name": "Incremento Example",
        "flds": [{"name": "Title", "ord": 0}],
        "tmpls": [{"qfmt": "old", "afmt": "old"}],
    }
    col = _Collection({"Incremento Example": model})

    try:
        ntu.ensure_note_type(col, _spec())
    except ntu.NoteTypeUpdateRequired as exc:
        assert "Card Format Updates" in str(exc)
    else:
        raise AssertionError("implicit schema update was not rejected")

    assert col.models.updated == []
    assert model["tmpls"][0]["qfmt"] == "old"


def test_explicit_consent_applies_fields_template_and_ordinals():
    model = {
        "name": "Incremento Example",
        "flds": [{"name": "Title", "ord": None}],
        "tmpls": [{"qfmt": "old", "afmt": "old"}],
    }
    col = _Collection({"Incremento Example": model})

    changed = ntu.ensure_note_type(col, _spec(), allow_existing_update=True)

    assert changed is True
    assert [field["name"] for field in model["flds"]] == ["Title", "Source"]
    assert [field["ord"] for field in model["flds"]] == [0, 1]
    assert model["tmpls"][0] == {"qfmt": "{{Title}}", "afmt": "{{Source}}"}
    assert col.models.updated == ["Incremento Example"]


def test_missing_note_type_is_created_only_when_explicit_feature_uses_it():
    col = _Collection()

    changed = ntu.ensure_note_type(col, _spec())

    assert changed is True
    assert col.models.added == ["Incremento Example"]
    assert ntu.inspect_note_type(
        col.models.by_name("Incremento Example"), _spec()
    ) == ()


def test_detector_skips_absent_types_and_does_not_save(monkeypatch):
    stale = {
        "name": "Incremento Example",
        "flds": [{"name": "Title", "ord": 0}],
        "tmpls": [{"qfmt": "old", "afmt": "old"}],
    }
    absent = ntu.NoteTypeSpec("Unused", ("Title",), "front", "back")
    monkeypatch.setattr(ntu, "incremento_note_type_specs", lambda: (_spec(), absent))
    col = _Collection({"Incremento Example": stale})

    pending = ntu.detect_incremento_note_type_updates(col)

    assert pending == (
        ntu.PendingNoteTypeUpdate(
            "Incremento Example",
            ("add fields: Source", "update the card template"),
        ),
    )
    assert col.models.updated == []
    assert col.models.added == []


def test_apply_updates_changes_only_approved_existing_types(monkeypatch):
    model = {
        "name": "Incremento Example",
        "flds": [{"name": "Title", "ord": 0}],
        "tmpls": [{"qfmt": "old", "afmt": "old"}],
    }
    monkeypatch.setattr(ntu, "incremento_note_type_specs", lambda: (_spec(),))
    col = _Collection({"Incremento Example": model})
    pending = ntu.detect_incremento_note_type_updates(col)

    applied = ntu.apply_incremento_note_type_updates(col, pending)

    assert applied == ("Incremento Example",)
    assert col.models.updated == ["Incremento Example"]


def test_apply_error_reports_types_saved_before_failure(monkeypatch):
    first_spec = _spec()
    second_spec = ntu.NoteTypeSpec(
        "Incremento Broken",
        ("Title", "Source"),
        "{{Title}}",
        "{{Source}}",
    )
    models = {
        spec.name: {
            "name": spec.name,
            "flds": [{"name": "Title", "ord": 0}],
            "tmpls": [{"qfmt": "old", "afmt": "old"}],
        }
        for spec in (first_spec, second_spec)
    }
    col = _Collection(models)
    original_update = col.models.update_dict

    def fail_second(model):
        if model["name"] == second_spec.name:
            raise RuntimeError("save failed")
        original_update(model)

    col.models.update_dict = fail_second
    monkeypatch.setattr(
        ntu,
        "incremento_note_type_specs",
        lambda: (first_spec, second_spec),
    )
    pending = ntu.detect_incremento_note_type_updates(col)

    try:
        ntu.apply_incremento_note_type_updates(col, pending)
    except ntu.NoteTypeApplyError as exc:
        assert exc.note_type == "Incremento Broken"
        assert exc.applied == ("Incremento Example",)
        assert isinstance(exc.cause, RuntimeError)
    else:
        raise AssertionError("partial apply failure was not reported")


def test_shipped_specs_do_not_require_internal_content_id_field():
    specs = ntu.incremento_note_type_specs()

    assert {spec.name for spec in specs} == {
        "Incremento PDF",
        "Incremento EPUB",
        "Incremento Video",
        "Incremento Web",
        "Incremento Writing",
        "Incremento Local File",
    }
    assert all("Incremento_Content_ID" not in spec.fields for spec in specs)
