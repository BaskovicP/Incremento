from study_visit import StudyVisit


def test_reference_visit_retains_original_card_and_side_until_explicit_return():
    collection = object()
    visit = StudyVisit("A", collection, 17, "answer")
    visit.navigate("book")
    visit.navigate("video")
    visit.navigate("book")
    assert (visit.card_id, visit.side) == (17, "answer")
    assert visit.current("A", collection, 17, "answer")
    assert visit.finish("A", collection, 17, "answer")
    assert not visit.current("A", collection, 17, "answer")


def test_reviewer_change_profile_switch_or_collection_reopen_retires_a_visit():
    collection = object()
    for profile, col, cid, side in [("B", collection, 17, "question"),
        ("A", object(), 17, "question"), ("A", collection, 18, "question"),
        ("A", collection, 17, "answer")]:
        visit = StudyVisit("A", collection, 17, "question")
        assert not visit.current(profile, col, cid, side)
        assert not visit.finish(profile, col, cid, side)
