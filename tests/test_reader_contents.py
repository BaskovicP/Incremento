from backend.reader_contents import epub_contents, normalize_contents_entries


def test_epub_contents_preserve_nested_fragment_targets_and_reject_escaping_links(tmp_path):
    (tmp_path / "book").mkdir()
    (tmp_path / "book/package.opf").write_text('''<package><manifest>
      <item href="nav.xhtml" properties="nav"/>
    </manifest></package>''')
    (tmp_path / "book/nav.xhtml").write_text('''<nav epub:type="landmarks"><a href="one.xhtml">Wrong list</a></nav>
      <nav epub:type="toc"><ol><li><a href="one.xhtml">Chapter</a><ol>
      <li><a href="one.xhtml#detail">Detail</a></li></ol></li>
      <li><a href="../../outside.xhtml">Escape</a></li>
      <li><a href="https://example.com/">Remote</a></li>
      <li><a href="missing.xhtml">Missing</a></li></ol></nav>''')
    (tmp_path / "book/one.xhtml").write_text('<h1>Chapter</h1><h2 id="detail">Detail</h2>')
    entries = epub_contents(tmp_path, {"opf_relpath": "book/package.opf", "sections": [{"href": "book/one.xhtml", "title": "One"}]})
    assert entries == [
        {"title": "Chapter", "depth": 0, "section_index": 0, "fragment": ""},
        {"title": "Detail", "depth": 1, "section_index": 0, "fragment": "detail"},
    ]


def test_epub_contents_support_legacy_ncx_and_section_fallback(tmp_path):
    (tmp_path / "package.opf").write_text('''<package><manifest><item href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest></package>''')
    (tmp_path / "one.xhtml").write_text('<h1>One</h1>')
    (tmp_path / "toc.ncx").write_text('''<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://example.invalid/ncx.dtd">
      <ncx><navMap><navPoint><navLabel><text>One</text></navLabel><content src="one.xhtml"/>
      <navPoint><navLabel><text>Part</text></navLabel><content src="one.xhtml#part"/></navPoint></navPoint></navMap></ncx>''')
    metadata = {"opf_relpath": "package.opf", "sections": [{"href": "one.xhtml", "title": "Section"}]}
    assert [(e["title"], e["depth"], e["fragment"]) for e in epub_contents(tmp_path, metadata)] == [("One", 0, ""), ("Part", 1, "part")]
    (tmp_path / "toc.ncx").unlink()
    assert epub_contents(tmp_path, metadata) == [{"title": "Section", "depth": 0, "section_index": 0, "fragment": ""}]


def test_contents_reject_symlinked_files_and_bound_bridge_entries(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "nav.xhtml").write_text('<nav><a href="one.xhtml">Secret</a></nav>')
    root = tmp_path / "root"
    root.mkdir()
    (root / "package.opf").write_text('<package><manifest><item href="nav.xhtml" properties="nav"/></manifest></package>')
    (root / "nav.xhtml").symlink_to(outside / "nav.xhtml")
    assert epub_contents(root, {"opf_relpath": "package.opf", "sections": []}) == []
    assert normalize_contents_entries([{"title": "Bad", "page": -1}, {"title": "Safe <title>", "page": 2, "depth": 999}], "pdf", 10) == [
        {"title": "Safe <title>", "depth": 12, "page": 2, "id": 1}
    ]
