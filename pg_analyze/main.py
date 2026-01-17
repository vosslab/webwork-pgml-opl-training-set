#!/usr/bin/env python3

# Standard Library
import argparse
import os
import re
import sys
import time

# Local modules
import pg_analyze.aggregate
import pg_analyze.classify
import pg_analyze.extract_answers
import pg_analyze.extract_evaluators
import pg_analyze.extract_widgets
import pg_analyze.tokenize
import pg_analyze.wire_inputs


#============================================

def main() -> None:
	start = time.perf_counter()
	args = parse_args()

	roots = _default_roots(args.roots)
	_log(f"pg_analyze: scanning roots: {', '.join(roots)}")
	scan_start = time.perf_counter()
	pg_files = scan_pg_files(roots)
	_log(f"pg_analyze: found {len(pg_files)} .pg files in {time.perf_counter() - scan_start:.2f}s")

	os.makedirs(args.out_dir, exist_ok=True)
	out_dir_abs = os.path.abspath(args.out_dir)
	aggregator = pg_analyze.aggregate.Aggregator(needs_review_limit=200, out_dir=args.out_dir)

	try:
		_log("pg_analyze: analyzing files...")
		last_progress = time.perf_counter()
		for i, file_path in enumerate(pg_files, start=1):
			text = _read_text_latin1(file_path)
			record = analyze_text(text=text, file_path=file_path)
			aggregator.add_record(record)
			last_progress = _maybe_log_progress(last_progress, done=i, total=len(pg_files))
		_log("pg_analyze: writing outputs...")
		write_reports(args.out_dir, aggregator)
		_log("pg_analyze: writing PGML diagnostic dump...")
		_write_pgml_blocks_unknown_top_signatures(args.out_dir, aggregator)
	finally:
		aggregator.close()

	elapsed = time.perf_counter() - start
	_log(f"pg_analyze: done in {elapsed:.2f}s; output is located at {out_dir_abs}")


#============================================


def _log(msg: str) -> None:
	print(msg, file=sys.stderr, flush=True)


def _maybe_log_progress(last_progress: float, *, done: int, total: int) -> float:
	now = time.perf_counter()
	if now - last_progress < 2.0:
		return last_progress
	_log(f"pg_analyze: processed {done}/{total} files...")
	return now


#============================================

def _write_pgml_blocks_unknown_top_signatures(out_dir: str, aggregator: pg_analyze.aggregate.Aggregator) -> None:
	import pg_analyze.extract_evaluators
	import pg_analyze.tokenize

	out_path = os.path.join(out_dir, "diagnostics", "pgml_blocks_unknown_pgml_blank_top_signatures.txt")
	os.makedirs(os.path.dirname(out_path), exist_ok=True)

	top_signatures = aggregator.top_unknown_signatures(limit=10)
	sig_to_files: dict[str, list[str]] = {}
	for sig in top_signatures:
		files = sorted(aggregator._unknown_signature_files.get(sig, []))  # intentional: diagnostic-only
		sig_to_files[sig] = files

	max_blocks = 500
	max_chars_per_block = 20000
	max_total_bytes = 50 * 1024 * 1024

	blocks_written = 0
	bytes_written = 0

	with open(out_path, "w", encoding="utf-8") as f:
		f.write("# PGML block dump for unknown_pgml_blank: top signatures\n")
		f.write("# Signatures:\n")
		for sig in top_signatures:
			f.write(f"# - {sig}\n")
		f.write("# Notes: excludes BEGIN_PGML_HINT and BEGIN_PGML_SOLUTION blocks\n\n")

		i = 0
		while True:
			any_left = False
			for signature in top_signatures:
				files = sig_to_files.get(signature, [])
				if i >= len(files):
					continue
				any_left = True
				file_path = files[i]

				if blocks_written >= max_blocks or bytes_written >= max_total_bytes:
					return

				try:
					text = _read_text_latin1(file_path)
				except OSError:
					continue

				newlines = pg_analyze.tokenize.build_newline_index(text)
				blocks = pg_analyze.extract_evaluators.extract_pgml_blocks(text, newlines=newlines)

				for b in blocks:
					if blocks_written >= max_blocks or bytes_written >= max_total_bytes:
						return

					kind = b.get("kind", "")
					if kind in {"BEGIN_PGML_HINT", "BEGIN_PGML_SOLUTION"}:
						continue

					start_line = int(b.get("start_line", 0) or 0)
					blank_markers = int(b.get("blank_marker_count", 0) or 0)
					has_payload = int(b.get("has_payload", 0) or 0)
					block_text = b.get("text", "")
					if not isinstance(block_text, str):
						block_text = ""

					header = (
						f"=== file={file_path} signature={signature} kind={kind} start_line={start_line} "
						f"blank_markers={blank_markers} has_payload={has_payload} ===\n"
					)

					f.write(header)
					bytes_written += len(header.encode("utf-8"))

					if len(block_text) > max_chars_per_block:
						body = block_text[:max_chars_per_block] + "\n[TRUNCATED]\n"
					else:
						body = block_text
						if not body.endswith("\n"):
							body += "\n"

					f.write(body)
					bytes_written += len(body.encode("utf-8"))

					f.write("=== END ===\n\n")
					bytes_written += len("=== END ===\n\n".encode("utf-8"))

					blocks_written += 1

			if not any_left:
				break
			i += 1


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
		"-o",
		"--out-dir",
		dest="out_dir",
		required=True,
		help="Directory to write aggregate TSV reports.",
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

