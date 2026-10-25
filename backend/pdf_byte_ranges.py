"""Read-only byte ranges for one captured, profile-owned PDF snapshot."""
import os
from pathlib import Path
import secrets
import stat

try:
    from . import paths
except ImportError:
    import paths

PDF_RANGE_CHUNK_SIZE = 256 * 1024


def _identity(value):
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


class PdfByteRangeSource:
    def __init__(self, addon_dir, profile, card_id, path):
        candidate = Path(path)
        if candidate.is_symlink():
            raise ValueError('Unsafe PDF path')
        target = candidate.resolve(strict=True)
        profile_root = paths.get_user_files_dir(addon_dir, profile)
        for component in [profile_root.parent, profile_root, candidate, *candidate.parents]:
            if (component == profile_root.parent or component == profile_root
                    or component.is_relative_to(profile_root)) and component.is_symlink():
                raise ValueError('Unsafe PDF path')
        pdf_root = paths.get_pdf_dir(addon_dir, profile).resolve()
        reader = paths.get_pdf_annotation_reader_path(addon_dir, profile, card_id).resolve()
        if target != reader and not target.is_relative_to(pdf_root):
            raise ValueError('PDF belongs to another reader')
        info = target.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
            raise ValueError('Invalid PDF file')
        self.path, self.identity = target, _identity(info)
        self.profile, self.card_id = profile, card_id
        self.descriptor = {'token': secrets.token_urlsafe(24), 'cardId': card_id,
            'length': info.st_size, 'chunkSize': PDF_RANGE_CHUNK_SIZE}

    def read(self, begin, end):
        if (type(begin) is not int or type(end) is not int
                or not 0 <= begin < end <= self.descriptor['length']
                or end - begin > PDF_RANGE_CHUNK_SIZE):
            raise ValueError('Invalid PDF range')
        flags = (os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
            | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0))
        descriptor = os.open(self.path, flags)
        try:
            if _identity(os.fstat(descriptor)) != self.identity:
                raise OSError('PDF snapshot changed')
            os.lseek(descriptor, begin, os.SEEK_SET)
            data = os.read(descriptor, end - begin)
            current = self.path.lstat()
            if (len(data) != end - begin or stat.S_ISLNK(current.st_mode)
                    or _identity(current) != self.identity
                    or _identity(os.fstat(descriptor)) != self.identity):
                raise OSError('PDF snapshot changed')
            return data
        finally:
            os.close(descriptor)
