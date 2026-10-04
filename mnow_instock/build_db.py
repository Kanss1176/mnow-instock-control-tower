"""Build the DuckDB database: python -m mnow_instock.build_db --out data/processed/mnow.duckdb"""
import argparse, pathlib
import duckdb, numpy as np, pandas as pd
from .config import CITIES, CITY_SCALE, SimConfig
from .placement import place_stores, placeholder_points
from .simulator import make_skus, simulate
from .controls import run_controls, has_errors

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_points():
    f = ROOT / "data/processed/hex_potential.csv"  # columns: city, lat, lon, score (Atlas output)
    if f.exists():
        return pd.read_csv(f), "atlas_derived"
    return None, "placeholder"


def build(cfg: SimConfig, out: str):
    rng = np.random.default_rng(cfg.seed)
    pts, source = load_points()
    stores = []
    for city in CITIES:
        p = pts[pts.city == city] if pts is not None else placeholder_points(city, seed=cfg.seed)
        centers, pot = place_stores(p, cfg.stores_per_city, seed=cfg.seed)
        for j in range(cfg.stores_per_city):
            stores.append({"city": city, "lat": centers[j, 0], "lon": centers[j, 1],
                           "potential": pot[j] * CITY_SCALE[city],
                           "potential_source": source})
    stores = pd.DataFrame(stores)
    stores.insert(0, "store_id", np.arange(len(stores)))
    skus = make_skus(cfg, rng)
    ev_file = ROOT / "data/raw/events.csv"
    events = pd.read_csv(ev_file if ev_file.exists() else ROOT / "data/raw/events_template.csv")
    inv, truth, orders = simulate(cfg, stores, skus, events)

    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(out)
    for name, df in [("dim_store", stores), ("dim_sku", skus), ("dim_event", events),
                     ("sim_inventory_daily", inv), ("sim_truth_daily", truth), ("sim_orders", orders)]:
        con.register("tmp", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp")
        con.unregister("tmp")
    report = run_controls(con)
    con.execute((ROOT / "sql/10_views.sql").read_text())
    return con, report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/processed/mnow.duckdb"))
    ap.add_argument("--stores-per-city", type=int, default=3)
    ap.add_argument("--skus", type=int, default=120)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    pathlib.Path(a.out).unlink(missing_ok=True)
    cfg = SimConfig(seed=a.seed, stores_per_city=a.stores_per_city, n_skus=a.skus, n_days=a.days)
    con, rep = build(cfg, a.out)
    print(rep[["control_id", "severity", "rule", "violations"]].to_string(index=False))
    if has_errors(rep):
        raise SystemExit("Controls failed (ERROR). Do not use this database.")
    print("\nWeekly instock % by city (last 3 weeks):")
    print(con.execute("SELECT city, wk, ROUND(instock_pct,3) instock, ROUND(sell_through,3) st FROM v_kpi_weekly_city "
                      "QUALIFY DENSE_RANK() OVER (ORDER BY wk DESC) <= 1 ORDER BY city").fetchdf().to_string(index=False))