def scan_pg_files(roots: list[str]) -> list[str]:
	"""
	Return a sorted list of .pg file paths under the given roots.

	Returned paths are workspace-relative (using os.sep).
	"""
	found: list[str] = []
	for root in roots:
		if not os.path.exists(root):
			continue
		if os.path.isfile(root):
			if root.endswith(".pg"):
				found.append(root)
			continue
		for dirpath, dirnames, filenames in os.walk(root):
			dirnames[:] = [d for d in dirnames if d != ".git"]
			for filename in filenames:
				if not filename.endswith(".pg"):
					continue
				found.append(os.path.join(dirpath, filename))
	return sorted(set(found))


#============================================


def analyze_file(file_path: str) -> dict:
	text = _read_text_latin1(file_path)
	return analyze_text(text=text, file_path=file_path)

def analyze_text(*, text: str, file_path: str) -> dict:
	comment_stripped = pg_analyze.tokenize.strip_comments(text)
	clean = pg_analyze.tokenize.strip_heredocs(comment_stripped)
	newlines = pg_analyze.tokenize.build_newline_index(clean)
	raw_newlines = pg_analyze.tokenize.build_newline_index(text)

	macros = pg_analyze.extract_evaluators.extract_macros(clean, newlines=newlines)
	widgets, _pgml_info = pg_analyze.extract_widgets.extract(clean, newlines=newlines)
	answers = pg_analyze.extract_answers.extract(clean, newlines=newlines)
	ans_evaluators = pg_analyze.extract_evaluators.extract(clean, newlines=newlines)
	pgml_payload_evaluators = pg_analyze.extract_evaluators.extract_pgml_payload_evaluators(text, newlines=raw_newlines)
	evaluators = ans_evaluators + pgml_payload_evaluators
	wiring = pg_analyze.wire_inputs.wire(widgets=widgets, evaluators=evaluators)
	has_multianswer = bool(_MULTIANSWER_RX.search(clean))
	named_rule_refs = _extract_named_rule_refs(evaluators)

	report = {
		"file": file_path,
		"macros": macros,
		"widgets": widgets,
		"evaluators": evaluators,
		"answers": answers,
		"wiring": wiring,
		"pgml": _pgml_info,
		"has_multianswer": has_multianswer,
	}

	labels, _ = pg_analyze.classify.classify(report)

	widget_kinds = [w.get("kind") for w in widgets if isinstance(w.get("kind"), str)]
	evaluator_kinds = [e.get("kind") for e in evaluators if isinstance(e.get("kind"), str)]
	evaluator_sources = [e.get("source") for e in evaluators if isinstance(e.get("source"), str)]
	input_count = sum(1 for w in widgets if w.get("kind") in {"blank", "popup", "radio", "checkbox", "matching", "ordering"})
	ans_count = len(ans_evaluators)
	wiring_empty = len(wiring) == 0
	confidence = float(labels.get("confidence", 0.0))
	types = labels.get("types", [])
	reasons = labels.get("reasons", [])

	ans_token_count = len(_ANS_TOKEN_RX.findall(clean))
	has_ans_token = 1 if ans_token_count > 0 else 0
	has_cmp_token = 1 if bool(_CMP_TOKEN_RX.search(clean)) else 0
	has_num_cmp_token = 1 if bool(_NUM_CMP_TOKEN_RX.search(clean)) else 0
	has_str_cmp_token = 1 if bool(_STR_CMP_TOKEN_RX.search(clean)) else 0
	has_named_ans_rule_token = 1 if bool(_NAMED_ANS_RULE_TOKEN_RX.search(clean)) else 0
	has_named_ans_token = 1 if bool(_NAMED_ANS_TOKEN_RX.search(clean)) else 0
	has_ans_num_to_name = 1 if bool(_ANS_NUM_TO_NAME_RX.search(clean)) else 0
	has_install_problem_grader = 1 if bool(_INSTALL_PROBLEM_GRADER_RX.search(clean)) else 0
	has_ans_rule_token = 1 if bool(_ANS_RULE_TOKEN_RX.search(clean)) else 0
	has_named_popup_list_token = 1 if bool(_NAMED_POPUP_LIST_TOKEN_RX.search(clean)) else 0

	pgml_blank_count = int(_pgml_info.get("blank_count", 0) or 0)
	pgml_block_count = int(_pgml_info.get("block_count", 0) or 0)
	if pgml_blank_count > 0:
		widget_kinds.extend(["pgml_blank"] * pgml_blank_count)
		input_count += pgml_blank_count

	has_answer_ctor = 1 if (len(answers) > 0 or bool(_CTOR_TOKEN_RX.search(clean))) else 0

	ans_call_evaluator_count = len(ans_evaluators)
	pgml_payload_evaluator_count = len(pgml_payload_evaluators)
	ans_call_evaluator_kinds = [e.get("kind") for e in ans_evaluators if isinstance(e.get("kind"), str)]
	pgml_payload_evaluator_kinds = [e.get("kind") for e in pgml_payload_evaluators if isinstance(e.get("kind"), str)]

	record = {
		"file": file_path,
		"types": types,
		"confidence": confidence,
		"input_count": input_count,
		"ans_count": ans_count,
		"widget_kinds": widget_kinds,
		"evaluator_kinds": evaluator_kinds,
		"evaluator_sources": evaluator_sources,
		"ans_call_evaluator_count": ans_call_evaluator_count,
		"pgml_payload_evaluator_count": pgml_payload_evaluator_count,
		"ans_call_evaluator_kinds": ans_call_evaluator_kinds,
		"pgml_payload_evaluator_kinds": pgml_payload_evaluator_kinds,
		"loadMacros": macros.get("loadMacros", []),
		"reasons": reasons,
		"wiring_empty": wiring_empty,
		"has_multianswer": has_multianswer,
		"named_rule_refs": named_rule_refs,
		"pgml_block_count": pgml_block_count,
		"pgml_blank_marker_count": pgml_blank_count,
		"ans_token_count": ans_token_count,
		"has_ans_token": has_ans_token,
		"has_cmp_token": has_cmp_token,
		"has_num_cmp_token": has_num_cmp_token,
		"has_str_cmp_token": has_str_cmp_token,
		"has_answer_ctor": has_answer_ctor,
		"has_named_ans_rule_token": has_named_ans_rule_token,
		"has_named_ans_token": has_named_ans_token,
		"has_ans_num_to_name": has_ans_num_to_name,
		"has_install_problem_grader": has_install_problem_grader,
		"has_ans_rule_token": has_ans_rule_token,
		"has_named_popup_list_token": has_named_popup_list_token,
	}

	bucket = pg_analyze.aggregate.needs_review_bucket(record)
	needs_review = (confidence < 0.55) or ((ans_count >= 2) and wiring_empty) or bool(bucket)
	if needs_review and (not bucket):
		bucket = "low_confidence_misc"
	record["needs_review"] = needs_review
	record["needs_review_bucket"] = bucket
	return record


