# Changelog

## 2026-01-17

- Update `README.md` to describe this repo as an AI-training-focused fork and refresh documentation links.
- Add `docs/CORPUS_CURATION.md` and link it from `README.md` to document how the corpus was curated.
- Add `pg_analyze/` (tokenizer + extractors + reports) to produce per-file JSON and TSV summaries for lightweight PG/PGML analysis.
- Improve `pg_analyze/` to handle heredocs during comment stripping, speed up line-number mapping, and make label reasons structured; bump JSON schema to version 2 and add a heredoc comment-stripping test.
- Reorganize `pg_analyze/` modules by merging scan/schema into `main.py`, merging reporting into `report.py`, and merging macro extraction into `extract_evaluators.py` without changing behavior.
- Convert heredoc tokenizer checks to pytest in `tests/test_tokenize_heredoc_comments.py`.
- Fix `pytest tests/` import path for `tests/test_tokenize_heredoc_comments.py` by explicitly adding the repo root to `sys.path`.
- Refactor `pg_analyze` to produce aggregate TSV reports by default (no per-file JSON), with optional `--per-file-tsv` and `--jsonl-out`, and add aggregation tests in `tests/test_pg_analyze_aggregate.py`.
- Update hygiene scripts/tests to skip missing tracked files when running in a working tree with unstaged deletions (`tests/test_indentation.py`, `tests/run_pyflakes.sh`).
- Add `tests/conftest.py` to put the repo root on `sys.path` for pytest.
- Remove per-file output options from `pg_analyze` (no per-file TSV/JSONL) to keep default behavior corpus-scale.
- Add regression tests for common PG/PGML patterns (heredocs, multiline ANS, MultiAnswer, PGML blanks) and count PGML blanks as inputs.
- Pre-strip heredoc bodies before running extractors and record `named_ans_rule(...)` references from evaluator expressions.
- Add aggregate-only "other" analysis reports (breakdown, restricted macro/widget/evaluator counts, PGML blank marker histograms, and small bounded samples) and label `unknown_pgml_blank` when PGML blanks exist but no evaluators/widgets are detected.
- Add cross-tab aggregate reports (type x widget, type x evaluator, widget x evaluator) plus a `coverage.tsv` sanity table.
- Ensure `coverage.tsv` always includes all four buckets (including zeros) and extend aggregation tests to cover the new cross-tab TSV outputs.
- Make `needs_review.tsv` actionable by bucketing and stratifying samples, and add `needs_review_*_counts.tsv` summaries (bucket/type/macro).
- Write curated bucket file lists under the output directory (`type/`, `widget/`, `evaluator/`) with one path per line for sampling/grepping without per-file JSON or TSV.
- Improve detection of common PGchoicemacros-based widgets/evaluators and add explicit `graph_like` and `essay` labels to reduce the "other" bucket.
- Add evaluator coverage instrumentation reports (`ans_token_hist.tsv`, `evaluator_coverage_reasons.tsv`) plus restricted macro counts and bounded samples to target missing evaluator detection in PGML-heavy files.
