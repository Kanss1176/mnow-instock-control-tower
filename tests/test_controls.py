import duckdb
from mnow_instock.controls import run_controls, has_errors


def test_clean_data_has_no_errors_but_warnings(small_db):
    _, rep, _ = small_db
    assert not has_errors(rep)
    warn = rep[rep.severity == "WARN"].set_index("control_id").violations
    assert "C8" in warn.index and "C9" in warn.index


def _copy(con):
    c = duckdb.connect(":memory:")
    for t in ["dim_store", "dim_sku", "dim_event", "sim_inventory_daily", "sim_orders"]:
        df = con.execute(f"select * from {t}").fetchdf()
        c.register("tmp", df); c.execute(f"create table {t} as select * from tmp"); c.unregister("tmp")
    return c


def test_detects_corruption(small_db):
    con, _, _ = small_db
    c = _copy(con)
    c.execute("update sim_inventory_daily set sold = on_hand_open + 5 where rowid = 10")   # C3, C4
    c.execute("insert into sim_inventory_daily select * from sim_inventory_daily where rowid = 20")  # C1
    c.execute("delete from sim_inventory_daily where rowid = 30")  # C5 gap
    rep = run_controls(c).set_index("control_id").violations
    assert rep["C1"] > 0 and rep["C3"] > 0 and rep["C4"] > 0 and rep["C5"] > 0
    assert has_errors(run_controls(c))


def test_detects_orphan_and_bad_order(small_db):
    con, _, _ = small_db
    c = _copy(con)
    c.execute("update sim_inventory_daily set store_id = 9999 where rowid = 5")
    c.execute("update sim_orders set arrive_day = order_day - INTERVAL 1 DAY where rowid = 3")
    rep = run_controls(c).set_index("control_id").violations
    assert rep["C7"] > 0 and rep["C6"] > 0
