"""Tests for the AI explanation layer: validator, fallback and outage handling."""
from src.explain import explain_flagged
from src.llm_client import LLMClient, LLMUnavailable
import sqlite3
from tests.conftest import SCHEMA_PATH


class FakeClient(LLMClient):
    """Fake model that always returns the canned text. Never calls a real LLM."""

    name = "fake"

    def __init__(self, text):
        self.text = text

    def generate(self, prompt: str, timeout: int = 20) -> str:
        return self.text


class DownClient(LLMClient):
    """Fake model that is always unavailable."""

    name = "down"

    def generate(self, prompt: str, timeout: int = 20) -> str:
        raise LLMUnavailable("simulated outage")


def seed_flagged_txn(conn, txn_id="T8"):
    """Insert one HIGH transaction (Delhi -> Mumbai, amount 48000) into all tables."""
    conn.executemany(
        "INSERT INTO city_coords (city, lat, lon) VALUES (?, ?, ?)",
        [("Delhi", 28.61, 77.21), ("Mumbai", 19.08, 72.88)],
    )
    conn.execute(
        "INSERT INTO clean_transactions "
        "(txn_id, customer_id, ts, ts_epoch, amount, merchant_category, "
        " city, channel, source_file, loaded_at) "
        "VALUES (?, 'C012', '2026-09-10 10:20:00', 1789035600, 48000, "
        " 'electronics', 'Mumbai', 'POS', 'test.csv', '2026-01-01 00:00:00')",
        (txn_id,),
    )
    conn.execute(
        "INSERT INTO features "
        "(txn_id, customer_id, ts_epoch, amount, txn_count_1h, history_count, "
        " baseline_median, baseline_mad, amount_robust_z, prev_city, "
        " minutes_since_prev, distance_km, speed_kmh, computed_at) "
        "VALUES (?, 'C012', 1789035600, 48000, 1, 10, 1950, 400, 77.7, 'Delhi', "
        " 20, 1150, 3450, '2026-01-01 00:00:00')",
        (txn_id,),
    )
    conn.execute(
        "INSERT INTO scores "
        "(txn_id, score, band, triggered_rules, rules_version, scored_at) "
        "VALUES (?, 70, 'HIGH', 'IMPOSSIBLE_TRAVEL,UNUSUAL_AMOUNT', 'v1', "
        " '2026-01-01 00:00:00')",
        (txn_id,),
    )
    conn.commit()


def test_hallucinated_number_is_rejected(conn):
    """T8: a model answer with an invented number is replaced by the template."""
    seed_flagged_txn(conn)
    client = FakeClient("Amount 99,999 is far above this customer's usual 1,950.")

    counts = explain_flagged(conn, client)

    source, model = conn.execute(
        "SELECT source, model_name FROM explanations WHERE txn_id = 'T8'"
    ).fetchone()
    assert counts == {"llm": 0, "fallback": 1}
    assert source == "fallback"
    assert model == "template"

def test_correct_ai_answer_is_accepted(conn):
    """T8 companion: an answer that only uses real facts is stored as 'llm'."""
    seed_flagged_txn(conn)
    good = ("Amount 48,000 is far above this customer's usual 1,950; "
            "previous transaction was in Delhi 20 minutes earlier, "
            "about 1,150 km away.")
    client = FakeClient(good)

    counts = explain_flagged(conn, client)

    text, source, model = conn.execute(
        "SELECT explanation_text, source, model_name FROM explanations "
        "WHERE txn_id = 'T8'"
    ).fetchone()
    assert counts == {"llm": 1, "fallback": 0}
    assert source == "llm"
    assert model == "fake"
    assert text == good

def make_db():
    """Fresh in-memory database with the schema and one flagged transaction."""
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    seed_flagged_txn(db)
    return db


def test_pipeline_survives_llm_outage():
    """T9: with the LLM down, explanations fall back and scores stay identical."""
    good = ("Amount 48,000 is far above this customer's usual 1,950; "
            "previous transaction was in Delhi 20 minutes earlier, "
            "about 1,150 km away.")
    db_ok, db_down = make_db(), make_db()

    explain_flagged(db_ok, FakeClient(good))
    counts_down = explain_flagged(db_down, DownClient())

    sources_ok = db_ok.execute("SELECT source FROM explanations").fetchall()
    sources_down = db_down.execute("SELECT source FROM explanations").fetchall()
    scores_ok = db_ok.execute("SELECT * FROM scores ORDER BY txn_id").fetchall()
    scores_down = db_down.execute("SELECT * FROM scores ORDER BY txn_id").fetchall()

    assert sources_ok == [("llm",)]
    assert sources_down == [("fallback",)]
    assert counts_down == {"llm": 0, "fallback": 1}
    assert scores_ok == scores_down
    assert len(scores_down) == 1

    db_ok.close()
    db_down.close()