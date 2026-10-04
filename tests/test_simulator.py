def test_conservation_and_bounds(small_db):
    con, _, _ = small_db
    q = lambda s: con.execute(s).fetchone()[0]
    assert q("select count(*) from sim_inventory_daily where on_hand_close <> on_hand_open - sold") == 0
    assert q("select count(*) from sim_inventory_daily where sold > on_hand_open") == 0
    assert q("select count(*) from sim_inventory_daily where on_hand_open<0 or sold<0") == 0


def test_truth_consistency(small_db):
    con, _, _ = small_db
    bad = con.execute("""select count(*) from sim_truth_daily t join sim_inventory_daily i using(store_id,sku_id,d)
                         where t.demand_true - i.sold <> t.lost_true or t.lost_true < 0""").fetchone()[0]
    assert bad == 0


def test_orders_arrive_after_placement(small_db):
    con, _, _ = small_db
    assert con.execute("select count(*) from sim_orders where arrive_day<=order_day or arrived_qty>actual_qty").fetchone()[0] == 0


def test_full_calendar(small_db):
    con, _, cfg = small_db
    n = con.execute("select count(*) from sim_inventory_daily").fetchone()[0]
    assert n == 10 * 1 * cfg.n_skus * cfg.n_days


def test_same_seed_same_result(tmp_path):
    from mnow_instock.config import SimConfig
    from mnow_instock.build_db import build
    cfg = SimConfig(stores_per_city=1, n_skus=10, n_days=30)
    a, _ = build(cfg, str(tmp_path / "a.duckdb"))
    b, _ = build(cfg, str(tmp_path / "b.duckdb"))
    qa = a.execute("select sum(sold), sum(on_hand_close) from sim_inventory_daily").fetchone()
    qb = b.execute("select sum(sold), sum(on_hand_close) from sim_inventory_daily").fetchone()
    assert qa == qb
