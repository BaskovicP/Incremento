"""Website tag preferences are opt-in, bounded, and isolated by Anki profile."""

import sqlite3
import json

import db
import pytest
from db_schema import initialize_schema


@pytest.fixture
def addon_dir(tmp_path):
    yield str(tmp_path)
    db.close_connection()


def test_remembered_tags_follow_hostname_across_pages_and_database_reopen(addon_dir):
    assert db.get_website_tags(addon_dir, "A", "https://Example.org/one") == {
        "site": "example.org", "enabled": False, "tags": [],
    }
    db.set_website_tags(addon_dir, "A", "https://Example.org/one?private=yes", True,
                        ["Research", "topic", "research"])
    db.close_connection()
    assert db.get_website_tags(addon_dir, "A", "http://example.org/two#section") == {
        "site": "example.org", "enabled": True, "tags": ["Research", "topic"],
    }
    conn = db.get_connection(addon_dir, "A")
    assert conn.execute("SELECT site FROM browser_website_tags").fetchall() == [("example.org",)]


def test_other_sites_subdomains_and_profiles_do_not_inherit_tags(addon_dir):
    db.set_website_tags(addon_dir, "A", "https://example.org", True, ["saved"])
    for profile, url in [("B", "https://example.org"), ("A", "https://other.org"),
                         ("A", "https://sub.example.org")]:
        assert db.get_website_tags(addon_dir, profile, url)["tags"] == []


def test_maximum_unicode_tag_set_and_international_hostname_round_trip(addon_dir):
    tags = [f"{index:02}" + "😀" * 198 for index in range(100)]
    db.set_website_tags(addon_dir, "A", "https://Bücher.example./one", True, tags)
    assert db.get_website_tags(addon_dir, "A", "http://xn--bcher-kva.example/two") == {
        "site": "xn--bcher-kva.example", "enabled": True, "tags": tags,
    }


def test_edit_empty_and_disable_replace_or_forget_only_current_website(addon_dir):
    db.set_website_tags(addon_dir, "A", "https://example.org", True, ["old"])
    db.set_website_tags(addon_dir, "A", "https://other.org", True, ["other"])
    db.set_website_tags(addon_dir, "A", "https://example.org", True, [])
    assert db.get_website_tags(addon_dir, "A", "https://example.org")["enabled"] is True
    assert db.get_website_tags(addon_dir, "A", "https://example.org")["tags"] == []
    db.set_website_tags(addon_dir, "A", "https://example.org", False, [])
    assert db.get_website_tags(addon_dir, "A", "https://example.org")["enabled"] is False
    assert db.get_website_tags(addon_dir, "A", "https://other.org")["tags"] == ["other"]


@pytest.mark.parametrize("url", ["file:///tmp/a", "javascript:alert(1)", "https://u:p@example.org",
                                     "https://example.org/\nsecret", "https://bad%host/", "x" * 8193])
def test_unsafe_website_input_has_no_side_effects(addon_dir, url):
    with pytest.raises(ValueError):
        db.set_website_tags(addon_dir, "A", url, True, ["tag"])
    assert db.get_connection(addon_dir, "A").execute(
        "SELECT count(*) FROM browser_website_tags"
    ).fetchone()[0] == 0


@pytest.mark.parametrize("enabled,tags", [("true", []), (True, ["x"] * 101),
                                          (True, ["x" * 201]), (True, [42]),
                                          (True, ["two words"]), (True, {"bad": "shape"})])
def test_invalid_preferences_preserve_previous_value(addon_dir, enabled, tags):
    db.set_website_tags(addon_dir, "A", "https://example.org", True, ["original"])
    with pytest.raises(ValueError):
        db.set_website_tags(addon_dir, "A", "https://example.org", enabled, tags)
    assert db.get_website_tags(addon_dir, "A", "https://example.org")["tags"] == ["original"]


def test_website_tag_budget_rejects_new_site_without_losing_existing_sites(addon_dir, monkeypatch):
    monkeypatch.setattr(db, "MAX_REMEMBERED_WEBSITES", 2)
    for host in ["one.org", "two.org"]:
        db.set_website_tags(addon_dir, "A", f"https://{host}", True, ["tag"])
    with pytest.raises(ValueError, match="limit"):
        db.set_website_tags(addon_dir, "A", "https://three.org", True, ["tag"])
    db.set_website_tags(addon_dir, "A", "https://one.org", True, ["updated"])
    assert db.get_website_tags(addon_dir, "A", "https://two.org")["tags"] == ["tag"]


def test_website_tags_migration_rolls_back_table_and_ledger_on_failure():
    conn = sqlite3.connect(":memory:")
    previous = tuple(item for item in db._SCHEMA_MIGRATIONS if item[0] < 13)
    initialize_schema(conn, bootstrap=db._create_tables, migrations=previous)

    def fail(connection):
        db._migration_13_website_tags(connection)
        raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError, match="interrupted"):
        initialize_schema(conn, bootstrap=db._create_tables,
                          migrations=previous + ((13, "website_tags", fail),))
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 12
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='browser_website_tags'").fetchone() is None
    conn.close()


def test_support_summary_reports_only_website_table_shape_and_count(addon_dir):
    import diagnostics

    db.set_website_tags(addon_dir, "A", "https://private-website.example", True, ["private-tag"])
    summary = diagnostics.collect_database_summary(addon_dir, "A")
    assert summary["tables"]["browser_website_tags"] == {
        "present": True, "row_count": 1, "column_count": 2,
    }
    encoded = json.dumps(summary)
    assert "private-website" not in encoded
    assert "private-tag" not in encoded
