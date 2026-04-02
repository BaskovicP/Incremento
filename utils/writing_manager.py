try:
    from ..backend.writing_manager import *
except ImportError:
    from writing_manager import *  # noqa: F401, F403
