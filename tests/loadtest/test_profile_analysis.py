from loadtest.profile_analysis import Frame, exclusive_hotspots


def test_hotspots_subtract_child_samples_instead_of_ranking_wide_parents() -> None:
    frames = [
        Frame("all", 100, 0, 48, 100),
        Frame("parent", 100, 0, 32, 100),
        Frame("first", 60, 0, 16, 60),
        Frame("second", 30, 60, 16, 30),
    ]

    assert exclusive_hotspots(frames) == [("first", 60), ("second", 30), ("parent", 10)]


def test_icicle_orientation_does_not_mistake_entry_points_for_hotspots() -> None:
    frames = [
        Frame("all", 100, 0, 0, 100),
        Frame("entry", 100, 0, 16, 100),
        Frame("first", 60, 0, 32, 60),
        Frame("second", 30, 60, 32, 30),
    ]

    assert exclusive_hotspots(frames) == [("first", 60), ("second", 30), ("entry", 10)]
