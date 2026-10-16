# Sample output from a full run

Generated from a fresh database with `LLM_PROVIDER=ollama` (local model `llama3.2`).
Rows with `source = llm` were written by the model and accepted by the validator.
Rows with `source = fallback` use the template, either because the model failed or
because its answer was rejected (for example, it contained a number that was not in
the facts). Scores are identical either way.

Command: `python -m src.run_all` (after deleting `data/pipeline.db`)

## Run summary

```
transactions_day1.csv: loaded 3992 rows
transactions_day2.csv: loaded 657 rows
reference tables: 12 cities, 150 customers, 4558 ground-truth rows
split raw: 4557 valid, 92 quarantined
clean load: 4466 inserted, 91 duplicates removed
loaded 4466 rows from SQL features
stored 4466 feature rows
stored 4466 scores
AI answer rejected for T001660: number not in facts: 1
AI answer rejected for T002362: number not in facts: 1
AI answer rejected for T002378: number not in facts: 1
AI answer rejected for T003168: number not in facts: 1
AI answer rejected for T003171: number not in facts: 1
explained 20 rows: 15 by llm, 5 by fallback
wrote 82 flagged rows to output/flagged_report.csv
wrote rule coverage to output/rule_coverage.md
run 1 SUCCESS: files_loaded=2, rows_in=4649, rows_clean=4466,
  rows_quarantined=92, duplicates_removed=91, flagged_medium=82, flagged_high=0
pytest -q: 12 passed
```

## First rows of output/flagged_report.csv

```
txn_id,customer_id,ts,amount,city,score,band,triggered_rules,explanation,source
T001164,C074,2026-09-04 16:53:31,1247.69,Pune,40,MEDIUM,IMPOSSIBLE_TRAVEL,"The flagged transaction from Pune to Kolkata resulted in a significant distance of 1575.4 km, which may indicate a long-distance travel. The minutes since the previous city, Kolkata, are relatively short at 10.6, suggesting a possible anomaly in the travel pattern.",llm
T001388,C020,2026-09-05 06:16:14,692.67,Chennai,40,MEDIUM,IMPOSSIBLE_TRAVEL,"The flagged transaction from Chennai to Kolkata resulted in a significant distance of 1358.4 km, which may indicate a long-distance travel. The minutes since the previous city, Kolkata, are 29.8, suggesting a relatively short travel time, which could be inconsistent with the distance traveled.",llm
T001659,C006,2026-09-06 02:29:32,197.81,Kolkata,40,MEDIUM,VELOCITY,"The flagged transaction from Kolkata has a medium score of 40, indicating a moderate level of risk. The transaction's velocity, as measured by the 5 transactions in the last hour, is above the threshold, which may warrant further investigation.",llm
T001660,C006,2026-09-06 02:31:10,208.71,Kolkata,40,MEDIUM,VELOCITY,6 transactions by this customer within 60 minutes. Score 40 (MEDIUM).,fallback
```

## Rule coverage (output/rule_coverage.md)

Labels come from our own synthetic generator, so this only shows which rule
catches which injected pattern. It is a sanity check, not accuracy.

| fraud_type | is_fraud | transactions | flagged | VELOCITY | UNUSUAL_AMOUNT | IMPOSSIBLE_TRAVEL |
|---|---|---|---|---|---|---|
| card_testing | 1 | 42 | 23 | 23 | 0 | 0 |
| impossible_travel | 1 | 8 | 8 | 0 | 0 | 8 |
| large_amount | 1 | 8 | 8 | 0 | 8 | 0 |
| legit_large | 0 | 5 | 5 | 0 | 5 | 0 |
| normal | 0 | 4403 | 38 | 0 | 38 | 0 |

Not-fraud transactions that were still flagged: 43 of 4408.

## How to read this

- Only the fifth and later transactions of a card-testing burst fire VELOCITY,
  so 23 of 42 are flagged.
- Each injected fraud type trips exactly one rule, so every flag is MEDIUM.
  HIGH appears when two rules fire together (covered by a test).
- Legitimate large purchases and some normal high amounts are false positives.
- Only the top 20 flagged rows get an explanation per run (`max_items` in
  `config/rules.yaml`). The other flagged rows keep their score and fired rules.
- The validator rejected 5 model answers in this run because they contained a number
  that was not in the facts; those rows use the template instead.
- AI wording can vary between runs, so explanations may differ slightly if you rerun
  from a fresh database. Scores never change.