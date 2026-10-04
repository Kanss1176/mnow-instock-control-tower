import numpy as np, pytest
from mnow_instock.placement import place_stores, placeholder_points


def test_placement_deterministic_and_mean_one():
    p = placeholder_points("Pune")
    c1, w1 = place_stores(p, 4, seed=1)
    c2, w2 = place_stores(p, 4, seed=1)
    assert np.allclose(c1, c2) and np.allclose(w1, w2)
    assert c1.shape == (4, 2) and abs(w1.mean() - 1) < 1e-9


def test_placeholder_points_deterministic_across_calls():
    assert placeholder_points("Pune").equals(placeholder_points("Pune"))


def test_rejects_bad_scores():
    p = placeholder_points("Pune"); p["score"] = -1
    with pytest.raises(ValueError):
        place_stores(p, 2)
