cat > docs/sample_output.md <<'EOF'
# Sample output from a full run

Generated from a fresh database with `LLM_PROVIDER=none`, so every explanation
below comes from the template fallback (`source = fallback`). With Gemini
enabled, the `source` column shows `llm` for rows the model explained and the
validator accepted.

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
LLM failed 3 times in a row; using template for the rest
explained 50 rows: 0 by llm, 50 by fallback
wrote 82 flagged rows to output/flagged_report.csv
wrote rule coverage to output/rule_coverage.md
run 1 SUCCESS: files_loaded=2, rows_in=4649, rows_clean=4466,
  rows_quarantined=92, duplicates_removed=91, flagged_medium=82, flagged_high=0
pytest -q: 12 passed
```

## Top 10 rows of output/flagged_report.csv

```
txn_id,customer_id,ts,amount,city,score,band,triggered_rules,explanation,source
T001164,C074,2026-09-04 16:53:31,1247.69,Pune,40,MEDIUM,IMPOSSIBLE_TRAVEL,"Previous transaction was in Kolkata 10.6 minutes earlier, about 1,575 km away. Score 40 (MEDIUM).",fallback
T001388,C020,2026-09-05 06:16:14,692.67,Chennai,40,MEDIUM,IMPOSSIBLE_TRAVEL,"Previous transaction was in Kolkata 29.8 minutes earlier, about 1,358 km away. Score 40 (MEDIUM).",fallback
T001659,C006,2026-09-06 02:29:32,197.81,Kolkata,40,MEDIUM,VELOCITY,5 transactions by this customer within 60 minutes. Score 40 (MEDIUM).,fallback
T001660,C006,2026-09-06 02:31:10,208.71,Kolkata,40,MEDIUM,VELOCITY,6 transactions by this customer within 60 minutes. Score 40 (MEDIUM).,fallback
T001662,C006,2026-09-06 02:34:51,218.32,Kolkata,40,MEDIUM,VELOCITY,7 transactions by this customer within 60 minutes. Score 40 (MEDIUM).,fallback
T001663,C006,2026-09-06 02:36:32,175.53,Kolkata,40,MEDIUM,VELOCITY,8 transactions by this customer within 60 minutes. Score 40 (MEDIUM).,fallback
T001755,C145,2026-09-06 10:00:02,406.51,Kolkata,40,MEDIUM,IMPOSSIBLE_TRAVEL,"Previous transaction was in Bengaluru 17.6 minutes earlier, about 1,561 km away. Score 40 (MEDIUM).",fallback
T002124,C134,2026-09-07 12:14:18,735.36,Kochi,40,MEDIUM,IMPOSSIBLE_TRAVEL,"Previous transaction was in Ahmedabad 11.3 minutes earlier, about 1,508 km away. Score 40 (MEDIUM).",fallback
T002176,C080,2026-09-07 16:04:24,510.78,Jaipur,40,MEDIUM,IMPOSSIBLE_TRAVEL,"Previous transaction was in Hyderabad 24.2 minutes earlier, about 1,095 km away. Score 40 (MEDIUM).",fallback
T002362,C073,2026-09-08 06:14:27,257.2,Mumbai,40,MEDIUM,VELOCITY,5 transactions by this customer within 60 minutes. Score 40 (MEDIUM).,fallback
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
- Only the top 50 flagged rows get an explanation per run (`max_items` in
  `config/rules.yaml`).
EOF