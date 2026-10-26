"""Shared presentation states for the reviewer and native study tabs."""
try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t


def resource_availability(items, *, present=False, failed=False):
    count = sum(bool(item.get('available')) for item in (items or []))
    if count or present:
        return dict(availability='ready', status=t('study_linked_count', count=max(1, count)), disabled=False)
    state = 'error' if failed else 'loading' if items is None else 'unavailable' if items else 'empty'
    key = dict(error='study_check_failed', loading='study_checking', unavailable='study_unavailable', empty='study_not_linked')[state]
    return dict(availability=state, status=t(key), disabled=True)


def card_availability(present):
    return dict(availability='ready' if present else 'empty',
                status=t('study_available' if present else 'study_no_card'), disabled=not present)
