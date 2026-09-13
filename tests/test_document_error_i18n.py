"""Expected document failures stay actionable in the selected UI language."""

import io
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.i18n import Translator
import epub_manager
import pdf_manager
import webpage_markdown


@pytest.mark.parametrize("kind,manager", [("pdf", pdf_manager), ("epub", epub_manager)])
@pytest.mark.parametrize("stage", ["card", "note", "filename", "file"])
@pytest.mark.parametrize("locale", ["hr", "zh-Hans"])
def test_cover_validation_translates_failure_without_mutation(
    tmp_path, monkeypatch, kind, manager, stage, locale,
):
    monkeypatch.setattr(manager, "t", Translator(locale).t, raising=False)
    upper = kind.upper()
    note = {f"{upper}_Filename": "" if stage == "filename" else f"my-file.{kind}",
            f"{upper}_Cover_Image": "existing-cover.png"}
    col = MagicMock()
    col.get_card.return_value = None if stage == "card" else SimpleNamespace(nid=77)
    col.get_note.return_value = None if stage == "note" else note
    stored = str(tmp_path / "TestProfile" / f"{kind}s" / f"my-file.{kind}")
    monkeypatch.setattr(manager, f"{kind}_storage_abspath", lambda _filename: stored)
    expected = {
        "hr": {
            "card": f"{upper} kartica nije pronađena.",
            "note": f"Povezana {upper} bilješka nije pronađena.",
            "filename": f"Ova {upper} bilješka nema spremljen naziv {upper} datoteke.",
            "file": f"Spremljena {upper} datoteka nije pronađena:\n{stored}",
        },
        "zh-Hans": {
            "card": f"未找到 {upper} 卡片。",
            "note": f"未找到关联的 {upper} 笔记。",
            "filename": f"此 {upper} 笔记未保存 {upper} 文件名。",
            "file": f"未找到已保存的 {upper} 文件：\n{stored}",
        },
    }[locale][stage]
    error_type = FileNotFoundError if stage == "file" else RuntimeError
    with pytest.raises(error_type) as exc:
        getattr(manager, f"regenerate_{kind}_card_cover")(str(tmp_path), col, 42)
    assert str(exc.value) == expected
    assert note[f"{upper}_Cover_Image"] == "existing-cover.png"
    col.update_note.assert_not_called()
    col.media.add_file.assert_not_called()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("locale", "empty", "unreadable", "download_empty"),
    [("hr", "HTML web-stranice je prazan.", "Nije moguće izdvojiti čitljiv sadržaj web-stranice.", "Preuzimanje web-stranice vratilo je prazan odgovor."),
     ("zh-Hans", "网页 HTML 为空。", "无法从网页提取可读内容。", "网页下载返回了空响应。")],
)
def test_webpage_extraction_errors_translate_while_exception_classes_remain_stable(
    monkeypatch, locale, empty, unreadable, download_empty,
):
    monkeypatch.setattr(webpage_markdown, "t", Translator(locale).t, raising=False)
    with pytest.raises(ValueError) as exc:
        webpage_markdown.convert_webpage_html_to_markdown("https://example.com/", " ")
    assert str(exc.value) == empty
    with pytest.raises(ValueError) as exc:
        webpage_markdown.convert_webpage_html_to_markdown("https://example.com/", "<main></main>")
    assert str(exc.value) == unreadable
    response = io.BytesIO(b"")
    response.headers = {}
    monkeypatch.setattr(webpage_markdown, "open_public_http", lambda *_args, **_kwargs: response)
    with pytest.raises(RuntimeError) as exc:
        webpage_markdown.fetch_webpage_markdown("https://example.com/")
    assert str(exc.value) == download_empty
