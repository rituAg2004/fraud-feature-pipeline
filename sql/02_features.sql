-- Velocity and previous-transaction features (window functions).
-- txn_count_1h counts this customer's transactions in the last 3600 seconds,
-- the current one included. LAG gives the previous transaction's city and time.
SELECT
    txn_id,
    customer_id,
    ts_epoch,
    amount,
    city,
    COUNT(*) OVER (
        PARTITION BY customer_id
        ORDER BY ts_epoch
        RANGE BETWEEN 3600 PRECEDING AND CURRENT ROW
    ) AS txn_count_1h,
    LAG(city) OVER w AS prev_city,
    LAG(ts_epoch) OVER w AS prev_epoch
FROM clean_transactions
WINDOW w AS (PARTITION BY customer_id ORDER BY ts_epoch, txn_id);