#============================================


def _read_text_latin1(path: str) -> str:
	with open(path, "r", encoding="latin-1") as f:
		return f.read()

#============================================


def write_reports(out_dir: str, aggregator: pg_analyze.aggregate.Aggregator) -> None:
	reports = aggregator.render_reports()
	for filename, content in reports.items():
		rel_path = pg_analyze.aggregate.OUTPUT_PATHS.get(filename, os.path.join("summary", filename))
		path = os.path.join(out_dir, rel_path)
		parent = os.path.dirname(path)
		if parent:
			os.makedirs(parent, exist_ok=True)
		if filename.endswith(".tsv"):
			content = _tsv_with_header(filename, content)
		with open(path, "w", encoding="utf-8") as f:
			f.write(content)

	_write_index(out_dir)


def _write_index(out_dir: str) -> None:
	lines = [
		"pg_analyze output index",
		"Note: TSV files start with '#' comment headers.",
		"",
		"Start here:",
		"- summary/coverage_widgets_vs_evaluator_source.tsv",
		"- summary/type_counts_all_files.tsv",
		"- needs_review/needs_review_bucket_counts.tsv",
		"",
		"Unknown/other categorization:",
		"- samples/unknown_pgml_blank_signature_counts.tsv",
		"- samples/other_signature_counts.tsv",
		"- diagnostics/pgml_blocks_unknown_pgml_blank_top_signatures.txt",
		"",
		"Then:",
		"- summary/evaluator_source_counts_all_files.tsv",
		"- counts/evaluator_kind_counts_pgml_payload_only.tsv",
		"",
		"Then:",
		"- cross_tabs/widget_kind_x_evaluator_kind_counts.tsv",
		"- cross_tabs/type_x_evaluator_source_counts.tsv",
		"",
		"For tuning:",
		"- macros/macro_counts_unknown_pgml_blank.tsv",
		"- needs_review/evaluator_missing_reasons_counts.tsv",
		"",
		"For examples:",
		"- diagnostics/pgml_blocks_unknown_pgml_blank_top_signatures.txt",
		"- samples/*.tsv",
		"",
	]

	path = os.path.join(out_dir, "INDEX.txt")
	with open(path, "w", encoding="utf-8") as f:
		f.write("\n".join(lines))


