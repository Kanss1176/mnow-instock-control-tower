"""Data controls. Exceptions are logged, never silently corrected."""
import pandas as pd

# (id, severity, description, SQL returning violating keys: one row per violation)
CONTROLS = [
 ("C1", "ERROR", "duplicate (store,sku,d) key",
  "SELECT store_id, sku_id, d FROM sim_inventory_daily GROUP BY 1,2,3 HAVING COUNT(*)>1"),
 ("C2", "ERROR", "negative stock or sales",
  "SELECT store_id, sku_id, d FROM sim_inventory_daily WHERE on_hand_open<0 OR on_hand_close<0 OR sold<0 OR arrivals<0"),
 ("C3", "ERROR", "sold exceeds opening stock",
  "SELECT store_id, sku_id, d FROM sim_inventory_daily WHERE sold>on_hand_open"),
 ("C4", "ERROR", "stock not conserved (close != open - sold)",
  "SELECT store_id, sku_id, d FROM sim_inventory_daily WHERE on_hand_close<>on_hand_open-sold"),
 ("C5", "ERROR", "date gap in store-sku series",
  "SELECT store_id, sku_id, NULL AS d FROM sim_inventory_daily GROUP BY 1,2 "
  "HAVING COUNT(DISTINCT d) <> DATE_DIFF('day', MIN(d), MAX(d)) + 1"),
 ("C6", "ERROR", "order arrives before it is placed or arrives more than ordered",
  "SELECT store_id, sku_id, order_day AS d FROM sim_orders WHERE arrive_day<order_day OR arrived_qty>actual_qty"),
 ("C7", "ERROR", "orphan store or sku key",
  "SELECT i.store_id, i.sku_id, MIN(i.d) AS d FROM sim_inventory_daily i "
  "LEFT JOIN dim_store s USING(store_id) LEFT JOIN dim_sku k USING(sku_id) "
  "WHERE s.store_id IS NULL OR k.sku_id IS NULL GROUP BY 1,2"),
 ("C8", "WARN", "event without source_url (date unverified)",
  "SELECT NULL AS store_id, NULL AS sku_id, NULL AS d FROM dim_event WHERE source_url IS NULL OR source_url=''"),
 ("C9", "WARN", "store potential is a placeholder, not Atlas-derived",
  "SELECT store_id, NULL AS sku_id, NULL AS d FROM dim_store WHERE potential_source<>'atlas_derived'"),
]


def run_controls(con):
    rows = []
    for cid, sev, desc, sql in CONTROLS:
        df = con.execute(sql).fetchdf()
        n = len(df)
        rows.append({"control_id": cid, "severity": sev, "rule": desc, "violations": n,
                     "sample": df.head(3).astype(str).to_dict("records") if n else []})
    out = pd.DataFrame(rows)
    con.execute("CREATE OR REPLACE TABLE dq_exceptions AS SELECT control_id, severity, rule, violations FROM out")
    return out


def has_errors(report: pd.DataFrame) -> bool:
    return bool(((report.severity == "ERROR") & (report.violations > 0)).any())
