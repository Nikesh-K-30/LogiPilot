from app.services.geo import distance_matrix, haversine_km, path_length, road_distance_km


def test_haversine_delhi_chennai_positive():
    # Delhi to Chennai roughly 1750–2200 km great-circle
    d = haversine_km(28.6139, 77.2090, 13.0827, 80.2707)
    assert 1700 < d < 2300


def test_road_factor_increases_distance():
    a = haversine_km(28.6, 77.2, 17.4, 78.5)
    b = road_distance_km(28.6, 77.2, 17.4, 78.5, road_factor=1.3)
    assert b > a


def test_matrix_symmetric():
    pts = [(28.6, 77.2), (17.4, 78.5), (12.97, 77.59)]
    m = distance_matrix(pts, 1.3)
    assert m[0][1] == m[1][0]
    assert m[0][0] == 0
    assert path_length(m, [0, 1, 2]) == round(m[0][1] + m[1][2], 3)
