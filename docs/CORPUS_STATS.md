# Corpus statistics

This document is a self-contained snapshot of corpus-level statistics for:

- Full OPL (a local run against upstream OPL).
- This PGML corpus (this fork).

The `pg_analyze` output files used to generate these numbers are temporary and are not expected to be kept in-repo.

For the 2026-01-17 snapshot below, those outputs lived locally under `full_OPL_output/` and `PGML_corpus_output/`.

## Highlights

- The curated PGML corpus is about 13% of full OPL by `*.pg` file count (9,386 vs 72,734).
- Evaluator extraction is predominantly PGML-derived in this fork (most files are `widgets=some,eval=pgml_only`).
- The curated PGML corpus is much more math-heavy by DBsubject (77.8% vs 61.5%) and greatly reduces physics by DBsubject
  (0.6% vs 6.2%).

## How to regenerate

Run `pg_analyze` and point it at a directory you do not plan to commit:

```bash
python3 -m pg_analyze.main -r problems -o /tmp/pg_analyze_output
```

The most relevant reports for the tables below are:

- `summary/corpus_profile.tsv`
- `summary/counts_all.tsv`
- `summary/coverage_widgets_vs_evaluator_source.tsv`
- `summary/discipline_counts.tsv`
- `summary/discipline_coverage.tsv`

## Snapshot date

The numbers below were recorded on 2026-01-17.

## Corpus size

- Full OPL:
  - `*.pg` files: 72,734
  - DBsubject lines: 70,463
- PGML corpus (this fork):
  - `*.pg` files: 9,386
  - DBsubject lines: 9,017

## Interaction profile (macro census)

Counts below are "files that load this macro" (not total loads).

- Full OPL:
  - `PGML.pl`: 18,075
  - `MathObjects.pl`: 48,691
  - `parserPopUp.pl`: 7,964
  - `parserRadioButtons.pl`: 6,578
  - `parserAssignment.pl`: 1,616
- PGML corpus (this fork):
  - `PGML.pl`: 9,386
  - `MathObjects.pl`: 8,594
  - `parserPopUp.pl`: 2,508
  - `parserRadioButtons.pl`: 2,058
  - `parserAssignment.pl`: 528

## Interaction profile (type counts)

Counts below are per-file, multi-label type counts (a file may contribute to multiple types).

- Full OPL:
  - `numeric_entry`: 44,575
  - `multiple_choice`: 37,516
  - `multipart`: (see `counts_all.tsv`)
  - `graph_like`: 8,908
  - `assignment_ordering`: 1,616
  - `matching`: 189
- PGML corpus (this fork):
  - `numeric_entry`: 9,332
  - `multiple_choice`: 3,144
  - `multipart`: 4,879
  - `graph_like`: 1,305
  - `assignment_ordering`: 528
  - `matching`: 0

## Evaluator coverage buckets

Each file contributes to exactly one coverage bucket:

- Full OPL (`*.pg` files: 72,734):
  - `widgets=some,eval=ans_only`: 43,004
  - `widgets=some,eval=pgml_only`: 13,183
  - `widgets=some,eval=both`: 405
  - `widgets=some,eval=none`: 758
  - `widgets=none,eval=none`: 8,177
  - `widgets=none,eval=ans_only`: 7,196
  - `widgets=none,eval=pgml_only`: 11
- PGML corpus (this fork) (`*.pg` files: 9,386):
  - `widgets=some,eval=pgml_only`: 9,140
  - `widgets=some,eval=both`: 239
  - `widgets=none,eval=none`: 4
  - `widgets=none,eval=pgml_only`: 3

## Discipline breakdown (DBsubject lines)

Counts below are DBsubject-line counts (not file counts).

Full OPL (70,463 DBsubject lines):

- Math: 43,358 (61.5%)
- Physics: 4,384 (6.2%)
- Engineering: 5,911 (8.4%)
- Stats: 2,967 (4.2%)
- Finance: 854 (1.2%)
- CS: 54 (0.1%)
- Grade level: 356 (0.5%)
- Meta noise: 11,168 (15.8%)
- Meta missing: 911 (1.3%)
- Other: 500 (0.7%)
- Chemistry: 0
- Life sciences: 0

PGML corpus (this fork) (9,017 DBsubject lines):

- Math: 7,014 (77.8%)
- Engineering: 1,398 (15.5%)
- Stats: 100 (1.1%)
- Physics: 51 (0.6%)
- CS: 43 (0.5%)
- Finance: 15 (0.2%)
- Grade level: 10 (0.1%)
- Meta noise: 51 (0.6%)
- Meta missing: 312 (3.5%)
- Other: 23 (0.3%)
- Chemistry: 0
- Life sciences: 0

## Notes

- In OPL, "grade level" is overwhelmingly K-12 tagging (for example "Middle School"), not pedagogy.
- Chemistry and life sciences are structurally absent as DBsubject labels in both runs above.
