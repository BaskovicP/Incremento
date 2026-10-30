"""Display-only cleanup for imported bibliographic filenames; stored titles stay intact."""
import re


def display_resource_title(raw):
    text = ' '.join(str(raw or '').split())
    clean = re.sub(r'\s+libgen\.[a-z.]+\s*$', '', text, flags=re.I)
    if clean != text:
        clean = re.sub(r'(?:\s*(?:\{[^{}]{0,240}\}|\([^()]{0,240}\))){2,8}\s*$', '', clean).strip()
        if clean.startswith('[') and ']' in clean:
            candidate = clean.split(']', 1)[1].strip(' -·')
            if len(candidate) >= 3:
                clean = candidate
    return clean or text
