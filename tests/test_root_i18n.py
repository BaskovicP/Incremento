"""The composition-root menus use the same catalog as their runtime translator."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.i18n import Translator


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('locale,skip,postpone', [('hr', 'Preskoči', 'Odgodi'), ('zh-Hans', '跳过', '推迟')])
def test_reviewer_question_buttons_translate_labels_and_preserve_commands(locale, skip, postpone):
    source = ast.parse((ROOT / '__init__.py').read_text(encoding='utf-8'))
    node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == '_incremento_show_answer_button')
    emitted = []
    namespace = {
        'json': json, '_t': Translator(locale).t,
        'tr': SimpleNamespace(actions_shortcut_key=lambda val: val, studying_space=lambda: 'Space', studying_show_answer=lambda: 'Native answer'),
        '_reviewer_item_skip_enabled': lambda card: True,
        '_item_skip_due_label': lambda: '2m', '_topic_postpone_due_label': lambda: '1d',
        '_sync_reviewer_extract_button': lambda reviewer: None,
        'mw': SimpleNamespace(pm=SimpleNamespace(get_answer_key=lambda ease: '5')),
        '_TOPIC_POSTPONE_EASE': 5,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<reviewer>', 'exec'), namespace)
    reviewer = SimpleNamespace(card=SimpleNamespace(should_show_timer=lambda: False), _remaining=lambda: '', bottom=SimpleNamespace(web=SimpleNamespace(eval=emitted.append)))
    for topic, label, command in [(False, skip, 'incremento_item_skip'), (True, postpone, 'incremento_topic_postpone')]:
        namespace['_reviewer_topic_postpone_enabled'] = lambda card: topic
        namespace['_incremento_show_answer_button'](reviewer)
        html = json.loads(emitted[-1][len('showQuestion('):].rsplit(',0);', 1)[0])
        assert f'>{label}<span' in html
        assert f'pycmd("{command}")' in html
        assert '>Native answer<' in html


def test_root_menu_labels_translate_without_changing_action_identity():
    source = ast.parse((ROOT / "__init__.py").read_text(encoding="utf-8"))
    menu = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == "_build_incremento_menu")
    labels = [node.args[0] for node in ast.walk(menu)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id in {"QAction", "QMenu"} and node.args]
    assert len(labels) >= 35
    assert all(isinstance(label, ast.Call) and isinstance(label.func, ast.Name)
               and label.func.id == "_t" for label in labels)
    object_names = [node.args[0].value for node in ast.walk(menu)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "setObjectName" and node.args
                    and isinstance(node.args[0], ast.Constant)]
    assert "incremento_menu" in object_names
    assert "incremento_open_settings" in object_names


def test_root_menu_catalogs_translate_settings_and_learning():
    assert Translator("en").t("root_menu_settings") == "Settings"
    assert Translator("hr").t("root_menu_settings") == "Postavke"
    assert Translator("zh-Hans").t("root_menu_settings") == "设置"
    assert Translator("hr").t("root_menu_start_learning") == "Pokreni postupno učenje"
    assert Translator("zh-Hans").t("root_menu_start_learning") == "开始渐进学习"


def test_root_feedback_and_palette_reasons_follow_the_selected_language():
    assert Translator("hr").t("root_browser_select_rows") == "Najprije odaberite jedan ili više redaka u Pregledniku."
    assert Translator("zh-Hans").t("root_reviewer_no_review_card") == "当前没有正在复习的卡片。"
    assert Translator("hr").t("root_palette_open_document") == "Otvorite PDF ili EPUB prije pretrage trenutačnog dokumenta."


def test_browser_context_menu_count_uses_croatian_plural_forms():
    tr = Translator("hr")
    assert tr.tn("root_browser_selected_card", 1) == "1 odabrana kartica"
    assert tr.tn("root_browser_selected_card", 2) == "2 odabrane kartice"
    assert tr.tn("root_browser_selected_card", 5) == "5 odabranih kartica"
    assert Translator("zh-Hans").t("root_browser_study_selected", count_label="3 张已选卡片") == "学习所选卡片（3 张已选卡片）"


def test_browser_operation_feedback_translates_counts_and_progress():
    tr = Translator("hr")
    assert tr.tn("root_browser_cards_to_topics", 1) == "1 odabrana kartica pretvorena u temu"
    assert tr.tn("root_browser_cards_to_topics", 3) == "3 odabrane kartice pretvorene u teme"
    assert tr.tn("root_browser_cards_to_topics", 5) == "5 odabranih kartica pretvoreno u teme"
    assert tr.t("root_browser_cover_progress_pdf", index=2, total=8) == "(2/8) Obnavljanje omota PDF-ova…"
    source = (ROOT / "__init__.py").read_text(encoding="utf-8")
    assert "f\"Converted {changed_count}" not in source
    assert "f\"Regenerated {regenerated}" not in source


def test_direct_review_and_database_inspection_feedback_is_translated():
    tr = Translator("hr")
    assert tr.t("root_browser_database_read_failed", error="disk") == "Nije moguće pročitati zapise baze Incremento:\ndisk"
    assert tr.tn("root_browser_review_skipped", 3) == "Preskočene su 3 nedostupne kartice."
    assert Translator("zh-Hans").t("root_browser_review_start_failed", error="failure") == "无法开始学习所选卡片：\nfailure"
    source = (ROOT / "__init__.py").read_text(encoding="utf-8")
    assert "Review Selected is unavailable with this Anki reviewer version." not in source


def test_note_format_and_about_messages_are_localized():
    tr = Translator("hr")
    assert tr.t("root_note_formats_current") == "Svi postojeći formati kartica Incremento ažurni su."
    assert Translator("zh-Hans").t("root_about_author") == "作者："
    source = (ROOT / "__init__.py").read_text(encoding="utf-8")
    assert 'showInfo("All existing Incremento card formats are up to date.")' not in source
    assert '<p><b>Author:</b>' not in source


def test_import_and_reviewer_feedback_uses_localized_messages():
    tr = Translator("hr")
    assert tr.t("root_video_choose_file") == "Odaberite lokalnu videodatoteku."
    assert tr.t("root_writing_enter_title") == "Unesite naslov."
    assert tr.t("root_reviewer_tags_added", tags="a, b") == "Dodane oznake: a, b"
    source = (ROOT / "__init__.py").read_text(encoding="utf-8")
    assert 'showInfo("Please choose a local video file.")' not in source


def test_pdf_import_and_ocr_statuses_are_localized():
    tr = Translator("hr")
    assert tr.tn("root_import_pdf_added", 2, deck="Deck") == "Dodane 2 PDF kartice → Deck"
    assert tr.t("root_ocr_scanned", count=4) == "Pregledane bilješke: 4"
    assert Translator("zh-Hans").t("root_pdf_reindex_failed", error="bad") == "PDF 文本重建索引失败：\nbad"


def test_backup_and_support_bundle_feedback_is_localized():
    tr = Translator("hr")
    assert tr.t("root_backup_full_title") == "Potpuna sigurnosna kopija"
    assert tr.t("root_backup_saved") == "Potpuna sigurnosna kopija spremljena je. Pojedinosti su u Centru aktivnosti."
    assert Translator("zh-Hans").t("root_support_progress") == "正在创建保护隐私的支持包…"


def test_settings_and_cleanup_summaries_are_localized():
    tr = Translator("hr")
    assert tr.t("root_settings_updated") == "Postavke Incrementa su ažurirane."
    assert tr.t("root_cleanup_stale_none") == "Nisu pronađeni zastarjeli redci napretka, indeksa pretrage ni OCR predmemorije."
    assert Translator("zh-Hans").t("root_cleanup_progress_summary", total=2, pdf=1, video=1, web=0).startswith("已删除过期进度记录：2")


def test_orphan_cleanup_prompts_translate_without_changing_file_values():
    tr = Translator("hr")
    assert tr.t("root_cleanup_pdf_none", path="/tmp/user.pdf") == "U /tmp/user.pdf nisu pronađene PDF datoteke."
    assert Translator("zh-Hans").t("root_cleanup_delete_files") == "删除这些文件吗？"
    source = (ROOT / "__init__.py").read_text(encoding="utf-8")
    assert 'title="Clean Up Orphaned PDFs"' not in source
