try:
    from ..frontend.web_dock import *
except ImportError:
    from web_dock import *  # noqa: F401, F403
