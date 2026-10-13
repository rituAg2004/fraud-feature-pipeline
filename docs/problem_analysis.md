# Problem Analysis

## 1. Business goal

Give a fraud analyst a ranked list of suspicious transactions, each with a score and a short reason, so the analyst can review the riskiest cases first.

## 2. Input data

Synthetic card transactions in CSV files. Seven columns arrive in every transaction file:

| Column | Meaning |
|---|---|
| txn_id | Unique id of the transaction |
| customer_id | Who made it |
| ts | Timestamp, format YYYY-MM-DD HH:MM:SS, assumed UTC |
| amount | Transaction amount |
| merchant_category | grocery, fuel, dining, transport, electronics, clothing, pharmacy |
| city | City of the transaction |
| channel | POS, online or ATM |

Data arrives in two loads (transactions_day1.csv, then transactions_day2.csv) to test incremental loading. The files contain deliberate data-quality problems: duplicates, null values, invalid amounts, bad timestamps and city spelling variants.

Reference data: city_coords.csv (latitude and longitude of 12 Indian cities).

## 3. Expected output

- A scored table: every transaction gets a score (0 to 100), a band (LOW, MEDIUM, HIGH) and the list of rules that fired.
- A report of flagged (MEDIUM and HIGH) transactions, highest score first, with a short explanation.
- A rule coverage table showing which rule catches which injected fraud type.

## 4. Fraud indicators (features)

1. Velocity: number of transactions by one customer in the last 60 minutes.
2. Unusual amount: how far the amount is from the customer's normal, using a robust z-score (median and MAD).
3. Location change: distance and implied speed between the previous and current city.

## 5. Where AI is used

Rules compute every feature, score and band. AI only writes a short explanation for MEDIUM and HIGH transactions and never changes a score. AI output is validated against the input facts. If the AI is down or its answer is wrong, a template explanation is used instead.

## 6. Assumptions

- All timestamps are UTC.
- All amounts are in one currency.
- Data is synthetic; fraud labels are injected by our own generator.
- Distance is a straight line between city centres, not road distance.
- home_city, typical_spend and ground truth exist only in the generator and evaluation; the detector never reads them.
- A customer needs at least 5 earlier transactions before the amount rule can fire.
- The baseline for amounts is the last 50 earlier transactions of the same customer.
- Flagged transactions are not removed from the baseline (needs analyst-confirmed labels; future work).

## 7. Edge cases

| Case | What can go wrong | How the pipeline handles it |
|---|---|---|
| Duplicate rows | Same txn_id counted twice | Keep the first by raw_id; the rest are counted as duplicates_removed |
| Null keys | Missing txn_id or customer_id | Row goes to quarantine (NULL_TXN_ID, NULL_CUSTOMER) |
| Invalid amount | Empty, not a number, zero or negative | Quarantine (NULL_AMOUNT, NON_POSITIVE_AMOUNT) |
| Bad timestamp | Text like 31-13-2026 or "not a date" | Quarantine (BAD_TIMESTAMP) |
| First transaction of a customer | No history to compare with | Amount and travel features are NULL; their rules do not fire |
| Same timestamp | Order of two transactions is unclear | Order by ts_epoch, then txn_id |
| Unknown city | No coordinates to compute distance | Distance is NULL, travel rule skipped, warning logged |
| Rerun | Same data loaded twice | File hash check, INSERT OR IGNORE and INSERT OR REPLACE keep tables unchanged |
| LLM failure | Provider down or timeout | Template explanation is used; scores are unchanged |
| LLM wrong answer | Invented number or city | Validator rejects it; template is used |
| Leakage | Using information not available yet, or generator secrets | Baseline uses only earlier rows (shift 1); detector never reads generator-only tables |