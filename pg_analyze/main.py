#!/usr/bin/env python3

# Standard Library
import argparse
import os

# Local modules
import pg_analyze.classify
import pg_analyze.extract_answers
import pg_analyze.extract_evaluators
import pg_analyze.extract_macros
import pg_analyze.extract_widgets
import pg_analyze.fs_scan
import pg_analyze.report_json
import pg_analyze.report_tsv
import pg_analyze.schemas
import pg_analyze.tokenize
import pg_analyze.wire_inputs


#============================================


def main() -> None:
	args = parse_args()

	roots = _default_roots(args.roots)
	pg_files = pg_analyze.fs_scan.scan_pg_files(roots)

	json_rows: list[dict] = []
	needs_review_paths: list[str] = []

	for file_path in pg_files:
		report, needs_review = analyze_file(file_path)
		if args.json_out_dir:
			pg_analyze.report_json.write_report_json(args.json_out_dir, file_path, report)

		row = build_tsv_row(report=report, needs_review=needs_review)
		json_rows.append(row)
		if needs_review:
			needs_review_paths.append(file_path)

	pg_analyze.report_tsv.write_tsv(args.tsv_out_file, json_rows)
	_write_needs_review(args.needs_review_file, needs_review_paths)


#============================================


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(prog="pg_analyze")

	parser.add_argument(
		"-r",
		"--roots",
		dest="roots",
		nargs="*",
		default=[],
		help="Roots to scan for .pg files (default: OpenProblemLibrary Contrib Pending, if present).",
	)
	parser.add_argument(
		"-j",
		"--json-out",
		dest="json_out_dir",
		default="output/pg_analyze/json",
		help="Directory for per-file JSON output.",
	)
	parser.add_argument(
		"-t",
		"--tsv-out",
		dest="tsv_out_file",
		default="output/pg_analyze/summary.tsv",
		help="Path for TSV summary output.",
	)
	parser.add_argument(
		"-n",
		"--needs-review",
		dest="needs_review_file",
		default="output/pg_analyze/needs_review.txt",
		help="Path for needs_review list output.",
	)

	return parser.parse_args()


#============================================


def _default_roots(roots: list[str]) -> list[str]:
	if roots:
		return roots
	candidates = ["OpenProblemLibrary", "Contrib", "Pending"]
	existing = [c for c in candidates if os.path.exists(c)]
	return existing if existing else ["."]


#============================================


def analyze_file(file_path: str) -> tuple[dict, bool]:
	text = _read_text_latin1(file_path)
	stripped = pg_analyze.tokenize.strip_comments(text)

	macros = pg_analyze.extract_macros.extract(stripped)
	widgets, pgml_info = pg_analyze.extract_widgets.extract(stripped)
	answers = pg_analyze.extract_answers.extract(stripped)
	evaluators = pg_analyze.extract_evaluators.extract(stripped)
	wiring = pg_analyze.wire_inputs.wire(widgets=widgets, evaluators=evaluators)

	report = {
		"schema_version": pg_analyze.schemas.JSON_SCHEMA_VERSION,
		"file": file_path,
		"macros": macros,
		"widgets": widgets,
		"evaluators": evaluators,
		"answers": answers,
		"wiring": wiring,
		"pgml": pgml_info,
	}

	labels, needs_review = pg_analyze.classify.classify(report)
	report["labels"] = labels

	return report, needs_review


#============================================


def build_tsv_row(*, report: dict, needs_review: bool) -> dict:
	widgets = report.get("widgets", [])
	evaluators = report.get("evaluators", [])
	macros = report.get("macros", {})
	labels = report.get("labels", {})

	widget_kinds = sorted({w.get("kind") for w in widgets if isinstance(w.get("kind"), str)})
	evaluator_kinds = sorted({e.get("kind") for e in evaluators if isinstance(e.get("kind"), str)})

	input_count = sum(1 for w in widgets if w.get("kind") in {"blank", "popup", "radio", "checkbox", "matching", "ordering"})
	ans_count = len(evaluators)

	return {
		"file": report.get("file", ""),
		"needs_review": str(needs_review).lower(),
		"confidence": labels.get("confidence", 0.0),
		"types": ",".join(labels.get("types", [])),
		"input_count": input_count,
		"ans_count": ans_count,
		"widget_kinds": ",".join(widget_kinds),
		"evaluator_kinds": ",".join(evaluator_kinds),
		"loadMacros": ",".join(macros.get("loadMacros", [])),
		"includePGproblem": ",".join(macros.get("includePGproblem", [])),
	}


#============================================


def _write_needs_review(path: str, files: list[str]) -> None:
	out_dir = os.path.dirname(path)
	if out_dir:
		os.makedirs(out_dir, exist_ok=True)
	with open(path, "w", encoding="utf-8") as f:
		for p in files:
			f.write(p + "\n")


#============================================


def _read_text_latin1(path: str) -> str:
	with open(path, "r", encoding="latin-1") as f:
		return f.read()


#============================================


if __name__ == "__main__":
	main()
