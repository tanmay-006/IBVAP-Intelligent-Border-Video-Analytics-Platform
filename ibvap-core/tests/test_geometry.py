import pytest

from ibvap_core.rules.geometry import angle_between_deg, point_in_polygon, segments_intersect, side

SQUARE = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]


def test_point_in_polygon():
    assert point_in_polygon((0.5, 0.5), SQUARE)
    assert not point_in_polygon((0.9, 0.5), SQUARE)
    assert not point_in_polygon((0.5, 0.1), SQUARE)


def test_segments_intersect():
    assert segments_intersect((0.5, 0.0), (0.5, 1.0), (0.0, 0.5), (1.0, 0.5))
    assert not segments_intersect((0.5, 0.0), (0.5, 0.4), (0.0, 0.5), (1.0, 0.5))
    assert not segments_intersect((1.5, 0.0), (1.5, 1.0), (0.0, 0.5), (1.0, 0.5))
    assert segments_intersect((0.5, 0.0), (0.5, 0.5), (0.0, 0.5), (1.0, 0.5))  # touching endpoint


def test_side():
    assert side((0, 0.5), (1, 0.5), (0.5, 0.9)) == -side((0, 0.5), (1, 0.5), (0.5, 0.1))
    assert side((0, 0.5), (1, 0.5), (0.3, 0.5)) == 0


@pytest.mark.parametrize(
    ("u", "v", "deg"), [((1, 0), (1, 0), 0), ((1, 0), (0, 1), 90), ((0, 1), (0, -1), 180)]
)
def test_angle(u, v, deg):
    assert angle_between_deg(u, v) == pytest.approx(deg)
