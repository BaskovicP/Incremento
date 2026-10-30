from frontend.study_resource_titles import display_resource_title


def test_bibliographic_filename_displays_the_book_title_without_changing_ordinary_titles():
    raw = '[DAMA - DMBOK2] Data Management Knowledge System Guide {DAMA International}{2017, DAMA International}{114604262} libgen.li'
    assert display_resource_title(raw) == 'Data Management Knowledge System Guide'
    assert display_resource_title('Guyton & Hall') == 'Guyton & Hall'
    assert display_resource_title('[Review] What is {A, B}?') == '[Review] What is {A, B}?'
    assert display_resource_title('Compare {A}{B}') == 'Compare {A}{B}'
    assert display_resource_title('  Capillary\nexchange lecture  ') == 'Capillary exchange lecture'


def test_bibliographic_title_handles_the_mixed_brackets_in_the_reported_filename():
    raw = '[DAMA - DMBOK2 - DAMA - DMBOK2] Data Management Knowledge System Guide 1{DAMA International}(2017, DAMA International){114604262} libgen.li'
    assert display_resource_title(raw) == 'Data Management Knowledge System Guide 1'
