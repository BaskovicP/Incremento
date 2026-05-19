import importlib.util
import os
import sys
import types


class _Signal:
    def connect(self, _callback):
        return None


class _BaseWidget:
    def __init__(self, *args, **kwargs):
        self._enabled = True

    def setEnabled(self, enabled):
        self._enabled = bool(enabled)

    def isEnabled(self):
        return self._enabled

    def setWordWrap(self, _value):
        return None

    def setFrameShape(self, _value):
        return None

    def setWidgetResizable(self, _value):
        return None

    def setWidget(self, _value):
        return None

    def setContentsMargins(self, *args):
        return None

    def setSpacing(self, _value):
        return None

    def setHorizontalSpacing(self, _value):
        return None

    def setVerticalSpacing(self, _value):
        return None

    def addWidget(self, *args):
        return None

    def addLayout(self, *args):
        return None

    def addStretch(self, *args):
        return None

    def addRow(self, *args):
        return None

    def setToolTip(self, _value):
        return None

    def setPlaceholderText(self, _value):
        return None

    def setMinimumHeight(self, _value):
        return None

    def setMinimumWidth(self, _value):
        return None

    def setMaximumWidth(self, _value):
        return None

    def resize(self, *args):
        return None

    def setWindowTitle(self, _value):
        return None

    def setPixmap(self, _value):
        return None

    def style(self):
        return _Style()

    def accept(self):
        return None

    def reject(self):
        return None

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class _Widget(_BaseWidget):
    pass


class _Dialog(_BaseWidget):
    pass


class _Layout(_BaseWidget):
    pass


