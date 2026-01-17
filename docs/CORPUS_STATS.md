# Corpus statistics

This document summarizes the current `output/` reports produced by `pg_analyze`.

Regenerate (overwrites `output/`):

```bash
python3 -m pg_analyze.main -r problems -o output
```

## Snapshot summary

From `output/summary/corpus_profile.tsv`:

- Total problem files (`*.pg`): 9,386
- Macro loads (files that `loadMacros(...)`):
  - `PGML.pl`: 9,386
  - `MathObjects.pl`: 8,594
  - `PGchoicemacros.pl`: 1,219
  - `PGgraphmacros.pl`: 1,305
  - `parserPopUp.pl`: 2,508
  - `parserRadioButtons.pl`: 2,058
  - `parserAssignment.pl`: 528
  - `parserMatch.pl`: 0
  - `MatchList(` token: 0 files

## Interaction profile

From `output/summary/counts_all.tsv` (type counts are per-file, multi-label):

- Types:
  - `numeric_entry`: 9,332
  - `multipart`: 4,879
  - `multiple_choice`: 3,144
  - `graph_like`: 1,305
  - `assignment_ordering`: 528
  - `fib_word`: 96
  - `essay`: 67

From `output/summary/coverage_widgets_vs_evaluator_source.tsv` (one bucket per file):

- `widgets=some,eval=pgml_only`: 9,140
- `widgets=some,eval=both`: 239
- `widgets=none,eval=none`: 4
- `widgets=none,eval=pgml_only`: 3

Evaluator sources (counts are evaluator occurrences, not files) are in
`output/summary/counts_all.tsv` under `group=evaluator_source`.

## Discipline breakdown (DBsubject)

`pg_analyze` buckets disciplines from lines matching `^## DBsubject(...)` and counts subject lines (not files).

Coverage from `output/summary/discipline_coverage.tsv`:

- `files_with_dbsubject`: 9,016
- `files_without_dbsubject`: 370
- `dbsubject_lines_total`: 9,017
- `dbsubject_lines_blank`: 279

Discipline counts from `output/summary/discipline_counts.tsv`:

- `math`: 7,014
- `engineering`: 1,398
- `stats`: 100
- `physics`: 51
- `meta_missing`: 312
- `grade_level`: 10
- `meta_noise`: 51
- `cs`: 43
- `finance`: 15
- `chemistry`: 0
- `life_sciences`: 0
- `other`: 23

For tuning the bucketing rules:

- Top subjects per discipline: `output/summary/discipline_subject_counts.tsv`
- Top unclassified subjects: `output/summary/discipline_unclassified_subject_counts.tsv`
- Sample files per discipline: `output/summary/discipline_samples.tsv`
- Per-file lists: `output/lists/discipline/*.txt`

## Notes

- Most of the large numbers above are properties of the current fork and its PGML-heavy curation, not universal OPL
  properties.
- `output/content_hints/*.tsv` are audit outputs only; they are not used for discipline classification.
