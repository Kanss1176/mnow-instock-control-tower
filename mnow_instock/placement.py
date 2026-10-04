"""Dark-store placement: weighted k-means over demand-potential points."""
import zlib
import numpy as np
import pandas as pd
from .config import CITIES


def placeholder_points(city, n=400, seed=0):
    """PLACEHOLDER potential surface (random). Replace with Atlas output (hex_potential.csv)."""
    rng = np.random.default_rng(seed + zlib.crc32(city.encode()) % 10_000)
    lat0, lon0 = CITIES[city]
    return pd.DataFrame({"city": city,
                         "lat": lat0 + rng.normal(0, 0.06, n),
                         "lon": lon0 + rng.normal(0, 0.06, n),
                         "score": rng.lognormal(0, 0.8, n)})


def place_stores(points, k, seed=0, iters=30):
    """Weighted k-means. Returns centers (k,2) and per-store potential with mean 1."""
    xy = points[["lat", "lon"]].to_numpy(float)
    w = points["score"].to_numpy(float)
    if (w < 0).any() or w.sum() <= 0:
        raise ValueError("scores must be non-negative with positive sum")
    rng = np.random.default_rng(seed)
    centers = xy[rng.choice(len(xy), size=k, replace=False, p=w / w.sum())]
    for _ in range(iters):
        d = ((xy[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
        a = d.argmin(1)
        for j in range(k):
            m = a == j
            if m.any():
                centers[j] = np.average(xy[m], axis=0, weights=w[m])
    d = ((xy[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
    a = d.argmin(1)
    share = np.array([w[a == j].sum() for j in range(k)])
    return centers, share / share.mean()
