"""SIMULATED dark-store inventory. Not Myntra data. Demonstrates method only.

Design rules (see README, circularity section):
 * The demand generator is structurally different from the replenishment policy's
   forecaster (policy uses a trailing mean of *censored* sales; generator has
   shocks and a regime break the policy never sees).
 * Every injected deviation carries a ground-truth cause label, kept in a
   separate truth table that analyses must not use except for evaluation.
"""
import numpy as np
import pandas as pd
from .config import (SimConfig, CATEGORIES, EVENT_AFFINITY, DOW_MULT, CAUSES)


def make_skus(cfg: SimConfig, rng):
    """ASSUMED SKU archetypes. Invented attributes, not Myntra's catalogue."""
    cat = rng.choice(CATEGORIES, cfg.n_skus)
    vel = rng.choice(["fast", "medium", "slow"], cfg.n_skus, p=[0.2, 0.4, 0.4])
    rate = {"fast": 1.2, "medium": 0.4, "slow": 0.1}
    base = np.array([rate[v] for v in vel]) * rng.lognormal(0, 0.25, cfg.n_skus)
    price = np.round(rng.lognormal(6.9, 0.5, cfg.n_skus), -1).clip(299, 6999)
    pack = rng.choice([1, 2, 4, 6], cfg.n_skus, p=[0.3, 0.3, 0.25, 0.15])
    phi = rng.uniform(0.2, 0.8, cfg.n_skus)  # NegBin dispersion
    return pd.DataFrame({"sku_id": np.arange(cfg.n_skus), "category": cat,
                         "velocity_class": vel, "base_rate": base, "price": price,
                         "case_pack": pack, "phi": phi, "source": "simulated"})


def event_multipliers(dates, events, skus_cats):
    """Per-category multiplier per date from the events table (uplift_assumed)."""
    T = len(dates)
    ev = np.ones(T)
    for _, r in events.iterrows():
        m = (dates >= pd.Timestamp(r["start"])) & (dates <= pd.Timestamp(r["end"]))
        ev[m] = np.maximum(ev[m], float(r["uplift_assumed"]))
    return {c: ev ** EVENT_AFFINITY[c] for c in skus_cats}


