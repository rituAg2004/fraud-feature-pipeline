"""Central settings: file paths, .env values and rules.yaml thresholds."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Project root = the folder that contains src/, sql/, config/ ...
BASE_DIR = Path(__file__).resolve().parent.parent

# Read the .env file if it exists. If it does not, nothing breaks.
load_dotenv(BASE_DIR / ".env")

# DB_PATH = BASE_DIR / "data" / "pipeline.db"
DB_PATH = Path(os.getenv("PIPELINE_DB", BASE_DIR / "data" / "pipeline.db"))
SCHEMA_PATH = BASE_DIR / "sql" / "01_schema.sql"
RULES_PATH = BASE_DIR / "config" / "rules.yaml"
SAMPLE_DIR = BASE_DIR / "data" / "sample"
REFERENCE_DIR = BASE_DIR / "data" / "reference"
OUTPUT_DIR = BASE_DIR / "output"


def load_rules(path=RULES_PATH):
    """Read rules.yaml and return it as a dictionary."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_llm_provider():
    """Return the LLM provider from .env: ollama, gemini or none (default)."""
    return os.getenv("LLM_PROVIDER", "none").lower()
