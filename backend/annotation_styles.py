"""Controlled text-mark styles shared by PDF and EPUB persistence."""

ANNOTATION_STYLES = ('highlight', 'underline', 'squiggly', 'dashed', 'dotted', 'strikeout')
PDF_STYLE_KINDS = dict(zip(ANNOTATION_STYLES, (
    'Highlight', 'Underline', 'Squiggly', 'Underline', 'Underline', 'StrikeOut',
)))


def normalize_annotation_style(value: object) -> str:
    if not isinstance(value, str) or value not in ANNOTATION_STYLES:
        raise ValueError('Unsupported annotation style')
    return value


def pdf_style_metadata(metadata: dict, style: object) -> dict:
    style = normalize_annotation_style(style)
    result = {**metadata, 'kind': PDF_STYLE_KINDS[style], 'incremento_style': style,
              'opacity': .42 if style == 'highlight' else 1}
    result.pop('quads', None)
    result.pop('xref', None)
    return result
