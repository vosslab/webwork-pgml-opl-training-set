# Corpus curation

This fork is curated to support AI training and related research focused on PGML-style WeBWorK problems, not to be a
complete general-purpose library distribution.

Training preference:

- I want a corpus of pg files based on modern techniques and would prefer to not train any AI on legacy techniques.

## What we removed

### Non problem-source files

We filtered the tree down to actual WeBWorK problem sources and removed other file types that are not needed for a
PGML-focused training corpus (for example `csv`, `txt`, `md`, and assorted repo metadata).

### Problems that are not PGML-based

Many `*.pg` files do not contain PGML blocks. Those were removed because this fork is specifically focused on problems
written in the PGML style.

Heuristics used:

- First pass: keep `*.pg` files that contain the string `PGML` (case-sensitive).
- Later pass: tighten to structural PGML blocks by requiring indentation-aware markers:
  - `^[[:space:]]*BEGIN_PGML`
  - `^[[:space:]]*END_PGML`

### Pointer or include-only stubs

Some `*.pg` files are wrappers that call another problem via `includePGproblem(...)`. Those were removed because the
standalone wrapper is not a useful training example when the real content lives elsewhere.

### Embedded blob payloads

A small number of problems contained very large base64-like blobs (often from embedded applets or packed data). Those
were removed because they are not good training targets and they inflate repository size.

Heuristic used:

- Detect base64-like character runs, for example:
  - `[A-Za-z0-9+/]{800,}={0,2}`

### Extreme line-length outliers

Most PGML problems include long narrative lines, but a subset have extreme line lengths (often due to huge LaTeX blocks,
large inline strings, or encoded content). These were treated as "likely messy or embedded-data heavy" and removed.

Heuristics used:

- Max line length thresholds (example cutoffs used: `> 200`, `> 400` bytes).
- Special case for "no whitespace" long lines to catch true blob payloads:
  - `length($0) > 400 && $0 !~ /[[:space:]]/`

## How we did it

### Enumerate, then operate from lists

The purge was done by repeatedly generating explicit file lists, inspecting samples, and then deleting from those lists.
This keeps the curation steps reproducible and auditable.

### NUL-safe pipelines

Because file paths can contain spaces, lists were generated and processed using NUL-safe pipelines (for example with
`-print0`, `xargs -0`, and `grep -Z`) and converted to newline-delimited lists only when needed for inspection.

### Encoding-safe scanning

Some tools emit multibyte warnings when scanning unknown encodings. When measuring line lengths and applying regexes,
`LC_ALL=C` was used to force byte-wise processing and keep scans predictable.
