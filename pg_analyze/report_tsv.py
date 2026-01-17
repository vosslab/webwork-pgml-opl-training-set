# Standard Library
import csv
import os


#============================================


def write_tsv(tsv_out_file: str, rows: list[dict]) -> None:
	out_dir = os.path.dirname(tsv_out_file)
	if out_dir:
		os.makedirs(out_dir, exist_ok=True)

	fieldnames = [
		"file",
		"needs_review",
		"confidence",
		"types",
		"input_count",
		"ans_count",
		"widget_kinds",
		"evaluator_kinds",
		"loadMacros",
		"includePGproblem",
	]

	with open(tsv_out_file, "w", encoding="utf-8", newline="") as f:
		w = csv.DictWriter(f, fieldnames=fieldnames, dialect="excel-tab")
		w.writeheader()
		for row in rows:
			w.writerow(row)

