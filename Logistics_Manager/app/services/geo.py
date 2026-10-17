from __future__ import annotations

import math
from typing import Sequence


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def road_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    road_factor: float = 1.3,
) -> float:
    return round(haversine_km(lat1, lon1, lat2, lon2) * road_factor, 3)


def distance_matrix(
    points: Sequence[tuple[float, float]],
    road_factor: float = 1.3,
) -> list[list[float]]:
    n = len(points)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = road_distance_km(
                points[i][0], points[i][1], points[j][0], points[j][1], road_factor
            )
            matrix[i][j] = d
            matrix[j][i] = d
    return matrix


def path_length(matrix: list[list[float]], order: Sequence[int]) -> float:
    if not order:
        return 0.0
    total = 0.0
    for a, b in zip(order, order[1:]):
        total += matrix[a][b]
    return round(total, 3)
