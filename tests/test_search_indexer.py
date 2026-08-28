import db
import search_indexer


def test_pdf_indexer_persists_state_and_skips_unchanged_file(tmp_path):
    addon_dir = str(tmp_path / "addon")
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"pdf")
    calls = []

    def extract(path, **_kwargs):
        calls.append(path)
        return ["searchable page"]

    first = search_indexer.index_pdf_documents(
        addon_dir, "Profile", [(10, str(pdf))], extractor=extract
    )
    second = search_indexer.index_pdf_documents(
        addon_dir, "Profile", [(10, str(pdf))], extractor=extract
    )

    assert first.indexed == 1
    assert second.skipped == 1
    assert calls == [str(pdf)]
    assert db.search_pdf_text_index(addon_dir, "Profile", "searchable")[0][:2] == (10, 1)


def test_pdf_indexer_honors_cancellation_between_files(tmp_path):
    addon_dir = str(tmp_path / "addon")
    documents = []
    for index in range(2):
        path = tmp_path / f"{index}.pdf"
        path.write_bytes(b"pdf")
        documents.append((index + 1, str(path)))
    calls = []

    def extract(path, **_kwargs):
        calls.append(path)
        return ["text"]

    result = search_indexer.index_pdf_documents(
        addon_dir,
        "Profile",
        documents,
        extractor=extract,
        cancelled=lambda: len(calls) >= 1,
    )

    assert result.cancelled is True
    assert result.indexed == 1
    assert len(calls) == 1


def test_forced_pdf_index_reextracts_unchanged_file(tmp_path):
    addon_dir = str(tmp_path / "addon")
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"pdf")
    calls = []

    def extract(path, **_kwargs):
        calls.append(path)
        return [f"version {len(calls)}"]

    search_indexer.index_pdf_documents(
        addon_dir, "Profile", [(10, str(pdf))], extractor=extract
    )
    search_indexer.index_pdf_documents(
        addon_dir,
        "Profile",
        [(10, str(pdf))],
        extractor=extract,
        force=True,
    )

    assert len(calls) == 2
    assert "version 2" in db.search_pdf_text_index(
        addon_dir, "Profile", "version"
    )[0][2]


def test_legacy_index_without_source_signature_is_refreshed_once(tmp_path):
    addon_dir = str(tmp_path / "addon")
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"new pdf")
    db.replace_pdf_text_index(addon_dir, "Profile", 10, ["stale legacy text"])
    calls = []

    def extract(path, **_kwargs):
        calls.append(path)
        return ["fresh indexed text"]

    first = search_indexer.index_pdf_documents(
        addon_dir,
        "Profile",
        [(10, str(pdf))],
        extractor=extract,
    )
    second = search_indexer.index_pdf_documents(
        addon_dir,
        "Profile",
        [(10, str(pdf))],
        extractor=extract,
    )

    assert first.indexed == 1
    assert second.skipped == 1
    assert calls == [str(pdf)]
    assert db.search_pdf_text_index(
        addon_dir, "Profile", "fresh"
    )[0][2] == "fresh indexed text"
