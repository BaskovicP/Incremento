try:
    from ..backend.scheduler import *
except ImportError:
    from scheduler import *  # noqa: F401, F403
