from __future__ import annotations

import hashlib
import json
import struct
import zipfile
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from backend.supermemo_format import (
    SuperMemoFormatError,
    decode_real48,
    extract_supermemo_archive,
    parse_supermemo_collection,
    write_optimization_archive,
)
from backend.supermemo_import import (
    _ordered_elements,
    _sanitize_rich_html,
    is_supermemo_cloze_element,
)


def _real48(value: float) -> bytes:
    if value == 0:
        return b"\0" * 6
    import math

    sign = value < 0
    mantissa, exponent = math.frexp(abs(value))
    fraction = int(round(((mantissa * 2.0) - 1.0) * (1 << 39)))
    if fraction == 1 << 39:
        fraction = 0
        exponent += 1
    raw = bytearray([exponent + 128])
    raw.extend(int(fraction).to_bytes(5, "little"))
    if sign:
        raw[5] |= 0x80
    return bytes(raw)


def _delphi_datetime(value: datetime) -> float:
    return (value - datetime(1899, 12, 30)).total_seconds() / 86_400


def _write_fixture(root: Path) -> tuple[Path, Path]:
    collection_dir = root / "Example"
    info_dir = collection_dir / "info"
    registry_dir = collection_dir / "registry"
    info_dir.mkdir(parents=True)
    registry_dir.mkdir()

    kno = bytearray(256)
    struct.pack_into("<III", kno, 0, 2, 1, 0)
    kno[12] = 22
    kno[13:19] = _real48(2.5)
    struct.pack_into("<HH", kno, 19, (date(2024, 1, 2) - date(1980, 1, 1)).days, 5)
    kno[23] = 9
    kno_path = root / "Example.Kno"
    kno_path.write_bytes(kno)

    element_info = bytearray(2 * 118)
    element_info[0] = 0
    element_info[1] = 2
    struct.pack_into("<I", element_info, 2, 1)
    struct.pack_into("<I", element_info, 6, 234)
    element_info[28:34] = _real48(3.25)
    struct.pack_into("<H", element_info, 44, 1)
    struct.pack_into("<I", element_info, 48, 12)

    second = 118
    element_info[second] = 1
    element_info[second + 1] = 1
    struct.pack_into("<I", element_info, second + 2, 2)
    struct.pack_into("<I", element_info, second + 6, 0)
    # Offset 10 is unrelated scheduling data. Repetitions and lapses are two
    # uint16 values at 12/14; the current interval is uint16 at 16.
    struct.pack_into("<H", element_info, second + 10, 230)
    struct.pack_into("<H", element_info, second + 12, 2)
    struct.pack_into("<H", element_info, second + 14, 1)
    struct.pack_into("<H", element_info, second + 16, 17)
    struct.pack_into("<h", element_info, second + 18, -8)
    struct.pack_into("<d", element_info, second + 20, _delphi_datetime(datetime(2024, 1, 8, 10, 15)))
    element_info[second + 28 : second + 34] = _real48(4.5)
    struct.pack_into("<H", element_info, second + 44, 1)
    struct.pack_into("<I", element_info, second + 48, 8)
    (info_dir / "ElementInfo.dat").write_bytes(element_info)

    contents = bytearray(2 * 37)
    struct.pack_into("<I", contents, 1, 0)
    struct.pack_into("<I", contents, 37 + 1, 1)
    (info_dir / "contents.dat").write_bytes(contents)
    (info_dir / "priority.sub").write_bytes(struct.pack("<II", 2, 1))
    (info_dir / "repetitions.dat").write_bytes(struct.pack("<II", 0, 9))

    history = bytearray(3 * 39)
    struct.pack_into("<IHHH", history, 0, 2, 1, 0, 0)
    struct.pack_into("<d", history, 10, _delphi_datetime(datetime(2023, 12, 18, 9, 30)))
    history[24] = 8
    struct.pack_into("<h", history, 25, -1)
    history[38] = 100
    offset = 39
    struct.pack_into("<IHHH", history, offset, 2, 1, 1, 3)
    struct.pack_into("<d", history, offset + 10, _delphi_datetime(datetime(2023, 12, 21, 10, 15)))
    history[offset + 24] = 2
    struct.pack_into("<h", history, offset + 25, 2500)
    history[offset + 38] = 91
    offset = 78
    struct.pack_into("<IHHH", history, offset, 2, 2, 1, 3)
    struct.pack_into("<d", history, offset + 10, _delphi_datetime(datetime(2023, 12, 24, 10, 15)))
    history[offset + 24] = 4
    struct.pack_into("<h", history, offset + 25, 2300)
    history[offset + 38] = 90
    (info_dir / "RepetitionHistory.dat").write_bytes(history)

    # One item component block. Each two-byte header carries the type in its
    # low byte and the following struct size minus one in its high byte. The
    # one-based registry member is at struct offset 18 (header offset 20).
    block = bytearray(234)
    struct.pack_into("<HHI", block, 0, 0xD431, 230, 2)
    block[8] = 6
    struct.pack_into("<H", block, 9, 43)
    component_offset = 54
    for component_type, payload_size, member_id in (
        (13, 28, 2),
        (2, 25, 0),
        (2, 25, 0),
        (2, 25, 0),
        (2, 25, 0),
        (0, 34, 3),
    ):
        block[component_offset] = component_type
        struct.pack_into("<H", block, component_offset + 1, payload_size)
        struct.pack_into("<I", block, component_offset + 20, member_id)
        component_offset += 3 + payload_size
    topic_block = bytearray(85)
    struct.pack_into("<HHI", topic_block, 0, 0xD431, 81, 1)
    topic_block[8] = 1
    struct.pack_into("<H", topic_block, 9, 43)
    topic_block[54] = 13
    struct.pack_into("<H", topic_block, 55, 28)
    struct.pack_into("<I", topic_block, 74, 4)
    (info_dir / "compon.dat").write_bytes(block + topic_block)

    texts = (
        "Authoritative root topic",
        "What is retained?",
        "Everything important",
        "Body",
        "Reference title",
        "Imported on January 2, 2024",
        "https://example.com/reference",
        "Reference source",
        "Reference comment",
    )
    text_rtx = bytearray()
    text_mem = bytearray()
    for index, text in enumerate(texts):
        value = text.encode("utf-8")
        encoded = value + b"\0" + struct.pack("<I", index + 1) + b"\0"
        start = len(text_rtx)
        text_rtx.extend(encoded)
        record = bytearray(30)
        struct.pack_into("<I", record, 0, 1 if index in {0, 3} else 0)
        struct.pack_into("<I", record, 4, 3)
        struct.pack_into("<I", record, 10, start + 1)
        struct.pack_into("<I", record, 14, len(encoded))
        if index == 0:
            struct.pack_into("<I", record, 18, 1)
            struct.pack_into("<I", record, 22, 10)
        elif index == 1:
            struct.pack_into("<I", record, 22, 11)
        elif index == 2:
            struct.pack_into("<I", record, 22, 12)
        elif index == 3:
            struct.pack_into("<I", record, 18, 2)
            struct.pack_into("<I", record, 22, 13)
        text_mem.extend(record)
    (registry_dir / "Text.rtx").write_bytes(text_rtx)
    (registry_dir / "Text.mem").write_bytes(text_mem)
    (registry_dir / "Text.lst").write_bytes(
        struct.pack("<IIII", 1, 0, 1, 0)
    )
    (registry_dir / "Text.ptr").write_bytes(b"")

    element_files = collection_dir / "elements" / "1"
    element_files.mkdir(parents=True)
    (element_files / "10.HTM").write_text(
        "<h2><strong>Authoritative root</strong> topic</h2>",
        encoding="utf-8",
    )
    (element_files / "11.HTM").write_text(
        "<p><strong>What</strong> is retained?</p>",
        encoding="utf-8",
    )
    (element_files / "12.HTM").write_text(
        "<em>Everything important</em>",
        encoding="utf-8",
    )
    (element_files / "13.HTM").write_text("<p>Body</p>", encoding="utf-8")

    image_value = b"Retention diagram"
    image_name = image_value + b"\0" + struct.pack("<I", 1) + b"\0"
    image_mem = bytearray(30)
    struct.pack_into("<I", image_mem, 0, 1)
    struct.pack_into("<I", image_mem, 4, 2)
    struct.pack_into("<I", image_mem, 10, 1)
    struct.pack_into("<I", image_mem, 14, len(image_name))
    struct.pack_into("<I", image_mem, 18, 1)
    struct.pack_into("<I", image_mem, 22, 14)
    (registry_dir / "Image.mem").write_bytes(image_mem)
    (registry_dir / "Image.rtx").write_bytes(image_name)
    (registry_dir / "Image.lst").write_bytes(struct.pack("<II", 2, 0))
    (registry_dir / "Image.ptr").write_bytes(struct.pack("<I", 1))
    (element_files / "14.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"fixture-image"
    )

    (registry_dir / "reference.dat").write_bytes(
        struct.pack("<8I", 0, 5, 6, 7, 8, 0, 0, 9)
    )

    (info_dir / "sm8opt.dat").write_bytes(b"legacy-opt")
    alg17 = collection_dir / "alg17"
    alg17.mkdir()
    (alg17 / "Recall.dat").write_bytes(b"recall-matrix")
    return kno_path, collection_dir


