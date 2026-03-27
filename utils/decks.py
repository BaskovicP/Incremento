try:
    from ..backend.decks import *
except ImportError:
    from decks import *  # noqa: F401, F403
