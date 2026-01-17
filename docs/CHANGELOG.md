# Changelog

## 2026-01-17

- Update `README.md` to describe this repo as an AI-training-focused fork and refresh documentation links.
- Add `docs/CORPUS_CURATION.md` and link it from `README.md` to document how the corpus was curated.
- Add `pg_analyze/` (tokenizer + extractors + reports) to produce per-file JSON and TSV summaries for lightweight PG/PGML analysis.
- Improve `pg_analyze/` to handle heredocs during comment stripping, speed up line-number mapping, and make label reasons structured; bump JSON schema to version 2 and add a heredoc comment-stripping test.
- Reorganize `pg_analyze/` modules by merging scan/schema into `main.py`, merging reporting into `report.py`, and merging macro extraction into `extract_evaluators.py` without changing behavior.
- Convert heredoc tokenizer checks to pytest in `tests/test_tokenize_heredoc_comments.py`.
- Fix `pytest tests/` import path for `tests/test_tokenize_heredoc_comments.py` by explicitly adding the repo root to `sys.path`.
