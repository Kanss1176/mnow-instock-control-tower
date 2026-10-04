import pandas as pd
from mnow_instock.atlas.ingest_osm import classify, count_by_hex, score, weight_sensitivity, build_query
from mnow_instock.atlas.ingest_weather import parse

FIXTURE = [  # hand-written fixture, NOT real OSM output
    {"lat": 12.97, "lon": 77.59, "tags": {"amenity": "university"}},
    {"lat": 12.97, "lon": 77.59, "tags": {"office": "company"}},
    {"center": {"lat": 12.98, "lon": 77.60}, "tags": {"shop": "mall"}},
    {"lat": 12.99, "lon": 77.61, "tags": {"railway": "station"}},
    {"lat": 12.99, "lon": 77.61, "tags": {"amenity": "cafe"}},   # ignored
    {"tags": {"office": "x"}},                                     # no coords: ignored
]


def test_classify():
    assert classify({"amenity": "college"}) == "college" and classify({"amenity": "cafe"}) is None


def test_count_by_hex_ignores_bad_rows():
    df = count_by_hex(FIXTURE)
    assert df[["college", "office", "mall", "transit"]].to_numpy().sum() == 4


def test_score_nonnegative_and_sensitivity_bounds():
    import numpy as np
    rng = np.random.default_rng(0)
    df = pd.DataFrame(rng.poisson(2, (60, 4)), columns=["college", "office", "mall", "transit"])
    assert (score(df) > 0).all()
    s = weight_sensitivity(df, n=30)
    assert -1 <= s["mean_spearman"] <= 1 and 0 <= s["mean_top_overlap"] <= 1


def test_query_contains_bbox():
    assert "out center" in build_query(12.97, 77.59)


def test_weather_parse():
    p = {"daily": {"time": ["2025-07-01"], "temperature_2m_mean": [24.1], "precipitation_sum": [3.2]}}
    assert parse(p, "Pune").iloc[0].temp_c == 24.1


def test_power_parse_missing_values():
    from mnow_instock.atlas.ingest_weather import parse_power
    p = {"properties": {"parameter": {"T2M": {"20250701": 24.5, "20250702": -999},
                                       "PRECTOTCORR": {"20250701": 1.2, "20250702": 0.0}}}}
    df = parse_power(p, "Pune")
    assert df.temp_c.isna().sum() == 1 and df.iloc[0].temp_c == 24.5


class _Resp:
    def __init__(self, ok, payload=None):
        self.ok, self.payload = ok, payload
    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("406 Not Acceptable")
    def json(self):
        return self.payload


class _Session:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
    def post(self, url, **kw):
        self.calls.append((url, kw["headers"]))
        return self.responses.pop(0)


def test_overpass_falls_back_to_next_mirror_and_sends_user_agent():
    from mnow_instock.atlas.ingest_osm import fetch_overpass
    s = _Session([_Resp(False), _Resp(True, {"elements": [{"id": 1}]})])
    out = fetch_overpass("q", session=s, endpoints=["a", "b"], tries=1, wait=0)
    assert out == [{"id": 1}] and [c[0] for c in s.calls] == ["a", "b"]
    assert "mnow-instock-control-tower" in s.calls[0][1]["User-Agent"]


def test_overpass_raises_when_all_fail():
    import pytest
    from mnow_instock.atlas.ingest_osm import fetch_overpass
    s = _Session([_Resp(False)] * 4)
    with pytest.raises(RuntimeError):
        fetch_overpass("q", session=s, endpoints=["a", "b"], tries=2, wait=0)


def test_city_is_cached_after_first_download(tmp_path):
    from mnow_instock.atlas.ingest_osm import process_city
    calls = []
    def fake_fetch(q):
        calls.append(q)
        return [{"lat": 12.97, "lon": 77.59, "tags": {"amenity": "university"}},
                {"lat": 12.98, "lon": 77.60, "tags": {"office": "x"}},
                {"lat": 12.99, "lon": 77.61, "tags": {"shop": "mall"}}]
    a = process_city("Bengaluru", 12.97, 77.59, tmp_path, fetch=fake_fetch)
    b = process_city("Bengaluru", 12.97, 77.59, tmp_path, fetch=fake_fetch)
    assert len(calls) == 1 and len(a) == len(b) and (b.score > 0).all()


def test_failed_city_does_not_delete_finished_ones(tmp_path):
    import pytest
    from mnow_instock.atlas.ingest_osm import process_city
    ok = lambda q: [{"lat": 12.97, "lon": 77.59, "tags": {"office": "x"}}]
    def boom(q): raise RuntimeError("network down")
    process_city("Pune", 18.5, 73.8, tmp_path, fetch=ok)
    with pytest.raises(RuntimeError):
        process_city("Jaipur", 26.9, 75.8, tmp_path, fetch=boom)
    assert (tmp_path / "Pune.csv").exists()