def test_real48_decoder_matches_supermemo_extended_values() -> None:
    assert decode_real48(bytes.fromhex("819a99999919")) == pytest.approx(1.2)
    assert decode_real48(_real48(-4.5)) == pytest.approx(-4.5)
    assert decode_real48(b"\0" * 6) == 0.0


def test_parse_collection_preserves_tree_priority_schedule_and_history(tmp_path: Path) -> None:
    kno_path, collection_dir = _write_fixture(tmp_path)

    parsed = parse_supermemo_collection(kno_path, collection_dir)

    assert parsed.name == "Example"
    assert parsed.structure_version == 22
    assert parsed.first_day == date(2024, 1, 2)
    assert parsed.default_forgetting_index == 9
    assert parsed.fingerprint == hashlib.sha256(kno_path.read_bytes()).hexdigest()
    assert [element.element_id for element in parsed.elements] == [1, 2]
    assert parsed.elements[1].parent_id == 1
    assert parsed.elements[1].priority_rank == 0
    assert parsed.elements[1].a_factor == pytest.approx(4.5)
    assert parsed.elements[1].forgetting_index == 8
    assert parsed.elements[1].current_interval == 17
    assert parsed.elements[1].due_date == date(2024, 1, 10)
    assert parsed.elements[1].last_repetition_date == date(2023, 12, 24)
    assert parsed.elements[1].question == "What is retained?"
    assert parsed.elements[1].answer == "Everything important"
    assert parsed.elements[1].question_html == "<p><strong>What</strong> is retained?</p>"
    assert parsed.elements[1].answer_html == "<em>Everything important</em>"
    assert len(parsed.elements[1].media) == 1
    assert parsed.elements[1].media[0].name == "Retention diagram"
    assert parsed.elements[1].media[0].source_path.name == "14.png"
    assert parsed.elements[0].title == "Authoritative root topic"
    assert parsed.elements[0].body == "Body"
    assert parsed.elements[0].body_html == "<p>Body</p>"
    assert parsed.elements[0].reference is not None
    assert parsed.elements[0].reference.title == "Reference title"
    assert parsed.elements[0].reference.url == "https://example.com/reference"
    assert parsed.elements[0].reference.source == "Reference source"
    assert parsed.elements[0].reference.comment == "Reference comment"
    assert [entry.grade for entry in parsed.elements[1].history] == [8, 2, 4]
    assert [entry.lapse_count for entry in parsed.elements[1].history] == [0, 1, 1]
    assert parsed.elements[1].repetition_count == 2
    assert parsed.elements[1].lapse_count == 1
    assert parsed.elements[1].history[1].previous_interval == 3
    assert parsed.elements[1].history[1].scheduled_interval == 3
    assert parsed.elements[1].history[2].scheduled_interval == 17


