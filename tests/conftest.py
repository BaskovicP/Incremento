import sys
import os
import types
from unittest.mock import MagicMock

# Mock Anki modules before any project code is imported
for mod in ("anki", "anki.cards", "aqt", "aqt.utils", "aqt.qt"):
    sys.modules.setdefault(mod, MagicMock())

# Mock incremento sub-modules so that __init__.py can resolve relative imports.
# These must be MagicMock so attribute access auto-creates stubs.
for mod_name in ("incremento.backend", "incremento.backend.cards",
                 "incremento.backend.statistics", "incremento.backend.session",
                 "incremento.frontend", "incremento.frontend.stats_dialog"):
    sys.modules.setdefault(mod_name, MagicMock())

# Use a plain ModuleType for the package itself — NOT a MagicMock — so that
# pytest's plugin discovery does `getattr(mod, "pytest_plugins", [])` and gets
# the default [] instead of an auto-created MagicMock attribute.
sys.modules.setdefault("incremento", types.ModuleType("incremento"))

# Add backend/ and frontend/ to path so direct imports resolve.
# Insert in reverse priority order so backend/ ends up first (highest priority).
addon_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for subdir in ("frontend", "backend"):
    path = os.path.join(addon_root, subdir)
    if path not in sys.path:
        sys.path.insert(0, path)
# Final sys.path order: backend/ → frontend/ → …
