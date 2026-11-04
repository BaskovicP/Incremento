"""Saved workspaces are bounded, profile-local data, never executable commands."""
from copy import deepcopy
import base64

import pytest

import config_service


def snapshot():
    return {'version': 1, 'state': base64.b64encode(b'Qt layout').decode(),
            'geometry': base64.b64encode(b'Qt geometry').decode(), 'panes': [
                {'name': 'incremento_pdf_dock', 'kind': 'pdf', 'card_id': 42,
                 'focused': True, 'page': 17, 'zoom': 1.5, 'scroll': .3,
                 'controls': {'collapsed': False, 'groups': {'reading': False}}},
                {'name': 'incremento_writing_dock', 'kind': 'writing', 'card_id': 71,
                 'controls': {'preview': False, 'wrap': True}}]}


def test_named_workspaces_survive_config_round_trip_without_crossing_profiles():
    raw = {'workspace_layouts': {'A': {'Reading': snapshot()}, 'B': {'Writing': snapshot()}},
           'future_setting': {'keep': True}}
    before = deepcopy(raw)
    normalized = config_service.normalize_config(raw)
    assert normalized['workspace_layouts'] == before['workspace_layouts']
    assert config_service.normalize_config(normalized) == normalized
    assert raw == before
    from workspace_layouts import saved_workspaces
    assert saved_workspaces(normalized, 'A') == {'Reading': snapshot()}
    assert saved_workspaces(normalized, 'missing') == {}
    assert normalized['future_setting'] == {'keep': True}


@pytest.mark.parametrize('change', [
    {'version': 9}, {'state': 'not base64'}, {'state': 'A' * 400_000},
    {'panes': []}, {'panes': [{'name': 'another_addon', 'kind': 'pdf', 'card_id': 42}]},
    {'panes': [{'name': 'incremento_pdf_dock', 'kind': 'writing', 'card_id': 42}]},
    {'panes': [{'name': 'incremento_pdf_dock', 'kind': 'pdf', 'card_id': True}]},
])
def test_invalid_workspace_is_rejected_without_losing_other_saved_layouts(change):
    from workspace_layouts import saved_workspaces
    bad = snapshot() | change
    config = config_service.normalize_config({'workspace_layouts': {'A': {'Good': snapshot(), 'Bad': bad}}})
    assert saved_workspaces(config, 'A') == {'Good': snapshot()}


def test_workspace_panes_discard_content_paths_and_untrusted_ui_values():
    from workspace_layouts import normalize_workspace
    raw = snapshot()
    raw['panes'][0].update(filename='/private/content.pdf', html='<script>secret</script>',
                           scroll=float('nan'), zoom=float('inf'))
    raw['panes'][0]['controls'].update(script='alert(1)', collapsed='false', groups={'reading': 'false'})
    clean = normalize_workspace(raw)
    assert 'filename' not in clean['panes'][0]
    assert 'html' not in clean['panes'][0]
    assert 'scroll' not in clean['panes'][0] and 'zoom' not in clean['panes'][0]
    assert clean['panes'][0]['controls'] == {'groups': {}}


def test_duplicate_pane_names_and_excessive_reference_windows_are_rejected():
    from workspace_layouts import normalize_workspace
    raw = snapshot()
    raw['panes'].append(deepcopy(raw['panes'][0]))
    assert normalize_workspace(raw) is None


def test_saved_writing_tabs_keep_order_and_active_card_without_persisting_content():
    from workspace_layouts import normalize_workspace
    raw = snapshot()
    raw['panes'][1]['writing_tabs'] = [80, 71, 99]
    raw['panes'][1]['draft_text'] = 'Must never enter workspace config'
    clean = normalize_workspace(raw)
    assert clean['panes'][1]['writing_tabs'] == [80, 71, 99]
    assert clean['panes'][1]['card_id'] == 71
    assert 'draft_text' not in clean['panes'][1]


@pytest.mark.parametrize('label,expected', [
    ('My reading tab', 'My reading tab'), ('  Notes & passages  ', 'Notes & passages'),
    ('x'*80, 'x'*80), ('x'*81, None), ('', None), ('bad\nlabel', None), (42, None),
])
def test_saved_workspace_tab_names_are_bounded_display_labels(label, expected):
    from workspace_layouts import normalize_workspace
    raw = snapshot()
    raw['panes'][0]['tab_name'] = label
    clean = normalize_workspace(raw)
    assert clean['panes'][0].get('tab_name') == expected
    assert clean['panes'][0]['card_id'] == 42
    assert clean['panes'][0]['name'] == 'incremento_pdf_dock'


@pytest.mark.parametrize('size,color,expected_size,expected_color', [
    ([180, 36], '#A1b2C3', [180, 36], '#a1b2c3'),
    ([80, 24], '#000000', [80, 24], '#000000'),
    ([480, 80], '#ffffff', [480, 80], '#ffffff'),
    ([79, 36], 'red', None, None),
    ([180, 81], '#12345678', None, None),
    ([True, 36], 'url(secret)', None, None),
    ([180, 36, 50], '#12345g', None, None),
    ('180x36', None, None, None),
])
def test_saved_tab_appearance_keeps_only_bounded_dimensions_and_opaque_hex_colors(
        size, color, expected_size, expected_color):
    from workspace_layouts import normalize_workspace
    raw = snapshot()
    raw['panes'][0].update(tab_size=size, tab_color=color)
    before = deepcopy(raw)
    clean = normalize_workspace(raw)
    assert clean['panes'][0].get('tab_size') == expected_size
    assert clean['panes'][0].get('tab_color') == expected_color
    assert normalize_workspace(clean) == clean
    assert raw == before


@pytest.mark.parametrize('mode', [True, False, None, 'true'])
def test_saved_workspace_keeps_only_boolean_open_as_tabs_policy(mode):
    from workspace_layouts import normalize_workspace
    raw = snapshot() | {'open_as_tabs': mode}
    clean = normalize_workspace(raw)
    if type(mode) is bool:
        assert clean['open_as_tabs'] is mode
    else:
        assert 'open_as_tabs' not in clean


@pytest.mark.parametrize('count,valid', [(8, True), (9, False)])
def test_saved_workspace_bounds_both_pdf_and_epub_reader_tabs(count, valid):
    from workspace_layouts import normalize_workspace
    raw = snapshot()
    raw['panes'] = [dict(name='incremento_'+kind+'_'+str(i), kind=kind, card_id=i+1)
                    for kind in ('pdf_reference', 'epub_reference') for i in range(count)]
    assert (normalize_workspace(raw) is not None) is valid


@pytest.mark.parametrize('tabs', [[True], [0], [71, -1], [71] * 33, [71, 71], [99], '71'])
def test_invalid_or_unbounded_writing_tab_lists_fall_back_to_the_active_card(tabs):
    from workspace_layouts import normalize_workspace
    raw = snapshot()
    raw['panes'][1]['writing_tabs'] = tabs
    clean = normalize_workspace(raw)
    assert 'writing_tabs' not in clean['panes'][1]
    assert clean['panes'][1]['card_id'] == 71
    raw['panes'] = [{'name': 'incremento_pdf_reference_' + str(i), 'kind': 'pdf_reference',
                     'card_id': i + 1} for i in range(9)]
    assert normalize_workspace(raw) is None
