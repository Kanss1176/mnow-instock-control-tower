-- Observable-only views (what an analyst could compute without ground truth).
CREATE OR REPLACE VIEW v_inventory_daily AS
SELECT i.*,
       AVG(sold) OVER (PARTITION BY store_id, sku_id ORDER BY d
                       ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS v28,
       on_hand_close / NULLIF(AVG(sold) OVER (PARTITION BY store_id, sku_id ORDER BY d
                       ROWS BETWEEN 27 PRECEDING AND CURRENT ROW), 0) AS days_of_cover,
       CASE WHEN on_hand_open = 0 THEN 1 ELSE 0 END AS oos_open
FROM sim_inventory_daily i;

CREATE OR REPLACE VIEW v_weekly_pair AS
SELECT store_id, sku_id, date_trunc('week', d) AS wk,
       SUM(CASE WHEN on_hand_open = 0 THEN 1 ELSE 0 END) AS oos_days,
       COUNT(*) AS days,
       SUM(sold) AS sold,
       SUM(arrivals) AS received,
       ARG_MIN(on_hand_open - arrivals, d) AS open_stock_wk
FROM sim_inventory_daily GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW v_kpi_weekly_city AS
SELECT s.city, w.wk,
       1.0 - SUM(w.oos_days) * 1.0 / SUM(w.days) AS instock_pct,
       SUM(w.sold) * 1.0 / NULLIF(SUM(w.open_stock_wk + w.received), 0) AS sell_through
FROM v_weekly_pair w JOIN dim_store s USING (store_id)
WHERE w.days = 7
GROUP BY 1, 2;

-- A5 persistence: out of stock >= 2 days in 3+ of the last 4 full weeks.
CREATE OR REPLACE VIEW v_persistence AS
WITH ranked AS (
  SELECT *, DENSE_RANK() OVER (ORDER BY wk DESC) AS wk_rank
  FROM v_weekly_pair WHERE days = 7),
last4 AS (SELECT * FROM ranked WHERE wk_rank <= 4)
SELECT store_id, sku_id,
       COUNT(*) FILTER (WHERE oos_days >= 2) AS bad_weeks,
       COUNT(*) FILTER (WHERE oos_days >= 2) >= 3 AS persistent,
       COUNT(*) FILTER (WHERE oos_days >= 2) >= 1 AS any_bad
FROM last4 GROUP BY 1, 2;

-- Evaluation-only views: use ground truth that does not exist in real life.
CREATE OR REPLACE VIEW eval_lost_by_cause AS
SELECT true_cause AS cause, SUM(lost_true) AS lost_units,
       SUM(lost_true) * 1.0 / SUM(SUM(lost_true)) OVER () AS share
FROM sim_truth_daily WHERE lost_true > 0 GROUP BY 1 ORDER BY 2 DESC;

CREATE OR REPLACE VIEW eval_fill_rate_city AS
SELECT s.city, SUM(t.demand_true - t.lost_true) * 1.0 / NULLIF(SUM(t.demand_true), 0) AS fill_rate
FROM sim_truth_daily t JOIN dim_store s USING (store_id) GROUP BY 1;
