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
    raw['panes'] = [{'name': 'incremento_pdf_reference_' + str(i), 'kind': 'pdf_reference',
                     'card_id': i + 1} for i in range(9)]
    assert normalize_workspace(raw) is None
