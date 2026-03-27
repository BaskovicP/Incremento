try:
    from ..backend.pdf_manager import *
except ImportError:
    from pdf_manager import *  # noqa: F401, F403
