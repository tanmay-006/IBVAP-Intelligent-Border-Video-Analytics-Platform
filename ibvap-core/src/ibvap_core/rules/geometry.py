"""2-D geometry in normalised image coordinates (x, y in 0..1, y pointing down)."""

from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[float, float]


def cross(o: Point, a: Point, b: Point) -> float:
    """Z component of (a - o) x (b - o). Sign tells which side of line o→a point b lies on."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def side(a: Point, b: Point, p: Point) -> int:
    c = cross(a, b, p)
    return (c > 0) - (c < 0)


def segments_intersect(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    """Proper or touching intersection of segments p1-p2 and q1-q2."""
    d1, d2 = side(q1, q2, p1), side(q1, q2, p2)
    d3, d4 = side(p1, p2, q1), side(p1, p2, q2)
    if d1 != d2 and d3 != d4 and 0 not in (d1, d2, d3, d4):
        return True

    def on_segment(a: Point, b: Point, p: Point) -> bool:
        return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])

    return (
        (d1 == 0 and on_segment(q1, q2, p1))
        or (d2 == 0 and on_segment(q1, q2, p2))
        or (d3 == 0 and on_segment(p1, p2, q1))
        or (d4 == 0 and on_segment(p1, p2, q2))
    )


def point_in_polygon(p: Point, polygon: Sequence[Point]) -> bool:
    """Ray casting; points on the boundary may fall either way."""
    x, y = p
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


def angle_between_deg(u: Point, v: Point) -> float:
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu == 0 or nv == 0:
        return 0.0
    cos = (u[0] * v[0] + u[1] * v[1]) / (nu * nv)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))
