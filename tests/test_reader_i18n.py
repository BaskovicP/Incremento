"""Reader labels are resolved when a dock is built, after startup locale setup."""

import reader_shell


def test_reader_shell_labels_and_accessibility_follow_active_locale(monkeypatch):
    messages = {
        "reader_back": "Natrag",
        "reader_search": "Pretraži",
        "reader_extract": "Izdvoji",
        "reader_bookmark": "Označi mjesto",
        "reader_review_all": "Pregledaj sve",
        "reader_pdf_name": "PDF",
        "reader_accessible_name": "{reader} čitač: {action}",
        "reader_accessible_description": "Radnja {action} u čitaču {reader}.",
        "reader_tooltip": "{action} u čitaču {reader}",
    }
    monkeypatch.setattr(
        reader_shell,
        "_t",
        lambda key, **values: messages.get(key, reader_shell._ENGLISH_MESSAGES[key]).format(**values),
    )

    class Button:
        def setText(self, value):
            self.text = value

        def setAccessibleName(self, value):
            self.accessible_name = value

        def setAccessibleDescription(self, value):
            self.accessible_description = value

        def setToolTip(self, value):
            self.tooltip = value

        def setProperty(self, _name, _value):
            pass

    button = Button()
    reader_shell.configure_reader_shell_buttons("pdf", {"back": button})

    assert button.text == "Natrag"
    assert button.accessible_name == "PDF čitač: Natrag"
    assert button.accessible_description == "Radnja Natrag u čitaču PDF."
    assert button.tooltip == "Natrag u čitaču PDF"


def test_epub_toolbar_labels_resolve_at_call_time(monkeypatch):
    monkeypatch.setattr(
        reader_shell,
        "_t",
        lambda key, **values: {
            "reader_navigation": "Navigacija",
            "reader_previous_page": "← Prethodna",
        }.get(key, reader_shell._ENGLISH_MESSAGES[key]).format(**values),
    )

    spec = reader_shell.reader_toolbar_clone_spec("epub")
    labels = reader_shell.reader_toolbar_action_text("epub")

    assert spec[0][1] == "Navigacija"
    assert labels["previous_page"] == "← Prethodna"
