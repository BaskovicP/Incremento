"""Read-only parser for native SuperMemo 17/18/20 collection files.

The parser intentionally extracts only data that maps to Anki or Incremento.
Unknown component types remain inert, and optimization records are copied
losslessly instead of being interpreted as executable scheduling rules.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import stat
import struct
import zipfile
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath


ELEMENT_INFO_RECORD_SIZE = 118
CONTENTS_RECORD_SIZE = 37
REPETITION_HISTORY_RECORD_SIZE = 39
TEXT_REGISTRY_RECORD_SIZE = 30
SUPPORTED_STRUCTURE_VERSIONS = frozenset({20, 21, 22})
_TEXT_COMPONENT_TYPES = frozenset({0, 13, 16})

_MAX_ELEMENTS = 5_000_000
_MAX_ARCHIVE_ENTRIES = 100_000
_MAX_ARCHIVE_MEMBER_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
_MAX_ELEMENT_FILES = 1_000_000
_MAX_HTML_BYTES = 16 * 1024 * 1024
_DELPHI_EPOCH = datetime(1899, 12, 30)
_SUPERMEMO_EPOCH = date(1980, 1, 1)


class SuperMemoFormatError(ValueError):
    """The source is incomplete, unsafe, corrupt, or unsupported."""


@dataclass(frozen=True)
class SuperMemoReview:
    repetition_number: int
    reviewed_at: datetime
    grade: int
    previous_interval: int
    scheduled_interval: int
    priority_at_review: float | None
    retrievability: int | None
    is_graded: bool
    lapse_count: int = 0


@dataclass(frozen=True)
class SuperMemoReference:
    reference_id: int
    title: str = ""
    date_text: str = ""
    url: str = ""
    source: str = ""
    comment: str = ""


@dataclass(frozen=True)
class SuperMemoMedia:
    member_id: int
    file_id: int
    name: str
    source_path: Path


@dataclass(frozen=True)
class SuperMemoElement:
    element_id: int
    element_type: int
    status: int
    parent_id: int | None
    sort_order: int
    priority_rank: int
    a_factor: float
    forgetting_index: int
    current_interval: int
    due_date: date | None
    repetition_count: int
    lapse_count: int
    title: str
    question: str
    answer: str
    body: str
    history: tuple[SuperMemoReview, ...]
    question_html: str = ""
    answer_html: str = ""
    body_html: str = ""
    media: tuple[SuperMemoMedia, ...] = ()
    deleted: bool = False
    last_repetition_date: date | None = None
    reference: SuperMemoReference | None = None

    @property
    def is_item(self) -> bool:
        return self.element_type == 1

    @property
    def is_task(self) -> bool:
        return self.element_type == 2


@dataclass(frozen=True)
class OptimizationFile:
    relative_path: str
    source_path: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class SuperMemoCollection:
    name: str
    kno_path: Path
    collection_dir: Path
    fingerprint: str
    structure_version: int
    first_day: date
    last_day: date
    default_forgetting_index: int
    elements: tuple[SuperMemoElement, ...]
    optimization_files: tuple[OptimizationFile, ...]


@dataclass(frozen=True)
class _RegistryMember:
    member_id: int
    kind: int
    text: str
    file_id: int
    rich_html: str


def decode_real48(raw: bytes) -> float:
    """Decode Delphi's six-byte Real48 floating-point representation."""
    if len(raw) != 6:
        raise SuperMemoFormatError("A Real48 value must contain exactly six bytes.")
    exponent = raw[0]
    if exponent == 0:
        return 0.0
    fraction = int.from_bytes(raw[1:5] + bytes((raw[5] & 0x7F,)), "little")
    value = (1.0 + fraction / float(1 << 39)) * math.ldexp(1.0, exponent - 129)
    return -value if raw[5] & 0x80 else value


