-- Fraud Feature Pipeline: database schema (part 1: loading and cleaning)

-- Which files were already loaded. Same name + same hash = skip on rerun.
CREATE TABLE IF NOT EXISTS ingested_files (
    file_name   TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL,
    row_count   INTEGER,
    loaded_at   TEXT
);

-- Data exactly as it arrived. Everything is TEXT so a bad value never breaks the load.
CREATE TABLE IF NOT EXISTS raw_transactions (
    raw_id            INTEGER PRIMARY KEY,
    source_file       TEXT,
    txn_id            TEXT,
    customer_id       TEXT,
    ts                TEXT,
    amount            TEXT,
    merchant_category TEXT,
    city              TEXT,
    channel           TEXT,
    ingested_at       TEXT
);

-- Valid rows with proper types. The primary key on txn_id stops duplicates.
CREATE TABLE IF NOT EXISTS clean_transactions (
    txn_id            TEXT PRIMARY KEY,
    customer_id       TEXT NOT NULL,
    ts                TEXT NOT NULL,
    ts_epoch          INTEGER NOT NULL,
    amount            REAL NOT NULL,
    merchant_category TEXT,
    city              TEXT,
    channel           TEXT,
    source_file       TEXT,
    loaded_at         TEXT
);

-- Bad rows are kept here with a reason, never silently dropped.
CREATE TABLE IF NOT EXISTS quarantine_transactions (
    q_id              INTEGER PRIMARY KEY,
    source_file       TEXT,
    txn_id            TEXT,
    customer_id       TEXT,
    ts                TEXT,
    amount            TEXT,
    merchant_category TEXT,
    city              TEXT,
    channel           TEXT,
    reason            TEXT NOT NULL,
    quarantined_at    TEXT
);

-- World fact: latitude and longitude of each city, used to compute distance.
CREATE TABLE IF NOT EXISTS city_coords (
    city  TEXT PRIMARY KEY,
    lat   REAL NOT NULL,
    lon   REAL NOT NULL
);


-- ---------------------------------------------------------------
-- Part 2: features, scores, explanations, run log, generator-only tables
-- ---------------------------------------------------------------

-- One row per transaction with every computed fact. Rules and the AI explanation read only this.
CREATE TABLE IF NOT EXISTS features (
    txn_id             TEXT PRIMARY KEY,
    customer_id        TEXT,
    ts_epoch           INTEGER,
    amount             REAL,
    txn_count_1h       INTEGER,
    history_count      INTEGER,
    baseline_median    REAL,
    baseline_mad       REAL,
    amount_robust_z    REAL,
    prev_city          TEXT,
    minutes_since_prev REAL,
    distance_km        REAL,
    speed_kmh          REAL,
    computed_at        TEXT
);

-- Score from the rules only. triggered_rules explains the score; rules_version says which thresholds made it.
CREATE TABLE IF NOT EXISTS scores (
    txn_id           TEXT PRIMARY KEY,
    score            INTEGER NOT NULL,
    band             TEXT NOT NULL,
    triggered_rules  TEXT,
    rules_version    TEXT,
    scored_at        TEXT
);

-- Short explanation for flagged transactions. source says whether the AI or the template wrote it.
CREATE TABLE IF NOT EXISTS explanations (
    txn_id            TEXT PRIMARY KEY,
    explanation_text  TEXT NOT NULL,
    source            TEXT NOT NULL,
    model_name        TEXT,
    created_at        TEXT
);

-- Log of every pipeline run, so two runs can be compared in the rerun demo.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id              INTEGER PRIMARY KEY,
    started_at          TEXT,
    finished_at         TEXT,
    status              TEXT,
    files_loaded        INTEGER,
    rows_in             INTEGER,
    rows_clean          INTEGER,
    rows_quarantined    INTEGER,
    duplicates_removed  INTEGER,
    flagged_medium      INTEGER,
    flagged_high        INTEGER
);

-- Generator-only profile. The detector never reads this table.
CREATE TABLE IF NOT EXISTS gen_customers (
    customer_id    TEXT PRIMARY KEY,
    home_city      TEXT,
    typical_spend  REAL
);

-- Ground truth from the generator. Used only by the report as a sanity check, never by the detector.
CREATE TABLE IF NOT EXISTS eval_ground_truth (
    txn_id      TEXT PRIMARY KEY,
    is_fraud    INTEGER,
    fraud_type  TEXT
);