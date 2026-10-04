"""OBSERVED data: OpenStreetMap points of interest -> H3 hex features -> demand-potential score.

Run locally (needs internet):  python -m mnow_instock.atlas.ingest_osm
Data (c) OpenStreetMap contributors, ODbL. Keep attribution in any published output.
NETWORK CALL NOT TESTED by the author's sandbox; parsing and scoring ARE unit-tested.
"""
import os, pathlib, time
import h3, numpy as np, pandas as pd, requests
from ..config import CITIES

ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter",
             "https://lz4.overpass-api.de/api/interpreter"]
# Overpass asks clients to identify themselves; a generic python-requests agent is often refused (HTTP 406).
# Optionally set OVERPASS_CONTACT to an email or your GitHub URL.
HEADERS = {"User-Agent": "mnow-instock-control-tower/0.1 (portfolio project; "
                         + os.environ.get("OVERPASS_CONTACT", "contact not set") + ")",
           "Accept": "*/*"}
ROOT = pathlib.Path(__file__).resolve().parents[2]
RES = 8          # ~0.7 km2 hexes; adjust and document
PAD = 0.15       # degrees around the city centre (ASSUMED catchment box)
CLASSES = {      # POI class -> OSM filters
    "college": ['["amenity"~"college|university"]'],
    "office": ['["office"]'],
    "mall": ['["shop"="mall"]'],
    "transit": ['["railway"="station"]', '["station"="subway"]'],
}
# ASSUMED prior weights; stress-test with weight_sensitivity() before trusting rankings.
PRIOR_W = {"college": 0.30, "office": 0.25, "mall": 0.25, "transit": 0.20}


def build_query(lat, lon):
    s, w, n, e = lat - PAD, lon - PAD, lat + PAD, lon + PAD
    parts = []
    for filters in CLASSES.values():
        for f in filters:
            for t in ("node", "way"):
                parts.append(f"{t}{f}({s},{w},{n},{e});")
    return f"[out:json][timeout:120];({''.join(parts)});out center;"


def classify(tags):
    if tags.get("amenity") in ("college", "university"): return "college"
    if "office" in tags: return "office"
    if tags.get("shop") == "mall": return "mall"
    if tags.get("railway") == "station" or tags.get("station") == "subway": return "transit"
    return None


def count_by_hex(elements, res=RES):
    rows = []
    for el in elements:
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        cls = classify(el.get("tags", {}))
        if lat is None or lon is None or cls is None:
            continue
        rows.append({"hex": h3.latlng_to_cell(lat, lon, res), "cls": cls})
    if not rows:
        return pd.DataFrame(columns=["hex", *CLASSES])
    df = pd.DataFrame(rows).groupby(["hex", "cls"]).size().unstack(fill_value=0)
    for c in CLASSES:
        if c not in df: df[c] = 0
    return df[list(CLASSES)].reset_index()


def score(df, weights=PRIOR_W):
    """Weighted sum of z-scores, shifted to be non-negative."""
    z = (df[list(CLASSES)] - df[list(CLASSES)].mean()) / df[list(CLASSES)].std(ddof=0).replace(0, 1)
    raw = sum(weights[c] * z[c] for c in CLASSES)
    return raw - raw.min() + 1e-6


def weight_sensitivity(df, n=1000, seed=0, top=0.1):
    """Rank stability under Dirichlet-perturbed weights: mean Spearman and top-decile overlap."""
    from scipy.stats import spearmanr
    rng = np.random.default_rng(seed)
    base = score(df)
    k = max(1, int(len(df) * top)); base_top = set(base.nlargest(k).index)
    alpha = np.array([PRIOR_W[c] for c in CLASSES]) * 20
    rho, ov = [], []
    for w in rng.dirichlet(alpha, n):
        s = score(df, dict(zip(CLASSES, w)))
        rho.append(spearmanr(base, s)[0]); ov.append(len(base_top & set(s.nlargest(k).index)) / k)
    return {"mean_spearman": float(np.mean(rho)), "mean_top_overlap": float(np.mean(ov))}


def fetch_overpass(query, session=requests, endpoints=ENDPOINTS, tries=5, wait=20):
    """POST the query; on any HTTP/connection error try the next mirror, then wait and retry.
    The wait doubles each round (20s, 40s, 80s...) so a brief internet drop or busy server is survived."""
    last = None
    for attempt in range(tries):
        for url in endpoints:
            try:
                r = session.post(url, data={"data": query}, headers=HEADERS, timeout=180)
                r.raise_for_status()
                return r.json()["elements"]
            except Exception as e:           # noqa: BLE001 - deliberately broad, re-raised below
                last = e
                print(f"  {url} failed: {type(e).__name__}: {str(e)[:120]}")
        if attempt < tries - 1:
            time.sleep(wait * (2 ** attempt))
    raise RuntimeError(f"All Overpass endpoints failed. Last error: {last}")


def process_city(city, lat, lon, cache_dir, fetch=None):
    """Return the scored hex table for one city, using a saved copy if it exists.
    Each finished city is written to disk immediately, so a crash never loses completed cities."""
    cache_dir = pathlib.Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / (city.replace(" ", "_") + ".csv")
    if f.exists():
        print(city, "already downloaded, skipping")
        return pd.read_csv(f)
    fetch = fetch or fetch_overpass
    hx = count_by_hex(fetch(build_query(lat, lon)))
    hx["city"] = city
    hx[["lat", "lon"]] = [h3.cell_to_latlng(h) for h in hx["hex"]]
    hx["score"] = score(hx)
    print(city, len(hx), "hexes", weight_sensitivity(hx, n=200))
    hx.to_csv(f, index=False)
    return hx


def main():
    out_dir = ROOT / "data/processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for city, (lat, lon) in CITIES.items():
        frames.append(process_city(city, lat, lon, out_dir / "osm_cache"))
        time.sleep(10)                              # be polite to the public Overpass server
    pd.concat(frames, ignore_index=True).to_csv(out_dir / "hex_potential.csv", index=False)
    print("Saved hex_potential.csv for", len(frames), "cities")


if __name__ == "__main__":
    main()