def test_parser_rejects_mismatched_fixed_record_counts(tmp_path: Path) -> None:
    kno_path, collection_dir = _write_fixture(tmp_path)
    (collection_dir / "info" / "ElementInfo.dat").write_bytes(b"broken")

    with pytest.raises(SuperMemoFormatError, match="ElementInfo.dat"):
        parse_supermemo_collection(kno_path, collection_dir)


def test_parser_accepts_legacy_repetition_hist_filename(tmp_path: Path) -> None:
    kno_path, collection_dir = _write_fixture(tmp_path)
    current = collection_dir / "info" / "RepetitionHistory.dat"
    current.rename(collection_dir / "info" / "RepetitionHist.dat")

    parsed = parse_supermemo_collection(kno_path, collection_dir)

    assert len(parsed.elements[1].history) == 3


def test_parser_reads_rich_answer_when_it_is_the_second_text_component(tmp_path: Path) -> None:
    kno_path, collection_dir = _write_fixture(tmp_path)
    block = bytearray(144)
    struct.pack_into("<HHI", block, 0, 0xD431, 140, 2)
    block[8] = 3
    struct.pack_into("<H", block, 9, 43)
    component_offset = 54
    for component_type, payload_size, member_id in (
        (13, 28, 2),
        (13, 28, 3),
        (2, 25, 1),
    ):
        block[component_offset] = component_type
        struct.pack_into("<H", block, component_offset + 1, payload_size)
        struct.pack_into("<I", block, component_offset + 20, member_id)
        component_offset += 3 + payload_size
    component_path = collection_dir / "info" / "compon.dat"
    topic_block = component_path.read_bytes()[234:]
    element_info = bytearray((collection_dir / "info" / "ElementInfo.dat").read_bytes())
    struct.pack_into("<I", element_info, 6, len(block))
    (collection_dir / "info" / "ElementInfo.dat").write_bytes(element_info)
    component_path.write_bytes(block + topic_block)

    item = parse_supermemo_collection(kno_path, collection_dir).elements[1]

    assert item.question == "What is retained?"
    assert item.answer == "Everything important"
    assert item.answer_html == "<em>Everything important</em>"


