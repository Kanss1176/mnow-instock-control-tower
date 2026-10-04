"""OBSERVED data: daily weather per city.
Primary source: Open-Meteo historical API. Fallback: NASA POWER daily point API.
Run locally:  python -m mnow_instock.atlas.ingest_weather
NETWORK CALLS NOT TESTED by the author's sandbox; parsers are unit-tested on hand-written fixtures.
Check each provider's terms and attribution before publishing derived data.
"""
import pathlib, time
import numpy as np, pandas as pd, requests
from ..config import CITIES

OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"
NASA_POWER = "https://power.larc.nasa.gov/api/temporal/daily/point"
ROOT = pathlib.Path(__file__).resolve().parents[2]
HEADERS = {"User-Agent": "mnow-instock-control-tower/0.1 (portfolio project)"}


def parse(payload, city):
    d = payload["daily"]
    return pd.DataFrame({"city": city, "d": pd.to_datetime(d["time"]),
                         "temp_c": d["temperature_2m_mean"], "rain_mm": d["precipitation_sum"],
                         "source": "open-meteo"})


def parse_power(payload, city):
    p = payload["properties"]["parameter"]
    t, r = p["T2M"], p["PRECTOTCORR"]
    days = sorted(t)
    return pd.DataFrame({"city": city, "d": pd.to_datetime(days, format="%Y%m%d"),
                         "temp_c": [t[k] for k in days], "rain_mm": [r[k] for k in days],
                         "source": "nasa-power"}).replace(-999, np.nan)   # -999 = missing in NASA POWER


def fetch_city(city, lat, lon, start, end, session=requests):
    try:
        r = session.get(OPEN_METEO, params={"latitude": lat, "longitude": lon, "start_date": start,
                        "end_date": end, "daily": "temperature_2m_mean,precipitation_sum",
                        "timezone": "Asia/Kolkata"}, headers=HEADERS, timeout=60)
        r.raise_for_status()
        return parse(r.json(), city)
    except Exception as e:                      # noqa: BLE001
        print(f"  Open-Meteo failed for {city} ({type(e).__name__}); trying NASA POWER")
    r = session.get(NASA_POWER, params={"parameters": "T2M,PRECTOTCORR", "community": "RE",
                    "latitude": lat, "longitude": lon, "start": start.replace("-", ""),
                    "end": end.replace("-", ""), "format": "JSON"}, headers=HEADERS, timeout=120)
    r.raise_for_status()
    return parse_power(r.json(), city)


def main(start="2025-07-01", end="2025-12-28"):
    (ROOT / "data/processed").mkdir(parents=True, exist_ok=True)
    frames = []
    for city, (lat, lon) in CITIES.items():
        frames.append(fetch_city(city, lat, lon, start, end))
        print(city, frames[-1].source.iloc[0], len(frames[-1]), "days")
        time.sleep(1)
    pd.concat(frames).to_csv(ROOT / "data/processed/weather_daily.csv", index=False)


if __name__ == "__main__":
    main()
