import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from mnow_instock.config import SimConfig
from mnow_instock.build_db import build


@pytest.fixture(scope="session")
def small_db(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("db") / "t.duckdb")
    cfg = SimConfig(stores_per_city=1, n_skus=20, n_days=60)
    con, rep = build(cfg, out)
    return con, rep, cfg
