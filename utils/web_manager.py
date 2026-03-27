try:
    from ..backend.web_manager import *
except ImportError:
    from web_manager import *  # noqa: F401, F403
