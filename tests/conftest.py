import sys
import os
import types
from unittest.mock import MagicMock

# Mock Anki modules before any project code is imported
for mod in ("anki", "anki.cards", "aqt", "aqt.utils", "aqt.qt"):
    sys.modules.setdefault(mod, MagicMock())

# Mock incremento sub-modules so that __init__.py can resolve relative imports.
# These must be MagicMock so attribute access auto-creates stubs.
for mod_name in ("incremento.utils", "incremento.utils.cards",
                 "incremento.utils.statistics", "incremento.utils.stats_dialog",
                 "incremento.utils.timer_widget", "incremento.utils.pdf_dock",
                 "incremento.utils.add_card_dock", "incremento.utils.video_dock",
                 "incremento.utils.web_dock", "incremento.utils.session"):
    sys.modules.setdefault(mod_name, MagicMock())

# Use a plain ModuleType for the package itself — NOT a MagicMock — so that
# pytest's plugin discovery does `getattr(mod, "pytest_plugins", [])` and gets
# the default [] instead of an auto-created MagicMock attribute.
sys.modules.setdefault("incremento", types.ModuleType("incremento"))

# Add utils/ to path so `import scheduler` and `import cards` resolve directly
utils_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "utils"))
sys.path.insert(0, utils_dir)
