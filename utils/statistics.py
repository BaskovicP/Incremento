try:
    from ..backend.statistics import *
except ImportError:
    from statistics import *  # noqa: F401, F403
