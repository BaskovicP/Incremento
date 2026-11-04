"""Session-only return locations for explicit cross-document passage visits."""
from copy import deepcopy


class ReaderReturnHistory:
    def __init__(self):
        self.profile = None
        self.entries = []

    def clear(self):
        self.entries.clear()
        self.profile = None

    def available(self, profile):
        if profile != self.profile:
            self.clear()
        return bool(self.entries)

    def push(self, profile, location):
        self.available(profile)
        self.profile = profile
        self.entries = [*self.entries, deepcopy(location)][-50:]

    def pop(self, profile):
        return self.entries.pop() if self.available(profile) else None
