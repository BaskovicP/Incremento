"""End-to-end check of shared-folder sync with two Anki collections and real AnkiWeb.

Developer tooling (docs/architecture/shared-folder-sync.md §9). It demonstrates
the sync scenarios with Anki's own sync code, two separate Incremento profile
folders and one shared folder standing in for a cloud-synced folder.

Use a disposable AnkiWeb account only: the first sync uploads a fresh test
collection and replaces whatever that account holds. Credentials are read from
INC_E2E_USER and INC_E2E_PASS and never written to disk; only AnkiWeb's session
key is kept between device-B steps, inside the work directory.

    INC_E2E_USER=... INC_E2E_PASS=... python scripts/sync_e2e.py two-devices \
        --workdir /tmp/inc-e2e --overwrite-ankiweb

    # Device B in a second Python, e.g. Linux under WSL (from Windows):
    python scripts/sync_e2e.py cross-platform --workdir C:/tmp/inc-e2e --overwrite-ankiweb \
        --b-python "~/venv/bin/python" --b-state "~/inc-e2e-b" --wsl

The second Python needs the anki and PyMuPDF packages. Exit status 0 means
every check passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RECT = {"x": 72.0, "y": 72.0, "w": 200.0, "h": 14.0}
MARKER = ".incremento-sync-e2e"


def fresh_directory(path: Path) -> None:
    """Empty ``path`` for a new run, but only if it is empty or was made by this script."""
    if path.exists():
        if any(path.iterdir()) and not (path / MARKER).is_file():
            raise SystemExit(f"{path} is not empty and was not created by this script; choose another directory.")
        shutil.rmtree(path)
    path.mkdir(parents=True)
    (path / MARKER).write_text("Created by scripts/sync_e2e.py; safe to delete.\n", encoding="utf-8")


def _load_backend():
    """Import Anki, PyMuPDF and the backend modules (PyMuPDF first: backend/statistics.py shadows the stdlib)."""
    import pymupdf  # noqa: F401

    sys.path.insert(0, str(REPO / "backend"))
    import db
    import paths
    import pdf_annotations
    import sync_service
    from anki import sync_pb2
    from anki.collection import Collection
    return db, paths, pdf_annotations, sync_service, sync_pb2, Collection


def _credentials() -> tuple[str, str]:
    user, password = os.environ.get("INC_E2E_USER"), os.environ.get("INC_E2E_PASS")
    if not user or not password:
        raise SystemExit("Set INC_E2E_USER and INC_E2E_PASS for a disposable AnkiWeb account.")
    return user, password


def _checked_workdir(path: str) -> Path:
    workdir = Path(path).expanduser().resolve()
    if workdir == REPO or REPO in workdir.parents:
        raise SystemExit("Use a work directory outside the repository.")
    return workdir


class Checks:
    def __init__(self):
        self.results: list[tuple[str, bool]] = []

    def __call__(self, label: str, condition: object, detail: str = "") -> None:
        self.results.append((label, bool(condition)))
        print(("PASS " if condition else "FAIL ") + label + (f"  [{detail}]" if detail else ""), flush=True)

    def finish(self) -> int:
        failed = [label for label, ok in self.results if not ok]
        print(f"\n{len(self.results) - len(failed)}/{len(self.results)} checks passed")
        return 1 if failed else 0


class Device:
    """One Anki collection with its own Incremento profile folder, in this process."""

    def __init__(self, modules, name: str, workdir: Path, credentials: tuple[str, str]):
        self.db, self.paths, self.pdf_annotations, self.service, sync_pb2, collection = modules
        self.required = sync_pb2.SyncCollectionResponse.ChangesRequired
        self.names = {value: name for name, value in self.required.items()}
        directory = workdir / name
        directory.mkdir(parents=True)
        self.addon, self.profile = str(directory / "addon"), "P"
        self.col = collection(str(directory / "collection.anki2"))
        self.credentials = credentials
        self.auth = None

    def ankiweb(self, prefer_upload: bool) -> str:
        if self.auth is None:
            self.auth = self.col.sync_login(*self.credentials, None)
        out = self.col.sync_collection(self.auth, False)
        if out.new_endpoint:
            self.auth.endpoint = out.new_endpoint
        required = out.required
        if required in (self.required.FULL_SYNC, self.required.FULL_UPLOAD, self.required.FULL_DOWNLOAD):
            upload = required == self.required.FULL_UPLOAD or (required == self.required.FULL_SYNC and prefer_upload)
            self.col.close_for_full_sync()
            self.col.full_upload_or_download(auth=self.auth, server_usn=out.server_media_usn, upload=upload)
            self.col.reopen(after_full_sync=True)
            return f"{self.names[required]}->{'upload' if upload else 'download'}"
        return self.names[required]

    def scalar(self, sql: str, *args):
        return self.col.db.scalar(sql, *args)

    @property
    def conn(self):
        return self.db.get_connection(self.addon, self.profile)

    def inc(self):
        return self.service.sync_now(self.addon, self.profile, self.col.db.all)

    def set_priority(self, card: int, value: float) -> None:
        with self.conn as conn:
            conn.execute("INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)", (card, value))

    def priority(self, card: int):
        row = self.conn.execute("SELECT priority FROM priorities WHERE card_id=?", (card,)).fetchone()
        return None if row is None else row[0]

    def inbox(self, card: int) -> list[str]:
        return [row[0] for row in self.conn.execute(
            "SELECT i.status FROM sync_inbox i JOIN sync_revisions r ON r.id=i.revision_id "
            "WHERE r.key LIKE ? ORDER BY r.seq", (f"card:{card}%",))]

    def add_note(self, front: str):
        note = self.col.new_note(self.col.models.by_name("Basic"))
        note["Front"], note["Back"] = front, "answer"
        self.col.add_note(note, self.col.decks.id("Default"))
        return note, note.card_ids()[0]

    def change_schema(self, field: str) -> None:
        model = self.col.models.by_name("Basic")
        self.col.models.add_field(model, self.col.models.new_field(field))
        self.col.models.update_dict(model)

    def add_annotated_pdf(self, card: int, note_id: int, content_id: str):
        import pymupdf

        pdf = self.paths.get_pdf_dir(self.addon, self.profile) / "book.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        with pymupdf.open() as document:
            document.new_page().insert_text((72, 82), "A passage worth remembering.")
            document.save(pdf)
        with self.conn as conn:
            conn.execute("INSERT INTO content_items(content_id, kind, card_id, note_id, storage_key, created_at, "
                         "updated_at) VALUES (?, 'pdf', ?, ?, 'pdfs/book.pdf', 1, 1)", (content_id, card, note_id))
            conn.execute("INSERT INTO pdf_highlights(id, card_id, page, color, text, note, rects, annotation_json, "
                         "note_html) VALUES ('h1', ?, 1, 'yellow', 'A passage', 'key idea', ?, '{}', '')",
                         (card, json.dumps([RECT])))
        self.pdf_annotations.sync_pdf_annotations(self.addon, self.profile, card, "book.pdf")
        return pdf

    def read_pdf(self, card: int) -> dict:
        import pymupdf

        pdf = self.paths.get_pdf_dir(self.addon, self.profile) / "book.pdf"
        if not pdf.is_file():
            return {"exists": False}
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        self.pdf_annotations.sync_pdf_annotations(self.addon, self.profile, card, "book.pdf")
        with pymupdf.open(pdf) as document:
            native = sum(1 for page in document for _ in page.annots())
        notes = [row[0] for row in self.conn.execute("SELECT note FROM pdf_highlights WHERE card_id=?", (card,))]
        return {"exists": True, "sha": sha, "native": native, "notes": notes}

    def add_reading_state(self, card: int) -> None:
        with self.conn as conn:
            conn.execute("UPDATE pdf_progress SET page=7, read_page=6, zoom=0.8 WHERE card_id=?", (card,))
            conn.execute("INSERT INTO reader_bookmarks(id, card_id, reader_type, label, comment_text, location_json, "
                         "created_at, updated_at) VALUES ('bm1', ?, 'pdf', 'Page 7', 'come back', '{\"page\": 7}', "
                         "5, 5)", (card,))

    def set_zoom(self, card: int, zoom: float) -> None:
        with self.conn as conn:
            conn.execute("INSERT OR REPLACE INTO pdf_progress(card_id, page, zoom) VALUES (?, 1, ?)", (card, zoom))

    def reading_state(self, card: int) -> dict:
        row = self.conn.execute("SELECT page, read_page, zoom FROM pdf_progress WHERE card_id=?", (card,)).fetchone()
        bookmark = self.conn.execute("SELECT comment_text FROM reader_bookmarks WHERE card_id=?", (card,)).fetchone()
        return {"position": list(row) if row else None, "bookmark": bookmark[0] if bookmark else None}

    def resolve_theirs(self) -> int:
        conflicts = self.service.open_conflicts(self.addon, self.profile)
        for conflict in conflicts:
            theirs = next(v for i, v in enumerate(conflict.values) if i != conflict.local_index)
            self.service.resolve(self.addon, self.profile, conflict.id, theirs, self.col.db.all)
        return len(conflicts)

    def close(self) -> None:
        self.col.close()
        self.db.close_connection()


# --- Two devices in one process ------------------------------------------------------

def two_devices(workdir: Path) -> int:
    modules = _load_backend()
    credentials = _credentials()
    folder = workdir / "CloudFolder"
    folder.mkdir(parents=True)
    a, b = Device(modules, "A", workdir, credentials), Device(modules, "B", workdir, credentials)
    service = a.service
    check = Checks()

    notes = [a.add_note(f"q{i}") for i in range(3)]
    c1, c2, c3 = (card for _, card in notes)
    print("A first AnkiWeb sync:", a.ankiweb(True))
    print("B first AnkiWeb sync:", b.ankiweb(False))
    check("setup: B has A's cards", b.scalar("select count() from cards") == 3)
    service.configure(a.addon, a.profile, str(folder))
    service.configure(b.addon, b.profile, str(folder))

    a.set_priority(c1, 25.0)
    a.inc()
    b.inc()
    check("S1 a priority set on A reaches B", b.priority(c1) == 25.0, f"B={b.priority(c1)}")

    _, c4 = a.add_note("q4")
    a.set_priority(c4, 33.0)
    a.inc()
    b.inc()
    check("S2 data before its card waits on B", b.inbox(c4) == ["pending_anki"], str(b.inbox(c4)))
    a.ankiweb(True)
    a.inc()
    b.inc()
    check("S2 still waits while B has not synced AnkiWeb", b.inbox(c4) == ["pending_anki"], str(b.inbox(c4)))
    b.ankiweb(False)
    b.inc()
    check("S2 applies after B's AnkiWeb sync", b.priority(c4) == 33.0, f"{b.inbox(c4)} B={b.priority(c4)}")

    note5, c5 = a.add_note("q5")
    a.ankiweb(True)
    a.set_priority(c5, 44.0)
    a.inc()
    a.col.remove_notes([note5.id])
    a.ankiweb(True)
    a.inc()
    b.ankiweb(False)
    b.inc()
    check("S3 data for a card deleted before B synced is obsolete", b.inbox(c5) == ["obsolete"]
          and b.priority(c5) is None, str(b.inbox(c5)))

    a.set_priority(c1, 10.0)
    b.set_priority(c1, 90.0)
    a.inc()
    report = b.inc()
    check("S4 concurrent edits become one conflict, keeping B's value",
          len(service.open_conflicts(b.addon, b.profile)) == 1 and b.priority(c1) == 90.0,
          f"conflicts={report.conflicts}")
    b.resolve_theirs()
    b.inc()
    a.inc()
    check("S4 after resolving on B both agree", a.priority(c1) == b.priority(c1) == 10.0
          and not service.open_conflicts(a.addon, a.profile) and not service.open_conflicts(b.addon, b.profile))

    pdf = a.add_annotated_pdf(c2, notes[1][0].id, "e" * 32)
    a.inc()
    b.inc()
    seen = b.read_pdf(c2)
    check("S5 the annotated PDF arrives byte for byte", seen.get("sha") == hashlib.sha256(pdf.read_bytes()).hexdigest())
    check("S5 B's interchange keeps one highlight with A's note", seen.get("native") == 1
          and seen.get("notes") == ["key idea"], str(seen))

    b.set_zoom(c2, 2.0)
    b.inc()
    a.inc()
    a.add_reading_state(c2)
    a.inc()
    b.inc()
    state = b.reading_state(c2)
    check("S6 position and bookmark follow, zoom stays", state == {"position": [7, 6, 2.0], "bookmark": "come back"},
          str(state))

    a.change_schema("Extra")
    print("A after a schema change:", a.ankiweb(True))
    print("B:", b.ankiweb(False))
    a.set_priority(c3, 66.0)
    a.inc()
    b.inc()
    check("S7 after a full sync, Incremento sync carries on", b.priority(c3) == 66.0)
    check("S7 earlier Incremento data survives the full sync", b.priority(c1) == 10.0 and b.priority(c4) == 33.0)

    a.change_schema("Extra2")
    a.ankiweb(True)
    _, c9 = a.add_note("q9")
    a.ankiweb(True)
    a.set_priority(c9, 77.0)
    a.inc()
    b.inc()
    check("S8 data for a card created after another device's full sync waits", b.inbox(c9) == ["pending_anki"],
          str(b.inbox(c9)))
    b.ankiweb(False)
    b.inc()
    check("S8 and applies once this device has synced", b.priority(c9) == 77.0)

    a.close()
    b.close()
    return check.finish()


# --- Device B in another Python ------------------------------------------------------

def _wsl_path(path: Path) -> str:
    resolved = str(Path(path).resolve())
    return "/mnt/" + resolved[0].lower() + resolved[2:].replace("\\", "/")


class RemoteDevice:
    """Device B driven one step at a time through another Python (optionally inside WSL)."""

    def __init__(self, python: str, state: str, wsl: bool):
        self.python, self.state, self.wsl = python, state, wsl

    def path(self, path: Path) -> str:
        return _wsl_path(path) if self.wsl else str(path)

    def __call__(self, action: str, **args) -> dict:
        step = [self.python, self.path(Path(__file__)), "device-step", self.path(REPO), self.state, action,
                json.dumps(args)]
        env = dict(os.environ)
        if self.wsl:
            env["WSLENV"] = "INC_E2E_USER/u:INC_E2E_PASS/u"
            quoted = " ".join("'" + part.replace("'", "'\\''") + "'" if index else part
                              for index, part in enumerate(step))
            command = ["wsl", "-e", "sh", "-c", f"cd ~ && {quoted} 2>/dev/null"]
        else:
            command = step
        out = subprocess.run(command, env=env, capture_output=True, timeout=600).stdout
        lines = out.decode("utf-8", "replace").replace("\0", "").strip().splitlines()
        if not lines:
            raise RuntimeError(f"device B step {action} printed nothing")
        return json.loads(lines[-1])


def cross_platform(workdir: Path, python: str, state: str, wsl: bool) -> int:
    modules = _load_backend()
    credentials = _credentials()
    folder = workdir / "CloudFolder"
    folder.mkdir(parents=True)
    b = RemoteDevice(python, state, wsl)
    print("B:", b("reset"))
    a = Device(modules, "A", workdir, credentials)
    service = a.service
    check = Checks()

    notes = [a.add_note(f"q{i}") for i in range(2)]
    c1, c2 = (card for _, card in notes)
    a.ankiweb(True)
    print("B first AnkiWeb sync:", b("ankiweb"))
    service.configure(a.addon, a.profile, str(folder))
    b("configure", folder=b.path(folder))

    a.set_priority(c1, 25.0)
    a.inc()
    b("inc")
    check("X1 A's priority reaches B", b("priority", card=c1)["value"] == 25.0)
    b("set_priority", card=c2, value=55.0)
    b("inc")
    a.inc()
    check("X2 B's priority reaches A", a.priority(c2) == 55.0)

    _, c3 = a.add_note("q3")
    a.set_priority(c3, 33.0)
    a.inc()
    b("inc")
    check("X3 data before its card waits on B", b("inbox", card=c3)["statuses"] == ["pending_anki"])
    a.ankiweb(True)
    a.inc()
    b("ankiweb")
    b("inc")
    check("X3 and applies after B's AnkiWeb sync", b("priority", card=c3)["value"] == 33.0)

    a.set_priority(c1, 10.0)
    b("set_priority", card=c1, value=90.0)
    a.inc()
    report = b("inc")
    check("X4 concurrent edits conflict on B", report["conflicts"] == 1, str(report))
    b("resolve_theirs")
    b("inc")
    a.inc()
    check("X4 resolved on B, both agree", a.priority(c1) == 10.0 and b("priority", card=c1)["value"] == 10.0
          and not service.open_conflicts(a.addon, a.profile))

    pdf = a.add_annotated_pdf(c2, notes[1][0].id, "f" * 32)
    expected = hashlib.sha256(pdf.read_bytes()).hexdigest()
    a.inc()
    b("set_zoom", card=c2, zoom=2.0)
    b("inc")
    seen = b("read_pdf", card=c2)
    check("X5 the annotated PDF arrives on B byte for byte", seen.get("sha") == expected)
    check("X5 B's interchange keeps one highlight with A's note", seen.get("native") == 1
          and seen.get("notes") == ["key idea"], str(seen))

    a.inc()
    a.add_reading_state(c2)
    a.inc()
    b("inc")
    state_b = b("reading_state", card=c2)
    check("X6 position and bookmark reach B, B keeps its zoom",
          state_b == {"position": [7, 6, 2.0], "bookmark": "come back"}, str(state_b))

    a.close()
    b("forget_session")
    return check.finish()


def device_step(repo: str, state_dir: str, action: str, args: dict) -> dict:
    """One action of device B; its state persists in ``state_dir`` between steps."""
    state = Path(state_dir).expanduser()
    if action == "reset":
        fresh_directory(state)
        return {"ok": True, "platform": sys.platform}
    if action == "forget_session":
        (state / "auth.bin").unlink(missing_ok=True)
        return {"ok": True}
    modules = _load_backend()
    device = Device.__new__(Device)
    device.db, device.paths, device.pdf_annotations, device.service, sync_pb2, collection = modules
    device.required = sync_pb2.SyncCollectionResponse.ChangesRequired
    device.names = {value: name for name, value in device.required.items()}
    device.addon, device.profile = str(state / "addon"), "P"
    device.col = collection(str(state / "collection.anki2"))
    try:
        if action == "ankiweb":
            session = state / "auth.bin"
            device.auth = sync_pb2.SyncAuth.FromString(session.read_bytes()) if session.exists() else None
            device.credentials = _credentials()
            required = device.ankiweb(prefer_upload=False)
            session.write_bytes(device.auth.SerializeToString())
            return {"required": required, "cards": device.scalar("select count() from cards")}
        if action == "configure":
            return {"created": device.service.configure(device.addon, device.profile, args["folder"]).created}
        if action == "inc":
            report = device.inc()
            return {"skipped": report.skipped, "applied": report.applied, "conflicts": report.conflicts,
                    "problems": report.problems}
        if action == "set_priority":
            device.set_priority(args["card"], args["value"])
            return {"ok": True}
        if action == "priority":
            return {"value": device.priority(args["card"])}
        if action == "inbox":
            return {"statuses": device.inbox(args["card"])}
        if action == "resolve_theirs":
            return {"resolved": device.resolve_theirs()}
        if action == "set_zoom":
            device.set_zoom(args["card"], args["zoom"])
            return {"ok": True}
        if action == "read_pdf":
            return device.read_pdf(args["card"])
        if action == "reading_state":
            return device.reading_state(args["card"])
        raise SystemExit(f"unknown device step {action}")
    finally:
        device.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("two-devices", "cross-platform"):
        command = commands.add_parser(name)
        command.add_argument("--workdir", required=True, help="Created afresh; must be outside the repository.")
        command.add_argument("--overwrite-ankiweb", action="store_true",
                             help="Confirm that the disposable AnkiWeb account's collection may be replaced.")
        if name == "cross-platform":
            command.add_argument("--b-python", required=True, help="Python with anki and PyMuPDF for device B.")
            command.add_argument("--b-state", required=True, help="Device B's state directory (in its own system).")
            command.add_argument("--wsl", action="store_true", help="Run device B inside WSL.")
    step = commands.add_parser("device-step")
    step.add_argument("repo")
    step.add_argument("state")
    step.add_argument("action")
    step.add_argument("args", nargs="?", default="{}")
    options = parser.parse_args(argv)

    if options.command == "device-step":
        print(json.dumps(device_step(options.repo, options.state, options.action, json.loads(options.args))))
        return 0
    if not options.overwrite_ankiweb:
        raise SystemExit("This replaces the AnkiWeb account's collection; pass --overwrite-ankiweb "
                         "only for a disposable account.")
    _credentials()
    workdir = _checked_workdir(options.workdir)
    fresh_directory(workdir)
    if options.command == "two-devices":
        return two_devices(workdir)
    return cross_platform(workdir, options.b_python, options.b_state, options.wsl)


if __name__ == "__main__":
    sys.exit(main())