def _read_required(path: Path, *, maximum: int = 2 * 1024 * 1024 * 1024) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise SuperMemoFormatError(f"Missing required SuperMemo file: {path.name}") from exc
    if not path.is_file() or path.is_symlink():
        raise SuperMemoFormatError(f"Unsafe required SuperMemo file: {path.name}")
    if size > maximum:
        raise SuperMemoFormatError(f"SuperMemo file is too large: {path.name}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SuperMemoFormatError(f"Could not read SuperMemo file: {path.name}") from exc


def _first_existing_file(directory: Path, *names: str) -> Path:
    """Resolve known native filename variants without accepting ambiguity."""
    for name in names:
        candidate = directory / name
        if candidate.exists():
            return candidate
    wanted = {name.casefold() for name in names}
    try:
        matches = [path for path in directory.iterdir() if path.name.casefold() in wanted]
    except OSError:
        matches = []
    if len(matches) > 1:
        raise SuperMemoFormatError(f"Ambiguous SuperMemo file: {names[0]}")
    return matches[0] if matches else directory / names[0]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _fixed_records(data: bytes, record_size: int, count: int, filename: str) -> list[bytes]:
    expected = record_size * count
    if len(data) != expected:
        raise SuperMemoFormatError(
            f"{filename} has {len(data)} bytes; expected {expected} for {count} elements."
        )
    return [data[offset : offset + record_size] for offset in range(0, expected, record_size)]


def _clean_text(value: str, *, limit: int = 2_000_000) -> str:
    value = value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return "".join(char for char in value[:limit] if char in "\n\t" or ord(char) >= 32).strip()


def _decode_registry_text(blob: bytes, offset: int, length: int, member_id: int) -> str:
    """Decode one RTX value and validate its six-byte ownership trailer."""
    if not offset:
        return ""
    start = int(offset) - 1
    length = int(length)
    if start < 0 or length < 6 or length > 2_000_006 or start + length > len(blob):
        raise SuperMemoFormatError("A SuperMemo registry member points outside its RTX file.")
    record = blob[start : start + length]
    if record[-6] != 0:
        raise SuperMemoFormatError("A SuperMemo registry member has a malformed RTX trailer.")
    trailer_member_id = int(struct.unpack_from("<I", record, length - 5)[0])
    if trailer_member_id != int(member_id):
        raise SuperMemoFormatError("A SuperMemo registry member identity does not match its RTX trailer.")
    raw = record[:-6]
    for encoding in ("utf-8", "cp1252"):
        try:
            return _clean_text(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    return _clean_text(raw.decode("utf-8", "replace"))


def _decode_html_file(path: Path) -> str:
    data = _read_required(path, maximum=_MAX_HTML_BYTES)
    for encoding in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding).replace("\x00", "")
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace").replace("\x00", "")


def _index_element_files(collection_dir: Path) -> dict[int, Path]:
    elements_dir = collection_dir / "elements"
    if not elements_dir.exists():
        return {}
    if not elements_dir.is_dir() or elements_dir.is_symlink():
        raise SuperMemoFormatError("The SuperMemo elements directory is unsafe.")
    indexed: dict[int, Path] = {}
    inspected = 0
    try:
        candidates = elements_dir.rglob("*")
        for path in candidates:
            inspected += 1
            if inspected > _MAX_ELEMENT_FILES:
                raise SuperMemoFormatError("The SuperMemo elements directory contains too many entries.")
            if path.is_symlink():
                raise SuperMemoFormatError("The SuperMemo elements directory contains a symlink.")
            if not path.is_file() or not path.stem.isdecimal():
                continue
            file_id = int(path.stem)
            if file_id < 1:
                continue
            if file_id in indexed:
                raise SuperMemoFormatError(f"Duplicate SuperMemo element file number: {file_id}")
            indexed[file_id] = path
    except OSError as exc:
        raise SuperMemoFormatError("Could not inspect the SuperMemo elements directory.") from exc
    return indexed


def _parse_registry(
    registry_dir: Path,
    registry_name: str,
    element_files: dict[int, Path],
    *,
    optional: bool = False,
    load_html: bool = False,
) -> tuple[list[_RegistryMember], dict[int, list[int]]]:
    memory_path = _first_existing_file(registry_dir, f"{registry_name}.mem")
    if optional and not memory_path.exists():
        return [], {}
    memory = _read_required(memory_path)
    names = _read_required(_first_existing_file(registry_dir, f"{registry_name}.rtx"))
    if len(memory) % TEXT_REGISTRY_RECORD_SIZE:
        raise SuperMemoFormatError(f"{registry_name}.mem has a truncated registry record.")
    members: list[_RegistryMember] = []
    usage_heads: list[tuple[int, int]] = []
    for index in range(len(memory) // TEXT_REGISTRY_RECORD_SIZE):
        record = memory[index * TEXT_REGISTRY_RECORD_SIZE : (index + 1) * TEXT_REGISTRY_RECORD_SIZE]
        usage_count = struct.unpack_from("<I", record, 0)[0]
        kind = struct.unpack_from("<I", record, 4)[0]
        name_offset = struct.unpack_from("<I", record, 10)[0]
        name_length = struct.unpack_from("<I", record, 14)[0]
        usage_head = struct.unpack_from("<I", record, 18)[0]
        file_id = struct.unpack_from("<I", record, 22)[0]
        rich_html = ""
        source_file = element_files.get(int(file_id))
        if (
            load_html
            and source_file is not None
            and source_file.suffix.casefold() in {".htm", ".html"}
        ):
            rich_html = _decode_html_file(source_file)
        members.append(
            _RegistryMember(
                member_id=index + 1,
                kind=int(kind),
                text=_decode_registry_text(names, name_offset, name_length, index + 1),
                file_id=int(file_id),
                rich_html=rich_html,
            )
        )
        usage_heads.append((int(usage_count), int(usage_head)))

    usage_path = _first_existing_file(registry_dir, f"{registry_name}.lst")
    usage_data = _read_required(usage_path) if usage_path.exists() else b""
    if len(usage_data) % 8:
        raise SuperMemoFormatError(f"{registry_name}.lst has a truncated usage record.")
    usage_nodes = [
        struct.unpack_from("<II", usage_data, offset)
        for offset in range(0, len(usage_data), 8)
    ]
    by_element: dict[int, list[int]] = {}
    for member_index, (usage_count, usage_head) in enumerate(usage_heads):
        if not usage_count or not usage_nodes or not 1 <= usage_head <= len(usage_nodes):
            continue
        pointer = usage_head
        visited: set[int] = set()
        for _ in range(min(usage_count, len(usage_nodes))):
            if not 1 <= pointer <= len(usage_nodes) or pointer in visited:
                break
            visited.add(pointer)
            element_id, next_pointer = usage_nodes[pointer - 1]
            if element_id > 0:
                by_element.setdefault(int(element_id), []).append(member_index + 1)
            if next_pointer == 0:
                break
            pointer = int(next_pointer)
    return members, by_element


def _parse_text_registry(
    registry_dir: Path,
    element_files: dict[int, Path],
) -> tuple[list[_RegistryMember], dict[int, list[int]]]:
    return _parse_registry(
        registry_dir,
        "Text",
        element_files,
        load_html=True,
    )


def _component_text_member_ids(
    component_data: bytes,
    offset: int,
    element_id: int,
) -> tuple[int, ...]:
    if offset == 0xFFFFFFFF:
        return ()
    if offset < 0 or offset + 9 > len(component_data):
        raise SuperMemoFormatError("ElementInfo.dat contains an invalid compon.dat pointer.")
    signature, payload_length = struct.unpack_from("<HH", component_data, offset)
    if signature != 0xD431:
        raise SuperMemoFormatError("compon.dat record signature does not match ElementInfo.dat.")
    end = offset + 4 + int(payload_length)
    if end > len(component_data):
        raise SuperMemoFormatError("compon.dat contains a truncated component record.")
    block = component_data[offset:end]
    if len(block) < 11:
        raise SuperMemoFormatError("compon.dat contains a truncated element component block.")
    owner_id = int(struct.unpack_from("<I", block, 4)[0])
    if owner_id != int(element_id):
        raise SuperMemoFormatError("compon.dat component owner does not match ElementInfo.dat.")
    component_count = block[8]
    records_offset = 11 + int(struct.unpack_from("<H", block, 9)[0])
    if records_offset < 11 or records_offset > len(block):
        raise SuperMemoFormatError("compon.dat contains an invalid component records offset.")
    cursor = records_offset
    text_member_ids: list[int] = []
    for _ in range(component_count):
        if cursor + 2 > len(block):
            raise SuperMemoFormatError("compon.dat contains a truncated component descriptor.")
        header = int(struct.unpack_from("<H", block, cursor)[0])
        component_type = header & 0xFF
        component_struct_size = (header >> 8) + 1
        component_end = cursor + 2 + component_struct_size
        if component_end > len(block):
            raise SuperMemoFormatError("compon.dat contains a truncated component payload.")
        if component_type in _TEXT_COMPONENT_TYPES:
            if cursor + 24 > component_end:
                raise SuperMemoFormatError("compon.dat contains a truncated text component.")
            member_id = int(struct.unpack_from("<I", block, cursor + 20)[0])
            if member_id:
                text_member_ids.append(member_id)
        cursor = component_end
    if cursor != len(block):
        raise SuperMemoFormatError("compon.dat component sizes do not match the element block.")
    return tuple(text_member_ids)


def _member_text(members: list[_RegistryMember], member_id: int | None) -> str:
    if member_id is None or member_id < 1 or member_id > len(members):
        return ""
    return members[member_id - 1].text


def _member_html(members: list[_RegistryMember], member_id: int | None) -> str:
    if member_id is None or member_id < 1 or member_id > len(members):
        return ""
    return members[member_id - 1].rich_html


def _best_title(texts: list[str], fallback: str) -> str:
    candidates = [text.strip() for text in texts if text.strip()]
    candidates = [
        text
        for text in candidates
        if not text.casefold().startswith("imported on ")
        and not text.casefold().startswith(("http://", "https://"))
    ]
    if not candidates:
        return fallback
    return min(candidates, key=lambda value: (len(value), candidates.index(value)))[:500]


def _parse_history(path: Path, element_count: int) -> dict[int, list[SuperMemoReview]]:
    data = _read_required(path)
    if len(data) % REPETITION_HISTORY_RECORD_SIZE:
        raise SuperMemoFormatError("RepetitionHistory.dat has a truncated history record.")
    history: dict[int, list[SuperMemoReview]] = {}
    for offset in range(0, len(data), REPETITION_HISTORY_RECORD_SIZE):
        record = data[offset : offset + REPETITION_HISTORY_RECORD_SIZE]
        element_id = int(struct.unpack_from("<I", record, 0)[0])
        repetition_number, lapse_count = struct.unpack_from("<HH", record, 4)
        if not 1 <= element_id <= element_count:
            raise SuperMemoFormatError("RepetitionHistory.dat contains an invalid element reference.")
        delphi_value = struct.unpack_from("<d", record, 10)[0]
        if not math.isfinite(delphi_value) or delphi_value < 0 or delphi_value > 1_000_000:
            raise SuperMemoFormatError("RepetitionHistory.dat contains an invalid timestamp.")
        reviewed_at = _DELPHI_EPOCH + timedelta(days=delphi_value)
        grade = int(record[24])
        raw_priority = int(struct.unpack_from("<h", record, 25)[0])
        priority = None if raw_priority < 0 else max(0.0, min(100.0, raw_priority / 100.0))
        raw_retrievability = int(record[38])
        history.setdefault(int(element_id), []).append(
            SuperMemoReview(
                repetition_number=int(repetition_number),
                reviewed_at=reviewed_at,
                grade=grade,
                previous_interval=int(struct.unpack_from("<H", record, 8)[0]),
                scheduled_interval=0,
                priority_at_review=priority,
                retrievability=None if raw_retrievability == 255 else raw_retrievability,
                is_graded=1 <= grade <= 5,
                lapse_count=int(lapse_count),
            )
        )
    for entries in history.values():
        entries.sort(
            key=lambda entry: (entry.reviewed_at, entry.lapse_count, entry.repetition_number)
        )
    return history


def _parse_references(
    registry_dir: Path,
    members: list[_RegistryMember],
) -> dict[int, SuperMemoReference]:
    path = _first_existing_file(registry_dir, "reference.dat")
    if not path.exists():
        return {}
    data = _read_required(path)
    if len(data) % 32:
        raise SuperMemoFormatError("reference.dat has a truncated reference record.")
    references: dict[int, SuperMemoReference] = {}
    for offset in range(0, len(data), 32):
        member_ids = struct.unpack_from("<8I", data, offset)
        reference_id = offset // 32 + 1
        references[reference_id] = SuperMemoReference(
            reference_id=reference_id,
            title=_member_text(members, int(member_ids[1])),
            date_text=_member_text(members, int(member_ids[2])),
            url=_member_text(members, int(member_ids[3])),
            source=_member_text(members, int(member_ids[4])),
            comment=_member_text(members, int(member_ids[7])),
        )
    return references


def _optimization_files(collection_dir: Path) -> tuple[OptimizationFile, ...]:
    candidates: list[Path] = []
    sm8 = collection_dir / "info" / "sm8opt.dat"
    if sm8.is_file() and not sm8.is_symlink():
        candidates.append(sm8)
    alg17 = collection_dir / "alg17"
    if alg17.is_dir() and not alg17.is_symlink():
        candidates.extend(
            path for path in sorted(alg17.glob("*.dat"), key=lambda value: value.name.casefold())
            if path.is_file() and not path.is_symlink()
        )
    result: list[OptimizationFile] = []
    for path in candidates:
        relative = path.relative_to(collection_dir).as_posix()
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
        result.append(OptimizationFile(relative, path, size, digest.hexdigest()))
    return tuple(sorted(result, key=lambda item: item.relative_path.casefold()))


def parse_supermemo_collection(kno_path: Path | str, collection_dir: Path | str) -> SuperMemoCollection:
    """Parse a matched ``.Kno`` file and native collection directory."""
    kno_path = Path(kno_path)
    collection_dir = Path(collection_dir)
    kno = _read_required(kno_path, maximum=16 * 1024 * 1024)
    if len(kno) < 24:
        raise SuperMemoFormatError("The KNO file is truncated.")
    element_count, _memorized, _allocated = struct.unpack_from("<III", kno, 0)
    if element_count < 1 or element_count > _MAX_ELEMENTS:
        raise SuperMemoFormatError("The KNO element count is invalid or unsupported.")
    structure_version = int(kno[12])
    if structure_version not in SUPPORTED_STRUCTURE_VERSIONS:
        raise SuperMemoFormatError(
            f"Unsupported SuperMemo structure version {structure_version}; "
            f"supported versions are {sorted(SUPPORTED_STRUCTURE_VERSIONS)}."
        )
    first_day_offset, last_day_offset = struct.unpack_from("<HH", kno, 19)
    first_day = _SUPERMEMO_EPOCH + timedelta(days=int(first_day_offset))
    last_day = first_day + timedelta(days=int(last_day_offset))

    info_dir = collection_dir / "info"
    registry_dir = collection_dir / "registry"
    element_records = _fixed_records(
        _read_required(info_dir / "ElementInfo.dat"),
        ELEMENT_INFO_RECORD_SIZE,
        int(element_count),
        "ElementInfo.dat",
    )
    contents_records = _fixed_records(
        _read_required(info_dir / "contents.dat"),
        CONTENTS_RECORD_SIZE,
        int(element_count),
        "contents.dat",
    )
    repetitions = _read_required(info_dir / "repetitions.dat")
    if len(repetitions) != int(element_count) * 4:
        raise SuperMemoFormatError("repetitions.dat does not match the KNO element count.")
    priorities = _read_required(info_dir / "priority.sub")
    if len(priorities) % 4:
        raise SuperMemoFormatError("priority.sub has a truncated element reference.")
    priority_ids = [struct.unpack_from("<I", priorities, offset)[0] for offset in range(0, len(priorities), 4)]
    if len(set(priority_ids)) != len(priority_ids) or any(
        element_id < 1 or element_id > element_count for element_id in priority_ids
    ):
        raise SuperMemoFormatError("priority.sub contains duplicate or invalid element references.")
    priority_rank = {int(element_id): rank for rank, element_id in enumerate(priority_ids)}

    element_files = _index_element_files(collection_dir)
    members, usages = _parse_text_registry(registry_dir, element_files)
    references = _parse_references(registry_dir, members)
    image_members, image_usages = _parse_registry(
        registry_dir,
        "Image",
        element_files,
        optional=True,
    )
    components = _read_required(info_dir / "compon.dat")
    raw_history = _parse_history(
        _first_existing_file(info_dir, "RepetitionHistory.dat", "RepetitionHist.dat"),
        int(element_count),
    )

    elements: list[SuperMemoElement] = []
    for index, record in enumerate(element_records):
        element_id = index + 1
        element_type = int(record[0])
        status = int(record[1])
        deleted = bool(contents_records[index][0])
        parent = int(struct.unpack_from("<I", contents_records[index], 1)[0])
        parent_id = parent if 1 <= parent <= element_count and parent != element_id else None
        title_member_id = int(struct.unpack_from("<i", record, 2)[0])
        native_title = _member_text(members, title_member_id)
        component_offset = int(struct.unpack_from("<I", record, 6)[0])
        component_text_members = _component_text_member_ids(
            components,
            component_offset,
            element_id,
        )
        if element_type == 1:
            question_member = component_text_members[0] if component_text_members else None
            answer_member = component_text_members[1] if len(component_text_members) > 1 else None
            body_component_members = component_text_members[2:]
        else:
            question_member = None
            answer_member = None
            body_component_members = component_text_members
        question = _member_text(members, question_member)
        answer = _member_text(members, answer_member)
        question_html = _member_html(members, question_member)
        answer_html = _member_html(members, answer_member)
        used_members = [
            (
                _member_text(members, member_id),
                _member_html(members, member_id),
            )
            for member_id in usages.get(element_id, [])
        ]
        used_texts = [text for text, _rich_html in used_members]
        fallback_title = question or answer or f"SuperMemo element {element_id}"
        title = native_title or _best_title(used_texts, fallback_title)
        if element_type == 1:
            question = question or title
            title = title[:500] or question[:500] or fallback_title
        component_body_candidates = [
            (
                _member_text(members, member_id),
                _member_html(members, member_id),
            )
            for member_id in body_component_members
            if _member_text(members, member_id)
        ]
        body_candidates = [
            (text, rich_html)
            for text, rich_html in used_members
            if text and text not in {title, question, answer}
        ]
        body, body_html = max(
            component_body_candidates or body_candidates,
            key=lambda pair: (bool(pair[1]), len(pair[0])),
            default=("", ""),
        )
        if element_type != 1:
            # Topic/concept component pointers identify body text, not a
            # question/answer pair. Leaving Question empty selects the topic
            # side of the Incremento SuperMemo template.
            question = ""
            answer = ""
            question_html = ""
            answer_html = ""

        media: list[SuperMemoMedia] = []
        for image_member_id in image_usages.get(element_id, []):
            if not 1 <= image_member_id <= len(image_members):
                continue
            image_member = image_members[image_member_id - 1]
            source_path = element_files.get(image_member.file_id)
            if source_path is None:
                continue
            media.append(
                SuperMemoMedia(
                    member_id=image_member.member_id,
                    file_id=image_member.file_id,
                    name=image_member.text,
                    source_path=source_path,
                )
            )

        current_interval = int(struct.unpack_from("<H", record, 16)[0])
        entries = list(raw_history.get(element_id, ()))
        entries = [
            replace(
                entry,
                scheduled_interval=(
                    entries[position + 1].previous_interval
                    if position + 1 < len(entries)
                    else current_interval
                ),
            )
            for position, entry in enumerate(entries)
        ]
        declared_repetitions = int(struct.unpack_from("<H", record, 12)[0])
        declared_lapses = int(struct.unpack_from("<H", record, 14)[0])
        observed_repetitions = max((entry.repetition_number for entry in entries), default=0)
        observed_lapses = max((entry.lapse_count for entry in entries), default=0)
        repetition_count = max(declared_repetitions, observed_repetitions)
        lapse_count = max(declared_lapses, observed_lapses)
        last_repetition_day = int(struct.unpack_from("<h", record, 18)[0])
        last_repetition_date = (
            first_day + timedelta(days=last_repetition_day - 1)
            if status == 1
            else None
        )
        due_index = int(struct.unpack_from("<I", repetitions, index * 4)[0])
        due_date = first_day + timedelta(days=due_index - 1) if due_index else None
        reference_id = int(struct.unpack_from("<H", record, 44)[0])
        elements.append(
            SuperMemoElement(
                element_id=element_id,
                element_type=element_type,
                status=status,
                parent_id=parent_id,
                sort_order=index,
                priority_rank=priority_rank.get(element_id, len(priority_ids) + index),
                a_factor=decode_real48(record[28:34]),
                forgetting_index=int(struct.unpack_from("<I", record, 48)[0]),
                current_interval=current_interval,
                due_date=due_date,
                repetition_count=repetition_count,
                lapse_count=lapse_count,
                title=_clean_text(title, limit=500),
                question=_clean_text(question),
                answer=_clean_text(answer),
                body=_clean_text(body),
                history=tuple(entries),
                question_html=question_html,
                answer_html=answer_html,
                body_html=body_html,
                media=tuple(media),
                deleted=deleted,
                last_repetition_date=last_repetition_date,
                reference=references.get(reference_id),
            )
        )

    return SuperMemoCollection(
        name=kno_path.stem,
        kno_path=kno_path,
        collection_dir=collection_dir,
        fingerprint=hashlib.sha256(kno).hexdigest(),
        structure_version=structure_version,
        first_day=first_day,
        last_day=last_day,
        default_forgetting_index=int(kno[23]),
        elements=tuple(elements),
        optimization_files=_optimization_files(collection_dir),
    )


def locate_supermemo_collection(root: Path | str) -> tuple[Path, Path]:
    """Locate one unambiguous KNO/folder pair below ``root``."""
    root = Path(root)
    if root.is_file() and root.suffix.casefold() == ".kno":
        folder = root.with_suffix("")
        if folder.is_dir():
            return root, folder
        raise SuperMemoFormatError("The folder paired with the KNO file is missing.")
    if not root.is_dir():
        raise SuperMemoFormatError("The selected SuperMemo source does not exist.")
    candidates: list[tuple[Path, Path]] = []
    for kno in sorted(root.rglob("*"), key=lambda value: value.as_posix().casefold()):
        if kno.is_file() and not kno.is_symlink() and kno.suffix.casefold() == ".kno":
            folder = kno.with_suffix("")
            if folder.is_dir() and not folder.is_symlink():
                candidates.append((kno, folder))
    if not candidates:
        raise SuperMemoFormatError("No matched KNO file and collection folder were found.")
    if len(candidates) != 1:
        raise SuperMemoFormatError("The source contains more than one SuperMemo collection.")
    return candidates[0]


def extract_supermemo_archive(archive_path: Path | str, destination: Path | str) -> tuple[Path, Path]:
    """Safely extract a ZIP and return its sole matched collection pair."""
    archive_path = Path(archive_path)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        bundle = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise SuperMemoFormatError("The selected file is not a readable ZIP archive.") from exc
    with bundle:
        entries = bundle.infolist()
        if len(entries) > _MAX_ARCHIVE_ENTRIES:
            raise SuperMemoFormatError("The ZIP archive contains too many entries.")
        total = 0
        root = destination.resolve()
        for entry in entries:
            raw_name = entry.filename.replace("\\", "/")
            path = PurePosixPath(raw_name)
            if (
                not raw_name
                or path.is_absolute()
                or any(part in {"", ".", ".."} for part in path.parts)
            ):
                raise SuperMemoFormatError(f"ZIP archive contains an unsafe path: {raw_name}")
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise SuperMemoFormatError(f"ZIP archive contains an unsafe symlink: {raw_name}")
            if entry.file_size > _MAX_ARCHIVE_MEMBER_BYTES:
                raise SuperMemoFormatError(f"ZIP entry is too large: {raw_name}")
            total += int(entry.file_size)
            if total > _MAX_ARCHIVE_TOTAL_BYTES:
                raise SuperMemoFormatError("The expanded ZIP archive is too large.")
            target = destination.joinpath(*path.parts)
            try:
                target.resolve().relative_to(root)
            except ValueError as exc:
                raise SuperMemoFormatError(f"ZIP archive contains an unsafe path: {raw_name}") from exc
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(entry, "r") as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    return locate_supermemo_collection(destination)


def write_optimization_archive(collection: SuperMemoCollection, destination: Path | str) -> Path:
    """Copy opaque SM8/SM17 optimization data and write a checksummed manifest."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    manifest_files: list[dict[str, object]] = []
    for item in collection.optimization_files:
        relative = PurePosixPath(item.relative_path)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise SuperMemoFormatError("Optimization data contains an unsafe path.")
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item.source_path, target)
        if target.stat().st_size != item.size:
            raise SuperMemoFormatError("Optimization data changed while it was being copied.")
        digest = _sha256_file(target)
        if digest != item.sha256:
            raise SuperMemoFormatError("Optimization data failed checksum verification.")
        manifest_files.append(
            {"path": item.relative_path, "size": item.size, "sha256": item.sha256}
        )
    manifest = {
        "format": "incremento-supermemo-optimization-v1",
        "collection": collection.name,
        "collection_fingerprint": collection.fingerprint,
        "structure_version": collection.structure_version,
        "scheduler": "preserved-only; Anki remains authoritative",
        "files": manifest_files,
    }
    manifest_path = destination / "manifest.json"
    temporary = destination / ".manifest.json.tmp"
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    return manifest_path
