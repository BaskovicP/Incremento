"""Bounded, inert passage anchors shared by the PDF and EPUB link repositories."""
import json
import math


def normalize_passage(value, kind='pdf'):
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - {'quote', 'prefix', 'suffix', 'rects', 'start', 'end'}:
        raise ValueError('Invalid passage')
    result = {}
    for key, limit in (('quote', 2000), ('prefix', 160), ('suffix', 160)):
        if key in value:
            text = value[key]
            if not isinstance(text, str) or len(text) > limit or '\0' in text:
                raise ValueError('Invalid passage text')
            result[key] = text
    if 'rects' in value:
        rects = value['rects']
        if kind != 'pdf' or not isinstance(rects, list) or len(rects) > 64:
            raise ValueError('Invalid passage rectangles')
        result['rects'] = []
        for rect in rects:
            if (not isinstance(rect, list) or len(rect) != 4
                    or any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 1 for n in rect)
                    or rect[2] <= 0 or rect[3] <= 0 or rect[0] + rect[2] > 1.000001
                    or rect[1] + rect[3] > 1.000001):
                raise ValueError('Invalid passage rectangle')
            result['rects'].append(list(rect))
    if 'start' in value or 'end' in value:
        start, end = value.get('start'), value.get('end')
        if (kind != 'epub' or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= 50_000_000):
            raise ValueError('Invalid passage range')
        result.update(start=start, end=end)
    return result


def encode_passage(value, kind='pdf'):
    return json.dumps(normalize_passage(value, kind), ensure_ascii=False, separators=(',', ':'))


def decode_passage(value, kind='pdf'):
    try:
        if not isinstance(value, str) or len(value) > 16000:
            return {}
        return normalize_passage(json.loads(value), kind)
    except (ValueError, TypeError):
        return {}


def parse_epub_reference(command):
    """Read legacy position-only commands and new inert passage payloads."""
    prefix = 'incremento_open_epub:'
    if not isinstance(command, str) or not command.startswith(prefix) or len(command) > 24000:
        return None
    try:
        raw = command[len(prefix):]
        if raw.startswith('{'):
            data = json.loads(raw)
            if (not isinstance(data, dict) or set(data) - {'card_id', 'section_index', 'focus_offset', 'scroll_ratio', 'passage'}
                    or any(type(data.get(key)) is not int for key in ('card_id', 'section_index', 'focus_offset'))):
                return None
        else:
            parts = raw.split(':')
            if len(parts) not in (3, 4):
                return None
            data = dict(card_id=int(parts[0]), section_index=int(parts[1]), focus_offset=int(parts[2]),
                        scroll_ratio=float(parts[3]) if len(parts) == 4 else None)
        ratio = data.get('scroll_ratio')
        if (not 0 < data['card_id'] <= 2**53 - 1 or not 0 <= data['section_index'] <= 1_000_000
                or not -1 <= data['focus_offset'] <= 50_000_000
                or (ratio is not None and (type(ratio) not in (int, float) or not math.isfinite(ratio) or not 0 <= ratio <= 1))):
            return None
        result = {key: data.get(key) for key in ('card_id', 'section_index', 'focus_offset', 'scroll_ratio')}
        passage = normalize_passage(data.get('passage'), 'epub')
        if passage:
            result['passage'] = passage
        return result
    except (ValueError, TypeError, KeyError, OverflowError):
        return None