def _tsv_with_header(name: str, content: str) -> str:
	meta = _tsv_meta(name)
	lines: list[str] = [
		f"# Population: {meta['population']}",
		f"# Unit: {meta['unit']}",
		f"# Notes: {meta['notes']}",
		f"# Sorted: {meta['sorted']}",
		"# ----",
	]
	return "\n".join(lines) + "\n" + content


def _tsv_meta(name: str) -> dict[str, str]:
	default = {
		"population": "all .pg files under roots",
		"unit": "one row aggregates multiple files",
		"notes": "see column headers",
		"sorted": "count desc, then keys asc",
	}

	table: dict[str, dict[str, str]] = {
		"counts_by_type.tsv": {
			"unit": "each file contributes 1 to each type label it matches",
			"notes": "multi-label expansion; a file may increment multiple types",
		},
		"confidence_bins.tsv": {
			"unit": "each file contributes to exactly one confidence bin",
			"notes": "bins are 0.0-0.1 .. 0.9-1.0 based on confidence",
		},
		"coverage.tsv": {
			"unit": "each file contributes to exactly one bucket",
			"notes": "widgets=some means any widget detected; eval=ans_only/pgml_only/both/none based on evaluator source",
		},
		"evaluator_source_counts.tsv": {
			"unit": "each evaluator occurrence contributes to its source",
			"notes": "sources are ans_call and pgml_payload",
		},
		"macro_counts.tsv": {
			"unit": "each file contributes 1 to each macro it loadMacros(...) (deduped per file)",
			"notes": "counts macro file names ending in .pl/.pg",
		},
		"widget_counts.tsv": {
			"unit": "each detected widget occurrence contributes 1",
			"notes": "includes repeated pgml_blank occurrences based on PGML blank markers",
		},
		"evaluator_counts.tsv": {
			"unit": "each detected evaluator occurrence contributes 1",
			"notes": "includes evaluators from ANS(...) and PGML blank payloads",
		},
		"pgml_payload_evaluator_counts.tsv": {
			"unit": "each detected PGML-payload evaluator occurrence contributes 1",
			"notes": "only evaluators extracted from PGML blank payloads",
		},
		"type_by_widget.tsv": {
			"unit": "each file contributes once per (type, widget_kind) pair",
			"notes": "multi-label expansion; widget_kind=none means no widgets detected",
		},
		"type_by_evaluator.tsv": {
			"unit": "each file contributes once per (type, evaluator_kind) pair",
			"notes": "multi-label expansion; evaluator_kind=none means no evaluators detected",
		},
		"type_by_evaluator_source.tsv": {
			"unit": "each file contributes once per (type, evaluator_source) pair",
			"notes": "multi-label expansion; evaluator_source=none means no evaluators detected",
		},
		"widget_by_evaluator.tsv": {
			"unit": "each file contributes once per (widget_kind, evaluator_kind) pair",
			"notes": "widget_kind/evaluator_kind are deduped per file; 'none' means none detected",
		},
		"input_count_hist.tsv": {
			"unit": "each file contributes to exactly one input_count bucket",
			"notes": "buckets are 0,1,2,3,4,5-9,10-19,20+",
		},
		"ans_count_hist.tsv": {
			"unit": "each file contributes to exactly one ANS(...) count bucket",
			"notes": "counts only ANS-call evaluators; buckets are 0,1,2,3,4,5-9,10-19,20+",
		},
		"ans_token_hist.tsv": {
			"unit": "each file contributes to exactly one ANS token count bucket",
			"notes": "counts occurrences of 'ANS(' after comment/heredoc preprocessing; buckets are 0,1,2,3,4,5-9,10-19,20+",
		},
		"pgml_blank_marker_hist.tsv": {
			"unit": "each file contributes to exactly one PGML blank marker count bucket",
			"notes": "counts [_] markers inside PGML blocks; buckets are 0,1,2,3,4,5-9,10-19,20+",
		},
		"other_pgml_blank_hist.tsv": {
			"population": "files labeled other",
			"unit": "each file contributes to exactly one PGML blank marker count bucket",
			"notes": "counts [_] markers inside PGML blocks; buckets are 0,1,2,3,4,5-9,10-19,20+",
		},
		"needs_review.tsv": {
			"population": "a stratified sample of needs_review files",
			"unit": "one sampled file per row",
			"notes": "up to 40 samples per bucket, up to 200 total; includes compact signal columns",
			"sorted": "bucket-stratified, then lower confidence first",
		},
		"needs_review_bucket_counts.tsv": {
			"population": "all needs_review files",
			"unit": "each file contributes to exactly one needs_review bucket",
			"notes": "buckets are derived from extracted signals (widgets/evaluators/macros/counts)",
		},
		"needs_review_type_counts.tsv": {
			"population": "all needs_review files",
			"unit": "each file contributes 1 to each type label it matches",
			"notes": "multi-label expansion",
		},
		"needs_review_macro_counts.tsv": {
			"population": "all needs_review files",
			"unit": "each file contributes 1 to each macro it loadMacros(...) (deduped per file)",
			"notes": "restricted to files flagged needs_review",
		},
		"evaluator_coverage_reasons.tsv": {
			"population": "files with no evaluators detected",
			"unit": "each file contributes to exactly one reason bucket",
			"notes": "helps distinguish 'no ANS' vs 'missed extraction' signals",
		},
		"macro_counts_other.tsv": {
			"population": "files labeled other",
			"unit": "each file contributes 1 to each macro it loadMacros(...) (deduped per file)",
			"notes": "macro counts restricted to other-labeled files",
		},
		"macro_counts_unknown_pgml_blank.tsv": {
			"population": "files labeled unknown_pgml_blank",
			"unit": "each file contributes 1 to each macro it loadMacros(...) (deduped per file)",
			"notes": "macro counts restricted to unknown_pgml_blank files",
		},
		"macro_counts_eval_none_numeric_entry.tsv": {
			"population": "files labeled numeric_entry with no evaluators detected",
			"unit": "each file contributes 1 to each macro it loadMacros(...) (deduped per file)",
			"notes": "macro counts restricted to numeric_entry + evaluator none",
		},
		"macro_counts_eval_none_multiple_choice.tsv": {
			"population": "files labeled multiple_choice with no evaluators detected",
			"unit": "each file contributes 1 to each macro it loadMacros(...) (deduped per file)",
			"notes": "macro counts restricted to multiple_choice + evaluator none",
		},
		"other_breakdown.tsv": {
			"population": "files labeled other",
			"unit": "each file contributes to exactly one other bucket",
			"notes": "bucketed by extracted signals to separate missing detection vs true other",
		},
		"widget_counts_other.tsv": {
			"population": "files labeled other",
			"unit": "each detected widget occurrence contributes 1",
			"notes": "widget counts restricted to other-labeled files",
		},
		"evaluator_counts_other.tsv": {
			"population": "files labeled other",
			"unit": "each detected evaluator occurrence contributes 1",
			"notes": "evaluator counts restricted to other-labeled files",
		},
		"unknown_pgml_blank_signature_counts.tsv": {
			"population": "files labeled unknown_pgml_blank",
			"unit": "each file contributes to exactly one signature",
			"notes": "top signatures by count; pct is percent of unknown_pgml_blank files",
		},
		"unknown_pgml_blank_signature_samples.tsv": {
			"population": "a stratified sample of unknown_pgml_blank files",
			"unit": "one sampled file per row",
			"notes": "up to 50 files per signature across top signatures, capped overall; deterministic evenly spaced picks",
			"sorted": "signature count desc, then traversal-spread within signature",
		},
		"other_signature_counts.tsv": {
			"population": "files labeled other",
			"unit": "each file contributes to exactly one signature",
			"notes": "top signatures by count; pct is percent of other-labeled files",
		},
		"other_signature_samples.tsv": {
			"population": "a stratified sample of other-labeled files",
			"unit": "one sampled file per row",
			"notes": "up to 50 files per signature across top signatures, capped overall; deterministic evenly spaced picks",
			"sorted": "signature count desc, then traversal-spread within signature",
		},
	}

	meta = default.copy()
	meta.update(table.get(name, {}))
	return meta