def simulate(cfg: SimConfig, stores: pd.DataFrame, skus: pd.DataFrame, events: pd.DataFrame):
    rng = np.random.default_rng(cfg.seed)
    dates = pd.date_range(cfg.start_date, periods=cfg.n_days)
    T, S, K = cfg.n_days, len(stores), len(skus)
    P = S * K
    s_idx = np.repeat(np.arange(S), K)
    k_idx = np.tile(np.arange(K), S)

    pot = stores["potential"].to_numpy()[s_idx]
    base = skus["base_rate"].to_numpy()[k_idx]
    phi = skus["phi"].to_numpy()[k_idx]
    pack = skus["case_pack"].to_numpy()[k_idx].astype(int)
    cats = skus["category"].to_numpy()[k_idx]

    # ---- demand generator -------------------------------------------------
    evm = event_multipliers(dates, events, CATEGORIES)
    ev_p = np.stack([evm[c] for c in cats])                       # (P,T)
    dow = np.array(DOW_MULT)[dates.dayofweek.to_numpy()]            # (T,)
    n_wk = T // 7 + 1
    shock_w = np.where(rng.random((P, n_wk)) < cfg.shock_prob_week,
                       rng.lognormal(0.7, 0.3, (P, n_wk)), 1.0)
    shock = np.repeat(shock_w, 7, axis=1)[:, :T]
    regime = np.ones((P, T))
    regime[(cats == cfg.regime_category)[:, None] & (np.arange(T) >= cfg.regime_day)[None, :]] = cfg.regime_factor
    lam = base[:, None] * pot[:, None] * dow[None, :] * ev_p * shock * regime
    g = rng.gamma(1.0 / phi[:, None], phi[:, None], size=(P, T))
    demand = rng.poisson(lam * g).astype(np.int64)

    # ---- inventory + replenishment loop ----------------------------------
    W = 12
    pipe = np.zeros((P, W), dtype=np.int64)
    on_hand = np.ceil(base * pot * 7 / pack).astype(np.int64) * pack
    lane = rng.lognormal(0, 0.2, S)[s_idx]
    sold = np.zeros((P, T), np.int64)
    open_h = np.zeros((P, T), np.int64)
    close_h = np.zeros((P, T), np.int64)
    arrivals = np.zeros((P, T), np.int64)
    cause_true = np.zeros((P, T), np.int8)
    mu_hist = np.zeros((P, T))
    last_cause = np.zeros(P, np.int8)
    last_cause_t = np.full(P, -10_000)
    orders = []
    H = cfg.lead_mean + 1
    pr = np.cumsum([cfg.p_override, cfg.p_stale, cfg.p_late, cfg.p_short])

    for t in range(T):
        arr = pipe[:, t % W].copy()
        pipe[:, t % W] = 0
        on_hand = on_hand + arr
        arrivals[:, t] = arr
        open_h[:, t] = on_hand
        s = np.minimum(demand[:, t], on_hand)
        sold[:, t] = s
        on_hand = on_hand - s
        close_h[:, t] = on_hand
        lost = demand[:, t] - s
        has_dev = (t - last_cause_t) <= cfg.cause_window
        cause_true[:, t] = np.where(lost > 0, np.where(has_dev, last_cause, 5), 0)

        win = sold[:, max(0, t - 27):t + 1]
        mu = np.maximum(win.mean(1), 0.02)
        sd = np.maximum(win.std(1), np.sqrt(mu))
        mu_hist[:, t] = mu
        ip = on_hand + pipe.sum(1)

        def order_qty(mu_use):
            target = np.maximum(mu_use * H + cfg.service_z * sd * np.sqrt(H),
                                cfg.min_display_packs * pack)
            rec = np.maximum(0.0, target - ip)
            rec = np.where(rec >= 0.5 * pack, rec, 0.0)
            return (np.ceil(rec / pack) * pack).astype(np.int64)

        rec_qty = order_qty(mu)
        u = rng.random(P)
        code = np.select([u < pr[0], u < pr[1], u < pr[2], u < pr[3]], [1, 2, 3, 4], 0)
        qty = rec_qty.copy()
        ov = code == 1
        qty = np.where(ov, np.ceil(rec_qty * np.where(rng.random(P) < 0.5, 0.5, 1.5) / pack).astype(np.int64) * pack, qty)
        if t >= 14:
            qty = np.where(code == 2, order_qty(mu_hist[:, t - 14]), qty)
        lead = 1 + rng.poisson((cfg.lead_mean - 1) * lane)
        lead = lead + np.where(code == 3, 2, 0)
        lead = np.minimum(lead, W - 1)
        fill = rng.beta(60, 2, P)
        fill = np.where(code == 4, rng.uniform(0.3, 0.7, P), fill)
        arrived = np.floor(qty * fill).astype(np.int64)
        placed = qty > 0
        idx = np.nonzero(placed)[0]
        np.add.at(pipe, (idx, (t + lead[idx]) % W), arrived[idx])
        dev = placed & (code > 0)
        last_cause = np.where(dev, code, last_cause).astype(np.int8)
        last_cause_t = np.where(dev, t, last_cause_t)
        if len(idx):
            orders.append(pd.DataFrame({
                "store_id": stores["store_id"].to_numpy()[s_idx[idx]],
                "sku_id": skus["sku_id"].to_numpy()[k_idx[idx]],
                "order_day": dates[t], "recommended_qty": rec_qty[idx],
                "actual_qty": qty[idx], "lead_days": lead[idx],
                "arrive_day": dates[t] + pd.to_timedelta(lead[idx], "D"),
                "arrived_qty": arrived[idx],
                "deviation_cause": np.array(list(CAUSES.values()))[code[idx]]}))

    # ---- tables ------------------------------------------------------------
    sid = np.repeat(stores["store_id"].to_numpy()[s_idx], T)
    kid = np.repeat(skus["sku_id"].to_numpy()[k_idx], T)
    dd = np.tile(dates.to_numpy(), P)
    inv = pd.DataFrame({"store_id": sid, "sku_id": kid, "d": dd,
                        "on_hand_open": open_h.ravel(), "arrivals": arrivals.ravel(),
                        "sold": sold.ravel(), "on_hand_close": close_h.ravel(),
                        "source": "simulated"})
    truth = pd.DataFrame({"store_id": sid, "sku_id": kid, "d": dd,
                          "demand_true": demand.ravel(),
                          "lost_true": (demand - sold).ravel(),
                          "true_cause": np.array(list(CAUSES.values()))[cause_true.ravel()]})
    ords = pd.concat(orders, ignore_index=True) if orders else pd.DataFrame()
    ords.insert(0, "order_id", np.arange(len(ords)))
    return inv, truth, ords
