try:
    from ..backend.video_manager import *
except ImportError:
    from video_manager import *  # noqa: F401, F403