def test_component_header_size_is_independent_of_first_struct_byte(tmp_path: Path) -> None:
    kno_path, collection_dir = _write_fixture(tmp_path)
    component_path = collection_dir / "info" / "compon.dat"
    components = bytearray(component_path.read_bytes())
    # The component header is only bytes 54-55. Byte 56 is the first byte of
    # the component structure and must not be folded into its size.
    components[56] = 7
    component_path.write_bytes(components)

    parsed = parse_supermemo_collection(kno_path, collection_dir)

    assert parsed.elements[1].question == "What is retained?"
    assert parsed.elements[1].answer == "Everything important"


def test_parser_marks_deleted_tree_records_without_using_schedule_status(tmp_path: Path) -> None:
    kno_path, collection_dir = _write_fixture(tmp_path)
    contents_path = collection_dir / "info" / "contents.dat"
    contents = bytearray(contents_path.read_bytes())
    contents[37] = 1
    contents_path.write_bytes(contents)

    parsed = parse_supermemo_collection(kno_path, collection_dir)

    assert parsed.elements[1].deleted is True
    assert parsed.elements[1].status == 1


def test_import_order_skips_deleted_ancestors_and_reparents_live_children(tmp_path: Path) -> None:
    kno_path, collection_dir = _write_fixture(tmp_path)
    parsed = parse_supermemo_collection(kno_path, collection_dir)
    with_deleted_root = replace(
        parsed,
        elements=(replace(parsed.elements[0], deleted=True), parsed.elements[1]),
    )

    ordered = _ordered_elements(with_deleted_root)

    assert [element.element_id for element in ordered] == [2]
    assert ordered[0].parent_id is None


