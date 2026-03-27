try:
    from ..backend.scheduler_config import *
except ImportError:
    from scheduler_config import *  # noqa: F401, F403