#============================================


_MULTIANSWER_RX = re.compile(r"\bMultiAnswer\s*\(")

_NAMED_RULE_REF_RX = re.compile(r"\bnamed_ans_rule\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")

_ANS_TOKEN_RX = re.compile(r"\bANS\s*\(")
_CMP_TOKEN_RX = re.compile(r"->\s*cmp\s*\(")
_NUM_CMP_TOKEN_RX = re.compile(r"\bnum_cmp\s*\(")
_STR_CMP_TOKEN_RX = re.compile(r"\b(str_cmp|string_cmp)\s*\(")
_NAMED_ANS_RULE_TOKEN_RX = re.compile(r"\b(NAMED_ANS_RULE|named_ans_rule)\s*\(")
_NAMED_ANS_TOKEN_RX = re.compile(r"\bNAMED_ANS\s*\(")
_ANS_NUM_TO_NAME_RX = re.compile(r"\bANS_NUM_TO_NAME\s*\(")
_INSTALL_PROBLEM_GRADER_RX = re.compile(r"\binstall_problem_grader\b")
_CTOR_TOKEN_RX = re.compile(r"\b(Real|Formula|Compute|String|List|Vector|Point)\s*\(")
_ANS_RULE_TOKEN_RX = re.compile(r"\b(ans_rule|answerRule|ans_box)\s*\(")
_NAMED_POPUP_LIST_TOKEN_RX = re.compile(r"\bNAMED_POP_UP_LIST\s*\(")


def _extract_named_rule_refs(evaluators: list[dict]) -> list[str]:
	names: list[str] = []
	for ev in evaluators:
		expr = ev.get("expr", "")
		if not isinstance(expr, str):
			continue
		for m in _NAMED_RULE_REF_RX.finditer(expr):
			name = m.group(1)
			if name not in names:
				names.append(name)
	return names


#============================================


if __name__ == "__main__":
	main()
