#!/usr/bin/env python3

# Standard Library
import argparse
import hashlib
import os
import re
import sys
import time

# Local modules
import pg_analyze.aggregate
import pg_analyze.classify
import pg_analyze.discipline
import pg_analyze.extract_answers
import pg_analyze.extract_evaluators
import pg_analyze.extract_widgets
import pg_analyze.tokenize
import pg_analyze.wire_inputs


#============================================

_STAR_SPEC_SIMPLE_VAR_RX = re.compile(r"^\$([A-Za-z_]\w*)$")

_ANSWERFORMATHELP_MATRICES_RX = re.compile(
	r"""(?i)\bAnswerFormatHelp\s*\(\s*['"]matrices['"]\s*\)"""
)

_RANDOMIZATION_CALL_RX = re.compile(r"\b(?:random|list_random)\s*\(")
_RESOURCES_QUOTED_RX = re.compile(r"""['"]([^'"]+)['"]""")

_ASSET_SIGNAL_RXS: dict[str, re.Pattern] = {
	"image_call": re.compile(r"\bimage\s*\(", re.IGNORECASE),
	"includegraphics": re.compile(r"\\includegraphics\b"),
	"init_graph_call": re.compile(r"\binit_graph\s*\(", re.IGNORECASE),
	"plot_functions_call": re.compile(r"\bplot_functions\s*\(", re.IGNORECASE),
	"applet_token": re.compile(r"\bApplet\b"),
	"geogebra_token": re.compile(r"\bGeoGebra\b", re.IGNORECASE),
	"livegraphics_token": re.compile(r"\bLiveGraphics\b"),
	"js_script_tag": re.compile(r"<\s*script\b", re.IGNORECASE),
	"javascript_token": re.compile(r"\bjavascript\b", re.IGNORECASE),
}


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
	roots_abs = [os.path.abspath(r) for r in roots]

	try:
		_log("pg_analyze: analyzing files...")
		last_progress = time.perf_counter()
		for i, file_path in enumerate(pg_files, start=1):
			raw_bytes = _read_bytes(file_path)
			text = raw_bytes.decode("latin-1")
			record = analyze_text(text=text, file_path=file_path)
			record["file_rel"] = _file_rel_to_roots(file_path=file_path, roots_abs=roots_abs)
			record["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
			record["sha256_ws"] = hashlib.sha256(raw_bytes.translate(None, b" \t\r\n")).hexdigest()
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
	symbol_table = pg_analyze.extract_answers.build_symbol_table(answers)
	ans_evaluators = pg_analyze.extract_evaluators.extract(clean, newlines=newlines)
	pgml_payload_evaluators, pgml_star_spec_evaluators = pg_analyze.extract_evaluators.extract_pgml_embedded_evaluators(text, newlines=raw_newlines)
	_refine_star_spec_evaluators(pgml_star_spec_evaluators, symbol_table=symbol_table)
	evaluators = ans_evaluators + pgml_payload_evaluators + pgml_star_spec_evaluators
	wiring = pg_analyze.wire_inputs.wire(widgets=widgets, evaluators=evaluators)
	has_multianswer = bool(_MULTIANSWER_RX.search(clean))
	named_rule_refs = _extract_named_rule_refs(evaluators)

	subtype_tags = _extract_subtype_tags_from_pgml(text)
	resource_exts = _extract_resource_exts(clean, newlines=newlines)
	has_randomization = 1 if bool(_RANDOMIZATION_CALL_RX.search(clean)) else 0
	asset_signals = _detect_asset_signals(clean)

	report = {
		"file": file_path,
		"macros": macros,
		"widgets": widgets,
		"evaluators": evaluators,
		"answers": answers,
		"wiring": wiring,
		"pgml": _pgml_info,
		"has_multianswer": has_multianswer,
		"subtype_tags": subtype_tags,
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
	has_matchlist_token = 1 if bool(_MATCHLIST_TOKEN_RX.search(clean)) else 0

	pgml_blank_count = int(_pgml_info.get("blank_count", 0) or 0)
	pgml_block_count = int(_pgml_info.get("block_count", 0) or 0)
	if pgml_blank_count > 0:
		widget_kinds.extend(["pgml_blank"] * pgml_blank_count)
		input_count += pgml_blank_count

	has_answer_ctor = 1 if (len(answers) > 0 or bool(_CTOR_TOKEN_RX.search(clean))) else 0

	ans_call_evaluator_count = len(ans_evaluators)
	pgml_payload_evaluator_count = len(pgml_payload_evaluators)
	pgml_star_spec_evaluator_count = len(pgml_star_spec_evaluators)
	ans_call_evaluator_kinds = [e.get("kind") for e in ans_evaluators if isinstance(e.get("kind"), str)]
	pgml_payload_evaluator_kinds = [e.get("kind") for e in pgml_payload_evaluators if isinstance(e.get("kind"), str)]
	pgml_star_spec_evaluator_kinds = [e.get("kind") for e in pgml_star_spec_evaluators if isinstance(e.get("kind"), str)]

	record = {
		"file": file_path,
		"types": types,
		"subtype_tags": subtype_tags,
		"confidence": confidence,
		"input_count": input_count,
		"ans_count": ans_count,
		"widget_kinds": widget_kinds,
		"evaluator_kinds": evaluator_kinds,
		"evaluator_sources": evaluator_sources,
		"ans_call_evaluator_count": ans_call_evaluator_count,
		"pgml_payload_evaluator_count": pgml_payload_evaluator_count,
		"pgml_star_spec_evaluator_count": pgml_star_spec_evaluator_count,
		"ans_call_evaluator_kinds": ans_call_evaluator_kinds,
		"pgml_payload_evaluator_kinds": pgml_payload_evaluator_kinds,
		"pgml_star_spec_evaluator_kinds": pgml_star_spec_evaluator_kinds,
		"loadMacros": macros.get("loadMacros", []),
		"reasons": reasons,
		"wiring_empty": wiring_empty,
		"has_multianswer": has_multianswer,
		"named_rule_refs": named_rule_refs,
		"pgml_block_count": pgml_block_count,
		"pgml_blank_marker_count": pgml_blank_count,
		"ans_token_count": ans_token_count,
		"has_randomization": has_randomization,
		"has_resources": 1 if resource_exts else 0,
		"resource_exts": resource_exts,
		"asset_signals": asset_signals,
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
		"has_matchlist_token": has_matchlist_token,
	}

	dbsubject_pairs = pg_analyze.discipline.extract_dbsubjects_pairs(text)
	dbsubjects_raw = [raw for raw, _norm in dbsubject_pairs]
	dbsubjects = [norm for _raw, norm in dbsubject_pairs]
	dbsubject_lines_total = len(dbsubject_pairs)
	dbsubject_lines_blank = sum(1 for raw, _norm in dbsubject_pairs if not raw.strip())
	has_dbsubject = 1 if dbsubject_lines_total > 0 else 0
	has_dbsubject_nonblank = 1 if any(raw.strip() for raw in dbsubjects_raw) else 0
	discipline_primary = pg_analyze.discipline.primary_discipline(dbsubjects)
	discipline_primary_subject = pg_analyze.discipline.primary_subject(dbsubjects)
	discipline_primary_subject_raw = ""
	for raw in dbsubjects_raw:
		if raw.strip():
			discipline_primary_subject_raw = raw.strip()
			break

	dbchapter_pairs = pg_analyze.discipline.extract_dbchapters_pairs(text)
	dbchapters_raw = [raw for raw, _norm in dbchapter_pairs]
	dbchapters = [norm for _raw, norm in dbchapter_pairs]
	dbchapter_lines_total = len(dbchapter_pairs)
	dbchapter_lines_blank = sum(1 for raw, _norm in dbchapter_pairs if not raw.strip())
	has_dbchapter = 1 if dbchapter_lines_total > 0 else 0
	has_dbchapter_nonblank = 1 if any(raw.strip() for raw in dbchapters_raw) else 0

	dbsection_pairs = pg_analyze.discipline.extract_dbsections_pairs(text)
	dbsections_raw = [raw for raw, _norm in dbsection_pairs]
	dbsections = [norm for _raw, norm in dbsection_pairs]
	dbsection_lines_total = len(dbsection_pairs)
	dbsection_lines_blank = sum(1 for raw, _norm in dbsection_pairs if not raw.strip())
	has_dbsection = 1 if dbsection_lines_total > 0 else 0
	has_dbsection_nonblank = 1 if any(raw.strip() for raw in dbsections_raw) else 0

	record["dbsubject_pairs"] = dbsubject_pairs
	record["dbchapter_pairs"] = dbchapter_pairs
	record["dbsection_pairs"] = dbsection_pairs
	record["dbsubjects_raw"] = dbsubjects_raw
	record["dbsubjects"] = dbsubjects
	record["dbsubject_lines_total"] = dbsubject_lines_total
	record["dbsubject_lines_blank"] = dbsubject_lines_blank
	record["has_dbsubject"] = has_dbsubject
	record["has_dbsubject_nonblank"] = has_dbsubject_nonblank
	record["discipline_primary"] = discipline_primary
	record["discipline_primary_subject"] = discipline_primary_subject
	record["discipline_primary_subject_raw"] = discipline_primary_subject_raw

	record["dbchapters_raw"] = dbchapters_raw
	record["dbchapters"] = dbchapters
	record["dbchapter_lines_total"] = dbchapter_lines_total
	record["dbchapter_lines_blank"] = dbchapter_lines_blank
	record["has_dbchapter"] = has_dbchapter
	record["has_dbchapter_nonblank"] = has_dbchapter_nonblank

	record["dbsections_raw"] = dbsections_raw
	record["dbsections"] = dbsections
	record["dbsection_lines_total"] = dbsection_lines_total
	record["dbsection_lines_blank"] = dbsection_lines_blank
	record["has_dbsection"] = has_dbsection
	record["has_dbsection_nonblank"] = has_dbsection_nonblank

	record["chem_terms_present"] = pg_analyze.discipline.chem_terms_present(text)
	record["bio_terms_present"] = pg_analyze.discipline.bio_terms_present(text)

	chem_hint = pg_analyze.discipline.first_chem_hint(text)
	if chem_hint is not None:
		record["chem_hint"] = chem_hint
	bio_hint = pg_analyze.discipline.first_bio_hint(text)
	if bio_hint is not None:
		record["bio_hint"] = bio_hint

	bucket = pg_analyze.aggregate.needs_review_bucket(record)
	needs_review = (confidence < 0.55) or ((ans_count >= 2) and wiring_empty) or bool(bucket)
	if needs_review and (not bucket):
		bucket = "low_confidence_misc"
	record["needs_review"] = needs_review
	record["needs_review_bucket"] = bucket
	return record


#============================================


def _read_text_latin1(path: str) -> str:
	return _read_bytes(path).decode("latin-1")


def _read_bytes(path: str) -> bytes:
	with open(path, "rb") as f:
		return f.read()


def _file_rel_to_roots(*, file_path: str, roots_abs: list[str]) -> str:
	abs_file = os.path.abspath(file_path)
	best_root: str | None = None
	for r in roots_abs:
		r2 = os.path.abspath(r)
		if abs_file == r2:
			best_root = r2
			break
		prefix = r2 + os.sep
		if abs_file.startswith(prefix):
			if best_root is None or len(r2) > len(best_root):
				best_root = r2
	if best_root is None:
		return os.path.basename(file_path)
	return os.path.relpath(abs_file, best_root)


def _extract_resource_exts(text: str, *, newlines: list[int]) -> list[str]:
	"""
	Extract resource file extensions from Resources(...) calls.

	This is intentionally shallow; it is used for aggregate-only reporting.
	"""
	calls = pg_analyze.tokenize.iter_calls(text, {"Resources"}, newlines=newlines)
	exts: set[str] = set()
	for c in calls:
		for m in _RESOURCES_QUOTED_RX.finditer(c.arg_text):
			val = m.group(1).strip()
			if not val:
				continue
			_ext = os.path.splitext(val)[1].lower()
			if not _ext:
				continue
			ext = _ext.lstrip(".")
			if not ext:
				continue
			exts.add(ext)
	return sorted(exts)


def _detect_asset_signals(text: str) -> list[str]:
	"""
	Return a list of lightweight, file-level asset/external-dependency signals.

	This is intentionally shallow and is used for aggregate-only reporting.
	"""
	signals: list[str] = []
	for name, rx in _ASSET_SIGNAL_RXS.items():
		if rx.search(text):
			signals.append(name)
	return sorted(signals)


#============================================


def _refine_star_spec_evaluators(evaluators: list[dict], *, symbol_table: dict[str, str]) -> None:
	"""
	Refine pgml_star_spec evaluators into more useful kinds.

	This is intentionally shallow:
	- "*{$var}" becomes star_spec_indirect (or _numeric/_string when ctor is known)
	- "*{expr}" becomes star_spec_expr
	"""
	for e in evaluators:
		if not isinstance(e, dict):
			continue
		if e.get("source") != "pgml_star_spec":
			continue

		kind = e.get("kind")
		if isinstance(kind, str) and kind and kind != "star_spec":
			continue

		expr = e.get("expr")
		if not isinstance(expr, str):
			continue
		expr = expr.strip()
		m = _STAR_SPEC_SIMPLE_VAR_RX.match(expr)
		if m:
			var = m.group(1)
			ctor = symbol_table.get(var)
			if ctor == "String":
				e["kind"] = "star_spec_indirect_string"
			elif ctor in {"Real", "Formula", "Compute", "List", "Vector", "Point"}:
				e["kind"] = "star_spec_indirect_numeric"
			else:
				e["kind"] = "star_spec_indirect"
			continue

		if "$" in expr:
			e["kind"] = "star_spec_expr"


def _extract_subtype_tags_from_pgml(text: str) -> list[str]:
	"""
	Extract lightweight subtype tags from PGML regions only.
	"""
	tags: list[str] = []
	if _pgml_has_matrices_help(text):
		tags.append("matrix_entry")
	return tags


def _pgml_has_matrices_help(text: str) -> bool:
	if not isinstance(text, str) or not text:
		return False
	newlines = pg_analyze.tokenize.build_newline_index(text)
	blocks = pg_analyze.extract_evaluators.extract_pgml_blocks(text, newlines=newlines)
	for b in blocks:
		if not isinstance(b, dict):
			continue
		kind = b.get("kind", "")
		if kind != "BEGIN_PGML":
			continue
		block_text = b.get("text", "")
		if not isinstance(block_text, str):
			continue
		if _ANSWERFORMATHELP_MATRICES_RX.search(block_text):
			return True
	return False

#============================================


def write_reports(out_dir: str, aggregator: pg_analyze.aggregate.Aggregator) -> None:
	_remove_obsolete_outputs(out_dir)
	_remove_ds_store(out_dir)

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
	_remove_empty_output_dirs(out_dir)


def _remove_obsolete_outputs(out_dir: str) -> None:
	paths = [
		# old per-topic stats outputs (replaced by summary/*.tsv masters)
		"summary/type_counts_all_files.tsv",
		"summary/confidence_bins.tsv",
		"summary/evaluator_source_counts_all_files.tsv",

		"counts/macro_load_counts_all_files.tsv",
		"counts/widget_kind_counts_all_files.tsv",
		"counts/evaluator_kind_counts_all_files.tsv",
		"counts/evaluator_kind_counts_pgml_payload_only.tsv",
		"counts/evaluator_kind_counts_pgml_star_spec_only.tsv",
		"counts/subtype_tag_counts_all_files.tsv",

		"cross_tabs/type_x_widget_kind_counts.tsv",
		"cross_tabs/type_x_evaluator_kind_counts.tsv",
		"cross_tabs/type_x_evaluator_source_counts.tsv",
		"cross_tabs/widget_kind_x_evaluator_kind_counts.tsv",

		"histograms/input_count_hist.tsv",
		"histograms/ans_count_hist.tsv",
		"histograms/ans_token_hist.tsv",
		"histograms/pgml_blank_marker_hist.tsv",
		"histograms/other_pgml_blank_hist.tsv",

		"macros/macro_counts_other.tsv",
		"macros/macro_counts_unknown_pgml_blank.tsv",
		"macros/macro_counts_eval_none_numeric_entry.tsv",
		"macros/macro_counts_eval_none_multiple_choice.tsv",
	]

	for rel in paths:
		path = os.path.join(out_dir, rel)
		try:
			os.remove(path)
		except OSError:
			pass


def _remove_empty_output_dirs(out_dir: str) -> None:
	paths = [
		"counts",
		"cross_tabs",
		"histograms",
		"macros",
	]
	for rel in paths:
		path = os.path.join(out_dir, rel)
		try:
			if os.path.isdir(path) and not os.listdir(path):
				os.rmdir(path)
		except OSError:
			pass


def _remove_ds_store(out_dir: str) -> None:
	for dirpath, _dirnames, filenames in os.walk(out_dir):
		if ".DS_Store" not in filenames:
			continue
		path = os.path.join(dirpath, ".DS_Store")
		try:
			os.remove(path)
		except OSError:
			pass


def _write_index(out_dir: str) -> None:
	lines = [
		"pg_analyze output index",
		"Note: TSV files start with '#' comment headers.",
		"",
		"Start here:",
		"- summary/coverage_widgets_vs_evaluator_source.tsv",
		"- summary/corpus_profile.tsv",
		"- summary/counts_all.tsv",
		"- summary/cross_tabs_all.tsv",
		"- summary/histograms_all.tsv",
		"- needs_review/needs_review_bucket_counts.tsv",
		"",
		"Unknown/other categorization:",
		"- samples/unknown_pgml_blank_signature_counts.tsv",
		"- samples/other_signature_counts.tsv",
		"- diagnostics/pgml_blocks_unknown_pgml_blank_top_signatures.txt",
		"- summary/macro_counts_segmented.tsv",
		"- summary/duplicate_clusters_top.tsv",
		"",
		"Then:",
		"- other/other_breakdown.tsv",
		"- other/widget_counts_other.tsv",
		"- other/evaluator_counts_other.tsv",
		"",
		"For tuning:",
		"- needs_review/evaluator_missing_reasons_counts.tsv",
		"",
		"Discipline breakdown:",
		"- summary/discipline_counts.tsv",
		"- summary/discipline_subject_counts.tsv",
		"- summary/discipline_unclassified_subject_counts.tsv",
		"- summary/discipline_samples.tsv",
		"- summary/discipline_coverage.tsv",
		"- content_hints/chem_terms_count.tsv",
		"- content_hints/bio_terms_count.tsv",
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
		"corpus_profile.tsv": {
			"unit": "one small profile snapshot per run",
			"notes": "key macro counts and token counts to summarize the corpus interaction profile",
			"sorted": "row order is fixed; do not sort",
		},
		"counts_all.tsv": {
			"unit": "each row is a (group, scope, key) count",
			"notes": "group and scope define the population; key is the item being counted",
			"sorted": "group asc, scope asc, count desc, key asc",
		},
		"cross_tabs_all.tsv": {
			"unit": "each row is a (row_dim, col_dim, row, col) count",
			"notes": "cross-tabs expand multi-labels; 'none' is used when nothing detected",
			"sorted": "row_dim asc, col_dim asc, count desc, row asc, col asc",
		},
		"histograms_all.tsv": {
			"unit": "each row is a (histogram, bin) count",
			"notes": "includes confidence_bin, input_count, ans_count, ans_token_count, PGML blank markers, and duplicate-cluster size histograms",
			"sorted": "histogram asc, count desc, bin asc",
		},
		"macro_counts_segmented.tsv": {
			"unit": "each row is a (segment, macro) count",
			"notes": "segment restricts the population (e.g. unknown_pgml_blank, eval_none_numeric_entry)",
			"sorted": "segment asc, count desc, macro asc",
		},
		"duplicate_clusters_top.tsv": {
			"population": "all .pg files under roots",
			"unit": "one row per duplicate cluster (top-N only, per hash type)",
			"notes": "sha256 clusters are exact duplicates; sha256_ws clusters remove ASCII whitespace before hashing; representative_file is workspace-relative when available",
			"sorted": "group_size desc, then representative_file asc, then hash asc",
		},
		"discipline_counts.tsv": {
			"population": "all .pg files under roots (DBsubject lines only)",
			"unit": "each DBsubject line contributes 1 to exactly one discipline",
			"notes": "counts are DBsubject-line counts (not file counts); only lines starting with '## DBsubject(' are considered",
			"sorted": "discipline order is fixed",
		},
		"discipline_subject_counts.tsv": {
			"population": "all .pg files under roots (DBsubject lines only)",
			"unit": "each DBsubject line contributes 1 to (discipline, subject_raw, subject_norm)",
			"notes": "subject_raw is quotes-stripped and trimmed; subject_norm is lowercased and whitespace-collapsed (with minimal typo fixups); top subjects per discipline only",
			"sorted": "discipline order is fixed; within discipline count desc, then subject asc",
		},
		"discipline_coverage.tsv": {
			"population": "all .pg files under roots",
			"unit": "file and line coverage metrics for DBsubject/DBchapter/DBsection",
			"notes": "multi-subject files contribute multiple DBsubject lines; blanks are counted after quote-stripping and trimming; changed_by_normalization counts raw != normalized",
			"sorted": "row order is fixed; do not sort",
		},
		"discipline_unclassified_subject_counts.tsv": {
			"population": "DBsubject lines bucketed as other",
			"unit": "each DBsubject line contributes 1 to (subject_raw, subject_norm)",
			"notes": "top unclassified subjects to drive taxonomy tuning; subject_raw preserves case/spacing and subject_norm is normalized",
			"sorted": "count desc, then subject asc",
		},
		"discipline_samples.tsv": {
			"population": "files with a primary discipline bucket",
			"unit": "one row per sampled file (per bucket)",
			"notes": "deterministic first-N samples in traversal order; primary_subject is the first non-blank DBsubject string",
			"sorted": "discipline order is fixed; within discipline traversal order",
		},
		"chem_terms_count.tsv": {
			"population": "content-hint audit (not used for classification)",
			"unit": "one row per matched file (capped)",
			"notes": "first hit per file, capped overall; helps audit chemistry-like terms without classifying by content",
			"sorted": "traversal order (capped)",
		},
		"bio_terms_count.tsv": {
			"population": "content-hint audit (not used for classification)",
			"unit": "one row per matched file (capped)",
			"notes": "first hit per file, capped overall; helps audit biology-like terms without classifying by content",
			"sorted": "traversal order (capped)",
		},
		"coverage.tsv": {
			"unit": "each file contributes to exactly one bucket",
			"notes": "widgets=some means any widget detected; eval=ans_only/pgml_only/both/none based on evaluator source",
		},
		"evaluator_source_counts.tsv": {
			"unit": "each evaluator occurrence contributes to its source",
			"notes": "sources are ans_call, pgml_payload, and pgml_star_spec",
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
			"notes": "includes evaluators from ANS(...) and PGML blank specs ({...} and *{...})",
		},
		"pgml_payload_evaluator_counts.tsv": {
			"unit": "each detected PGML-payload evaluator occurrence contributes 1",
			"notes": "only evaluators extracted from PGML blank payloads",
		},
		"pgml_star_spec_evaluator_counts.tsv": {
			"unit": "each detected PGML-star-spec evaluator occurrence contributes 1",
			"notes": "only evaluators extracted from PGML blank '*{...}' specs",
		},
		"subtype_tag_counts.tsv": {
			"unit": "each file contributes 1 to each subtype tag it matches",
			"notes": "multi-label expansion; subtype tags are a lightweight secondary taxonomy",
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
_MATCHLIST_TOKEN_RX = re.compile(r"\bMatchList\s*\(")


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
