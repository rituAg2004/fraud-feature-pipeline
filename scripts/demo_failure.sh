#!/usr/bin/env bash
# Failure demo: the LLM is down, the pipeline still finishes, scores are identical.
set -e
DB_NORMAL=data/pipeline.db
DB_DOWN=data/demo_llm_down.db
rm -f "$DB_DOWN"

q() { python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute(sys.argv[2]).fetchall())" "$1" "$2"; }

echo "=== Normal run (already done, AI on) ==="
echo "scores (count, sum):"
q $DB_NORMAL "SELECT COUNT(*), SUM(score) FROM scores"
echo "explanations by source:"
q $DB_NORMAL "SELECT source, COUNT(*) FROM explanations GROUP BY source"

echo
echo "=== Run with LLM down (LLM_PROVIDER=none), fresh database ==="
LLM_PROVIDER=none PIPELINE_DB=$DB_DOWN python -m src.run_all
echo "scores (count, sum):"
q $DB_DOWN "SELECT COUNT(*), SUM(score) FROM scores"
echo "explanations by source:"
q $DB_DOWN "SELECT source, COUNT(*) FROM explanations GROUP BY source"

echo
echo "The AI is an optional last layer: when it fails, scores do not change."