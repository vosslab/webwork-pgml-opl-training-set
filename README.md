[![](https://img.shields.io/badge/license-CC%20BY--NC--SA%203.0-blue)](https://creativecommons.org/licenses/by-nc-sa/3.0/)
[![GitHub contributors](https://img.shields.io/github/contributors/vosslab/webwork-open-problem-PGML)](https://github.com/vosslab/webwork-open-problem-PGML/graphs/contributors)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/y/vosslab/webwork-open-problem-PGML)](https://github.com/vosslab/webwork-open-problem-PGML/graphs/commit-activity)
[![GitHub last commit](https://img.shields.io/github/last-commit/vosslab/webwork-open-problem-PGML)](https://github.com/vosslab/webwork-open-problem-PGML/commits/main)

# WeBWorK Open Problem Library (training fork)

This repository is a fork of the WeBWorK Open Problem Library (OPL) intended to organize and reduce problems for AI
training and related research, rather than to serve as a general-purpose WeBWorK library distribution.

## Documentation

- [docs/AUTHORS.md](docs/AUTHORS.md): Maintainers and notable contributors.
- [docs/CHANGELOG.md](docs/CHANGELOG.md): User-facing log of changes in this fork.
- [docs/CORPUS_CURATION.md](docs/CORPUS_CURATION.md): What was removed and how the corpus was curated.
- [docs/CORPUS_STATS.md](docs/CORPUS_STATS.md): Self-contained corpus statistics and comparisons.
- [docs/MARKDOWN_STYLE.md](docs/MARKDOWN_STYLE.md): Markdown rules for this repo.
- [docs/PYTHON_STYLE.md](docs/PYTHON_STYLE.md): Python coding rules for this repo.
- [docs/REPO_STYLE.md](docs/REPO_STYLE.md): Repo conventions (naming, structure, docs).

## Quick start

- Clone the repository.
- Problem files are `*.pg` under `OpenProblemLibrary/`, `Contrib/`, and `Pending/`.
- Treat this repo as a dataset source: select and transform problems as needed for your training pipeline.

## Purging methodology

This fork was curated by removing non-problem-source files and filtering `*.pg` problems down to PGML-style content
(including removing include-only wrappers and embedded blob payloads); see [docs/CORPUS_CURATION.md](docs/CORPUS_CURATION.md).

## Notes

- I want a corpus of pg files based on modern techniques and would prefer to not train any AI on legacy techniques.
- The corpus interaction profile is dominated by MathObjects numeric entry and PGchoice-style widgets; `pg_analyze`
  writes a small per-run summary to `summary/corpus_profile.tsv` under the chosen output directory.
- The upstream OPL is maintained at [openwebwork/webwork-open-problem-library](https://github.com/openwebwork/webwork-open-problem-library).
- OPL background and conventions: [WeBWorK Documentation Wiki](https://webwork.maa.org/wiki/Open_Problem_Library).
- Licensing details for problems in this repo: [OPL_LICENSE](OPL_LICENSE).