class _Label(_BaseWidget):
    def __init__(self, text="", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = text


class _ButtonGroup(_BaseWidget):
    def addButton(self, _button):
        return None


class _CheckBox(_BaseWidget):
    def __init__(self, text="", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = text
        self._checked = False
        self.toggled = _Signal()

    def setChecked(self, value):
        self._checked = bool(value)

    def isChecked(self):
        return self._checked


class _RadioButton(_CheckBox):
    pass


class _LineEdit(_BaseWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._text = ""

    def setText(self, value):
        self._text = str(value)

    def text(self):
        return self._text


class _PlainTextEdit(_BaseWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._text = ""

    def setPlainText(self, value):
        self._text = str(value)

    def toPlainText(self):
        return self._text


class _ComboBox(_BaseWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._items = []
        self._current_index = 0
        self.currentIndexChanged = _Signal()

    def addItem(self, label, data=None):
        self._items.append((label, data))

    def count(self):
        return len(self._items)

    def itemData(self, index):
        return self._items[index][1]

    def setCurrentIndex(self, index):
        self._current_index = int(index)

    def currentData(self):
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index][1]
        return None


class _SpinBase(_BaseWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._min = 0
        self._max = 100
        self._value = 0

    def setRange(self, minimum, maximum):
        self._min = minimum
        self._max = maximum

    def setValue(self, value):
        self._value = max(self._min, min(self._max, value))

    def value(self):
        return self._value

    def minimum(self):
        return self._min

    def maximum(self):
        return self._max

    def setSuffix(self, _value):
        return None


class _DoubleSpinBox(_SpinBase):
    def setDecimals(self, value):
        self._decimals = int(value)

    def decimals(self):
        return getattr(self, "_decimals", 0)

    def setSingleStep(self, value):
        self._step = float(value)

    def singleStep(self):
        return getattr(self, "_step", 0.0)


class _SpinBox(_SpinBase):
    pass


class _PushButton(_BaseWidget):
    def __init__(self, text="", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = text
        self.clicked = _Signal()

    def setText(self, value):
        self.text = str(value)


class _ToolButton(_PushButton):
    def setAutoRaise(self, _value):
        return None


class _TabWidget(_BaseWidget):
    def addTab(self, *args):
        return None


class _ScrollArea(_BaseWidget):
    class Shape:
        NoFrame = 0


class _DialogButtonBox(_BaseWidget):
    class StandardButton:
        Ok = 1
        Cancel = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.accepted = _Signal()
        self.rejected = _Signal()


class _KeySequence:
    class SequenceFormat:
        PortableText = 0

    def __init__(self, text=""):
        self._text = str(text)

    def toString(self, _format=None):
        return self._text


class _KeySequenceEdit(_BaseWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sequence = _KeySequence("")

    def setKeySequence(self, sequence):
        self._sequence = sequence

    def keySequence(self):
        return self._sequence

    def clear(self):
        self._sequence = _KeySequence("")


class _Style:
    class StandardPixmap:
        SP_MessageBoxWarning = 1

    class _Icon:
        def pixmap(self, *_args):
            return None

    def standardIcon(self, _pixmap):
        return self._Icon()


_qt_module = types.ModuleType("aqt.qt")
_qt_module.QButtonGroup = _ButtonGroup
_qt_module.QCheckBox = _CheckBox
_qt_module.QComboBox = _ComboBox
_qt_module.QDialog = _Dialog
_qt_module.QDialogButtonBox = _DialogButtonBox
_qt_module.QFormLayout = _Layout
_qt_module.QGridLayout = _Layout
_qt_module.QHBoxLayout = _Layout
_qt_module.QKeySequence = _KeySequence
_qt_module.QKeySequenceEdit = _KeySequenceEdit
_qt_module.QLabel = _Label
_qt_module.QLineEdit = _LineEdit
_qt_module.QPlainTextEdit = _PlainTextEdit
_qt_module.QPushButton = _PushButton
_qt_module.QRadioButton = _RadioButton
_qt_module.QScrollArea = _ScrollArea
_qt_module.QStyle = _Style
_qt_module.QDoubleSpinBox = _DoubleSpinBox
_qt_module.QSpinBox = _SpinBox
_qt_module.QTabWidget = _TabWidget
_qt_module.QToolButton = _ToolButton
_qt_module.QVBoxLayout = _Layout
_qt_module.QWidget = _Widget

_aqt_module = types.ModuleType("aqt")
_aqt_module.qt = _qt_module
_aqt_module.mw = types.SimpleNamespace(addonManager=None)

sys.modules["aqt"] = _aqt_module
sys.modules["aqt.qt"] = _qt_module


_SPEC = importlib.util.spec_from_file_location(
    "_incremento_settings_dialog",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "frontend", "settings_dialog.py")
    ),
)
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["_incremento_settings_dialog"] = _MOD
_SPEC.loader.exec_module(_MOD)

IncrementoSettingsDialog = _MOD.IncrementoSettingsDialog
default_shortcuts = _MOD.default_shortcuts
SHORTCUT_ACTION_SPECS = _MOD.SHORTCUT_ACTION_SPECS


class TestIncrementoSettingsDialogDefaultTopicAFactor:
    def test_initializes_default_topic_a_factor_spin(self):
        dialog = IncrementoSettingsDialog({}, current_default_topic_a_factor=4.25)
        assert dialog._default_topic_a_factor_spin.value() == 4.25
        assert dialog._default_topic_a_factor_spin.minimum() == 1.1
        assert dialog._default_topic_a_factor_spin.maximum() == 100.0
        assert dialog._default_topic_a_factor_spin.decimals() == 3
        assert dialog._default_topic_a_factor_spin.singleStep() == 0.1

    def test_clamps_out_of_range_default_topic_a_factor(self):
        low = IncrementoSettingsDialog({}, current_default_topic_a_factor=0.5)
        high = IncrementoSettingsDialog({}, current_default_topic_a_factor=250.0)
        assert low.default_topic_a_factor == 1.1
        assert high.default_topic_a_factor == 100.0

    def test_exposes_default_topic_a_factor_for_save(self):
        dialog = IncrementoSettingsDialog({}, current_default_topic_a_factor=3.5)
        dialog._default_topic_a_factor_spin.setValue(6.7894)
        assert dialog.default_topic_a_factor == 6.789


class TestIncrementoSettingsDialogExtractionHighlight:
    def test_highlight_when_extracting_defaults_enabled(self):
        dialog = IncrementoSettingsDialog({})
        assert dialog.extract_highlight_when_extracting is True

    def test_highlight_when_extracting_respects_current_value(self):
        dialog = IncrementoSettingsDialog(
            {},
            current_extract_highlight_when_extracting=False,
        )
        assert dialog.extract_highlight_when_extracting is False


class TestIncrementoSettingsDialogExtractCopySourceTags:
    def test_checkbox_reflects_incoming_value(self):
        dialog = IncrementoSettingsDialog(
            {},
            current_extract_copy_source_tags=True,
        )
        assert dialog._extract_copy_source_tags_cb.isChecked() is True

    def test_property_returns_saved_value(self):
        dialog = IncrementoSettingsDialog({})
        dialog._extract_copy_source_tags_cb.setChecked(True)
        assert dialog.extract_copy_source_tags is True


class TestIncrementoSettingsDialogTimerCompletionBeep:
    def test_checkbox_defaults_enabled(self):
        dialog = IncrementoSettingsDialog({})
        assert dialog.timer_completion_beep is True

    def test_checkbox_reflects_incoming_value(self):
        dialog = IncrementoSettingsDialog(
            {},
            current_timer_completion_beep=False,
        )
        assert dialog._timer_completion_beep_cb.isChecked() is False

    def test_property_returns_saved_value(self):
        dialog = IncrementoSettingsDialog({})
        dialog._timer_completion_beep_cb.setChecked(False)
        assert dialog.timer_completion_beep is False


class TestIncrementoSettingsDialogReviewerButtons:
    def test_fail_pass_defaults_enabled_for_new_profiles(self):
        dialog = IncrementoSettingsDialog({})
        assert dialog.use_fail_pass_on_items is True

    def test_fail_pass_respects_explicit_saved_value(self):
        dialog = IncrementoSettingsDialog({}, current_use_fail_pass_on_items=False)
        assert dialog.use_fail_pass_on_items is False


class TestIncrementoSettingsDialogShortcuts:
    def test_extract_card_shortcut_is_exposed_in_settings(self):
        extract_spec = next(
            spec for spec in SHORTCUT_ACTION_SPECS if spec["id"] == "extract_card"
        )

        assert extract_spec["label"] == "Extract Card"
        assert default_shortcuts()["extract_card"] == "Alt+X"