def test_parser_rejects_registry_member_with_wrong_trailer_identity(tmp_path: Path) -> None:
    kno_path, collection_dir = _write_fixture(tmp_path)
    memory = (collection_dir / "registry" / "Text.mem").read_bytes()
    offset = struct.unpack_from("<I", memory, 10)[0] - 1
    length = struct.unpack_from("<I", memory, 14)[0]
    text_path = collection_dir / "registry" / "Text.rtx"
    registry = bytearray(text_path.read_bytes())
    struct.pack_into("<I", registry, offset + length - 5, 999)
    text_path.write_bytes(registry)

    with pytest.raises(SuperMemoFormatError, match="registry member identity"):
        parse_supermemo_collection(kno_path, collection_dir)


def test_registry_member_with_zero_offset_ignores_stale_length(tmp_path: Path) -> None:
    kno_path, collection_dir = _write_fixture(tmp_path)
    memory_path = collection_dir / "registry" / "Text.mem"
    memory = bytearray(memory_path.read_bytes())
    struct.pack_into("<I", memory, 10, 0)
    memory_path.write_bytes(memory)

    parsed = parse_supermemo_collection(kno_path, collection_dir)

    assert parsed.elements[0].title == "Body"


def test_only_lossless_single_omissions_are_selected_for_cloze(tmp_path: Path) -> None:
    kno_path, collection_dir = _write_fixture(tmp_path)
    item = parse_supermemo_collection(kno_path, collection_dir).elements[1]

    assert is_supermemo_cloze_element(
        replace(item, question="Mention a [...]: Gets attention", answer="person")
    )
    assert not is_supermemo_cloze_element(
        replace(item, question="Use [...] and [...]", answer="one combined answer")
    )
    assert not is_supermemo_cloze_element(
        replace(item, question="Missing [...]", answer="")
    )


def test_rich_html_keeps_formatting_but_removes_active_content() -> None:
    cleaned = _sanitize_rich_html(
        '<p class="lead" style="color:red;background:url(file:///secret)">'
        '<strong onclick="steal()">Formatted</strong>'
        '<a href="javascript:steal()">bad link</a>'
        '<script>steal()</script></p>'
    )

    assert '<p class="lead" style="color:red;background:">' in cleaned
    assert "<strong>Formatted</strong>" in cleaned
    assert "bad link</a>" in cleaned
    assert "script" not in cleaned
    assert "onclick" not in cleaned
    assert "javascript" not in cleaned


def test_zip_extraction_rejects_traversal_and_symlink_entries(tmp_path: Path) -> None:
    archive = tmp_path / "hostile.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.Kno", b"bad")

    with pytest.raises(SuperMemoFormatError, match="unsafe path"):
        extract_supermemo_archive(archive, tmp_path / "out")
    assert not (tmp_path / "escape.Kno").exists()


def test_optimization_archive_is_lossless_and_manifested(tmp_path: Path) -> None:
    kno_path, collection_dir = _write_fixture(tmp_path)
    parsed = parse_supermemo_collection(kno_path, collection_dir)
    destination = tmp_path / "preserved"

    manifest_path = write_optimization_archive(parsed, destination)

    manifest = json.loads(manifest_path.read_text("utf-8"))
    assert [entry["path"] for entry in manifest["files"]] == [
        "alg17/Recall.dat",
        "info/sm8opt.dat",
    ]
    assert (destination / "alg17" / "Recall.dat").read_bytes() == b"recall-matrix"
    assert manifest["files"][0]["sha256"] == hashlib.sha256(b"recall-matrix").hexdigest()
