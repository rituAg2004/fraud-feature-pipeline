# Design and Decision Note: Fraud Feature Pipeline (DAI-023)

## Goal and scope

Turn synthetic card transactions into three fraud indicators (velocity, unusual amount, location change), a rule-based score from 0 to 100 and a short explanation for each flagged transaction. The project is a small single-machine pipeline using Python and SQLite; it favours a finished, tested core over many tools.

## Key decisions and why

- **Rules score, AI only explains.** Thresholds live in `config/rules.yaml`, so the score is auditable and repeatable. An LLM is not repeatable enough to score, and there are no real fraud labels. The AI writes explanation text only and never changes a score.
- **Robust z-score for amounts.** One large purchase inflates mean and standard deviation and hides later fraud (laptop example: normal z = 0.05, robust z about 250). Median and MAD barely move. If MAD is 0, a fallback avoids divide-by-zero.
- **SQLite for storage, pandas for median and MAD.** SQLite handles time windows well (velocity, previous city) but has no median function, so pandas computes the baseline. No server is needed, so setup is easy.
- **Raw, clean and quarantine layers.** Raw keeps data exactly as it arrived. Bad rows go to quarantine with a reason and are never silently dropped.
- **Idempotent loading.** Files are skipped by hash, clean rows use `INSERT OR IGNORE`, features and scores use `INSERT OR REPLACE`. Running twice changes nothing (test `test_rerun_is_idempotent`).
- **AI behind one interface with a validator and fallback.** `llm_client.py` is the only place that knows about providers (`gemini`, `none`). The validator rejects an answer containing a number or city that is not in the input facts, and a deterministic template is used instead. If the provider fails repeatedly, the rest of the run uses templates.
- **Generator-only data kept away from the detector.** `home_city`, `typical_spend` and ground truth are never read by the detector (test `test_detector_independent_of_generator_tables`).

## Trade-offs

- **Full recompute vs incremental features.** Features are recomputed for every row on each run. This is simple and correct, but would not scale to very large data.
- **Rule transparency vs recall.** Rules are easy to explain and change but use fixed thresholds. Velocity only fires from the fifth transaction, so 23 of 42 card-testing transactions are flagged.
- **Synthetic vs real data.** Synthetic data lets me inject duplicates, nulls and fraud patterns, but labels come from my own generator, so the rule coverage table is a sanity check, not accuracy.

## Alternatives considered

Mean and standard deviation (masking problem); IQR fence; Isolation Forest; Random Forest or XGBoost (labels are injected by my own generator, so accuracy would be circular); a Kaggle dataset (often pre-cleaned and missing customer and city); Kafka streaming (unneeded for this scope).

## Limitations and next steps

- On the sample data no transaction reaches HIGH, because each injected fraud type triggers one rule; HIGH is covered by a unit test.
- Very consistent spenders (small MAD) produce some false positives (38 of 4,403 normal transactions); a minimum-MAD floor could reduce this.
- Next: real labels with a Random Forest or XGBoost model blended with the rules and scored by PR-AUC on a time-based split; incremental features; analyst feedback to exclude confirmed fraud from baselines.