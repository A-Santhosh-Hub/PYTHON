from app.ui.label_layout import _overlap, place_labels

R = 20


def test_single_label_goes_below_its_marker():
    (rect,) = place_labels([(100, 100, 60)], bounds=(500, 300))
    assert rect[1] == 100 + R + 2 and rect[0] == 70


def test_no_label_for_empty_text():
    assert place_labels([(100, 100, 0), (200, 100, 40)], bounds=(500, 300))[0] is None


def test_neighbouring_labels_do_not_overlap_each_other():
    # the reported case: markers 68 px apart with wide labels ("Next weapon" / "Previous weapon")
    markers = [(100, 100, 90), (168, 100, 120), (236, 100, 70)]
    rects = place_labels(markers, bounds=(800, 400))
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert not _overlap(a, b)


def test_labels_do_not_cover_other_markers():
    markers = [(100, 100, 90), (168, 100, 120), (236, 100, 70)]
    rects = place_labels(markers, bounds=(800, 400))
    for rect in rects:
        for mx, my, _ in markers:
            nearest_x = max(rect[0], min(mx, rect[0] + rect[2]))
            nearest_y = max(rect[1], min(my, rect[1] + rect[3]))
            assert (nearest_x - mx) ** 2 + (nearest_y - my) ** 2 >= R * R


def test_label_near_the_bottom_edge_moves_above():
    (rect,) = place_labels([(100, 290, 60)], bounds=(500, 300))
    assert rect[1] + rect[3] <= 300 and rect[1] < 290


def test_label_stays_inside_horizontal_bounds():
    (rect,) = place_labels([(5, 100, 80)], bounds=(500, 300))
    assert rect[0] >= 0
    (rect,) = place_labels([(495, 100, 80)], bounds=(500, 300))
    assert rect[0] + rect[2] <= 500


def test_many_crowded_markers_still_all_get_a_rectangle():
    markers = [(100 + i * 25, 100, 80) for i in range(8)]
    rects = place_labels(markers, bounds=(800, 400))
    assert all(r is not None for r in rects)
