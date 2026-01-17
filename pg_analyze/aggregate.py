# Standard Library
import heapq
import os

# Local modules
import pg_analyze.discipline


#============================================


def confidence_bin(confidence: float) -> str:
	if confidence < 0.0:
		confidence = 0.0
	if confidence > 1.0:
		confidence = 1.0
	i = int(confidence * 10.0)
	if i >= 10:
		i = 9
	lo = i / 10.0
	hi = (i + 1) / 10.0
	return f"{lo:.1f}-{hi:.1f}"


#============================================


def count_bucket(count: int) -> str:
	if count <= 0:
		return "0"
	if count == 1:
		return "1"
	if count == 2:
		return "2"
	if count == 3:
		return "3"
	if count == 4:
		return "4"
	if count <= 9:
		return "5-9"
	if count <= 19:
		return "10-19"
	return "20+"


#============================================

def _bucket_percentile(hist: dict[str, int], *, percentile: float) -> str:
	"""
	Return a bucket label at a percentile based on a binned histogram.

	This reports the first bucket where cumulative count >= percentile.
	"""
	order = ["0", "1", "2", "3", "4", "5-9", "10-19", "20+"]
	total = sum(int(v) for v in hist.values() if isinstance(v, int))
	if total <= 0:
		return ""
	target = max(1, int(total * percentile))
	cum = 0
	for b in order:
		cum += int(hist.get(b, 0) or 0)
		if cum >= target:
			return b
	return order[-1]


def _duplicate_stats(counts: dict[str, int]) -> dict[str, int]:
	unique = len(counts)
	dup_groups = 0
	dup_files = 0
	max_group = 0
	for c in counts.values():
		if c <= 1:
			continue
		dup_groups += 1
		dup_files += c
		if c > max_group:
			max_group = c
	return {
		"unique": unique,
		"dup_groups": dup_groups,
		"dup_files": dup_files,
		"max_group": max_group,
	}

def _duplicate_group_size_hist(counts: dict[str, int]) -> dict[str, int]:
	"""
	Return a histogram over duplicate group sizes (groups only, not files).
	"""
	hist: dict[str, int] = {}
	for c in counts.values():
		if c <= 1:
			continue
		_inc(hist, count_bucket(int(c)))
	return hist


#============================================


def reasons_to_text(reasons: list[dict]) -> str:
	parts: list[str] = []
	for r in reasons:
		if not isinstance(r, dict):
			continue
		kind = r.get("kind")
		value = r.get("value")
		if not isinstance(kind, str) or not isinstance(value, str):
			continue
		parts.append(f"{kind}:{value}")
	return "; ".join(parts)


#============================================


def _inc(counter: dict[str, int], key: str, amount: int = 1) -> None:
	counter[key] = counter.get(key, 0) + amount


#============================================

def _path_prefix(path: str, *, depth: int) -> str:
	if not isinstance(path, str) or not path:
		return ""
	p = path.replace(os.sep, "/")
	parts = [x for x in p.split("/") if x and x != "."]
	if not parts:
		return ""
	return "/".join(parts[: max(1, depth)])


#============================================


def _render_counts_tsv(rows: list[tuple[str, int]], *, key_name: str) -> str:
	lines: list[str] = [f"{key_name}\tcount"]
	for key, count in sorted(rows, key=lambda x: (-x[1], x[0])):
		lines.append(f"{key}\t{count}")
	return "\n".join(lines) + "\n"


def _render_long_counts_tsv(rows: list[tuple[str, str, str, int]]) -> str:
	"""
	Render a long-format counts table.

	Rows are (group, scope, key, count).
	"""
	lines: list[str] = ["group\tscope\tkey\tcount"]
	rows_sorted = sorted(rows, key=lambda x: (x[0], x[1], -x[3], x[2]))
	for group, scope, key, count in rows_sorted:
		lines.append(f"{group}\t{scope}\t{key}\t{count}")
	return "\n".join(lines) + "\n"


def _render_long_cross_tabs_tsv(rows: list[tuple[str, str, str, str, int]]) -> str:
	"""
	Render a long-format cross-tab table.

	Rows are (row_dim, col_dim, row, col, count).
	"""
	lines: list[str] = ["row_dim\tcol_dim\trow\tcol\tcount"]
	rows_sorted = sorted(rows, key=lambda x: (x[0], x[1], -x[4], x[2], x[3]))
	for row_dim, col_dim, row, col, count in rows_sorted:
		lines.append(f"{row_dim}\t{col_dim}\t{row}\t{col}\t{count}")
	return "\n".join(lines) + "\n"


def _render_long_histograms_tsv(rows: list[tuple[str, str, int]]) -> str:
	"""
	Render a long-format histogram table.

	Rows are (histogram, bin, count).
	"""
	lines: list[str] = ["histogram\tbin\tcount"]
	rows_sorted = sorted(rows, key=lambda x: (x[0], -x[2], x[1]))
	for hist_name, bin_name, count in rows_sorted:
		lines.append(f"{hist_name}\t{bin_name}\t{count}")
	return "\n".join(lines) + "\n"


#============================================

OUTPUT_PATHS: dict[str, str] = {
	# summary/
	"counts_all.tsv": "summary/counts_all.tsv",
	"cross_tabs_all.tsv": "summary/cross_tabs_all.tsv",
	"corpus_profile.tsv": "summary/corpus_profile.tsv",
	"histograms_all.tsv": "summary/histograms_all.tsv",
	"macro_counts_segmented.tsv": "summary/macro_counts_segmented.tsv",
	"coverage.tsv": "summary/coverage_widgets_vs_evaluator_source.tsv",
	"discipline_counts.tsv": "summary/discipline_counts.tsv",
	"discipline_subject_counts.tsv": "summary/discipline_subject_counts.tsv",
	"discipline_coverage.tsv": "summary/discipline_coverage.tsv",
	"discipline_unclassified_subject_counts.tsv": "summary/discipline_unclassified_subject_counts.tsv",
	"discipline_samples.tsv": "summary/discipline_samples.tsv",
	"chem_terms_count.tsv": "content_hints/chem_terms_count.tsv",
	"bio_terms_count.tsv": "content_hints/bio_terms_count.tsv",

	# needs_review/
	"needs_review.tsv": "needs_review/needs_review_samples_topN.tsv",
	"needs_review_bucket_counts.tsv": "needs_review/needs_review_bucket_counts.tsv",
	"needs_review_type_counts.tsv": "needs_review/needs_review_type_counts.tsv",
	"needs_review_macro_counts.tsv": "needs_review/needs_review_macro_counts.tsv",
	"evaluator_coverage_reasons.tsv": "needs_review/evaluator_missing_reasons_counts.tsv",

	# other/
	"other_breakdown.tsv": "other/other_breakdown.tsv",
	"widget_counts_other.tsv": "other/widget_counts_other.tsv",
	"evaluator_counts_other.tsv": "other/evaluator_counts_other.tsv",

	# samples/
	"unknown_pgml_blank_signature_counts.tsv": "samples/unknown_pgml_blank_signature_counts.tsv",
	"unknown_pgml_blank_signature_samples.tsv": "samples/unknown_pgml_blank_signature_samples.tsv",
	"other_signature_counts.tsv": "samples/other_signature_counts.tsv",
	"other_signature_samples.tsv": "samples/other_signature_samples.tsv",
	"duplicate_clusters_top.tsv": "summary/duplicate_clusters_top.tsv",
}

_STRONG_WIDGET_MACRO_SUBSTRINGS = (
	"parserradiobuttons",
	"parserpopup",
	"parsercheckbox",
	"parsermatching",
	"parserassignment",
)


def needs_review_bucket(record: dict) -> str:
	"""
	Return a single actionable bucket label for needs_review triage.

	Return "" when no special bucket applies.
	"""
	load_macros = record.get("loadMacros", [])
	widget_kinds = record.get("widget_kinds", [])
	evaluator_kinds = record.get("evaluator_kinds", [])
	input_count = int(record.get("input_count", 0) or 0)
	ans_count = int(record.get("ans_count", 0) or 0)
	types = record.get("types", [])
	wiring_empty = bool(record.get("wiring_empty", False))

	has_widgets = input_count > 0 or (isinstance(widget_kinds, list) and bool(widget_kinds))
	has_evaluators = ans_count > 0 or (isinstance(evaluator_kinds, list) and bool(evaluator_kinds))

	if (not has_widgets) and (not has_evaluators) and input_count == 0 and ans_count == 0:
		return "coverage_no_signals"

	if isinstance(evaluator_kinds, list) and ("custom" in evaluator_kinds):
		return "custom_checker"

	if isinstance(types, list) and ("multipart" in types):
		if wiring_empty or (not has_evaluators) or input_count == 0:
			return "multipart_unclear"

	if _has_strong_widget_macro(load_macros) and (not has_widgets):
		return "macro_only_widget_missing"

	if has_widgets and (not has_evaluators):
		return "widget_no_evaluator"

	if has_evaluators and (not has_widgets):
		return "evaluator_no_widget"

	return ""


def _has_strong_widget_macro(load_macros: list[str]) -> bool:
	if not isinstance(load_macros, list):
		return False
	for m in load_macros:
		if not isinstance(m, str):
			continue
		low = m.lower()
		for s in _STRONG_WIDGET_MACRO_SUBSTRINGS:
			if s in low:
				return True
	return False


#============================================


class Aggregator:
	def __init__(self, *, needs_review_limit: int = 200, out_dir: str | None = None):
		self.total_files = 0
		self.matchlist_files = 0

		self.files_with_dbsubject = 0
		self.files_with_dbsubject_nonblank = 0
		self.dbsubject_lines_total = 0
		self.dbsubject_lines_blank = 0
		self.dbsubject_lines_changed_by_normalization = 0
		self.dbsubject_raw_distinct: set[str] = set()
		self.dbsubject_norm_distinct: set[str] = set()

		self.files_with_dbchapter = 0
		self.files_with_dbchapter_nonblank = 0
		self.dbchapter_lines_total = 0
		self.dbchapter_lines_blank = 0
		self.dbchapter_lines_changed_by_normalization = 0
		self.dbchapter_raw_distinct: set[str] = set()
		self.dbchapter_norm_distinct: set[str] = set()

		self.files_with_dbsection = 0
		self.files_with_dbsection_nonblank = 0
		self.dbsection_lines_total = 0
		self.dbsection_lines_blank = 0
		self.dbsection_lines_changed_by_normalization = 0
		self.dbsection_raw_distinct: set[str] = set()
		self.dbsection_norm_distinct: set[str] = set()

		self.discipline_line_counts: dict[str, int] = {d: 0 for d in pg_analyze.discipline.DISCIPLINES}
		self.discipline_subject_counts: dict[tuple[str, str, str], int] = {}
		self.discipline_primary_subject_counts: dict[tuple[str, str], int] = {}
		self.discipline_sample_files: dict[str, list[tuple[str, str]]] = {}
		self._chem_hint_rows: list[tuple[str, int, str, str]] = []
		self._bio_hint_rows: list[tuple[str, int, str, str]] = []
		self._chem_hint_cap = 200
		self._bio_hint_cap = 200
		self.chem_files_with_hit = 0
		self.bio_files_with_hit = 0
		self.chem_term_counts: dict[str, int] = {}
		self.bio_term_counts: dict[str, int] = {}
		self.chem_prefix_counts: dict[str, int] = {}
		self.bio_prefix_counts: dict[str, int] = {}

		self.type_counts: dict[str, int] = {}
		self.confidence_bins: dict[str, int] = {}
		self.macro_counts: dict[str, int] = {}
		self.widget_counts: dict[str, int] = {}
		self.widget_file_counts: dict[str, int] = {}
		self.evaluator_counts: dict[str, int] = {}
		self.input_hist: dict[str, int] = {}
		self.multipart_input_hist: dict[str, int] = {}
		self.ans_hist: dict[str, int] = {}
		self.pgml_blank_hist: dict[str, int] = {}
		self.other_pgml_blank_hist: dict[str, int] = {}
		self.type_by_eval_coverage: dict[tuple[str, str], int] = {}

		self.path_top_counts: dict[str, int] = {}
		self.files_with_resources = 0
		self.resource_ext_counts: dict[str, int] = {}
		self.files_with_randomization = 0
		self.asset_signal_file_counts: dict[str, int] = {}

		self._sha256_counts: dict[str, int] = {}
		self._sha256_ws_counts: dict[str, int] = {}
		self._sha256_example: dict[str, str] = {}
		self._sha256_ws_example: dict[str, str] = {}

		self.other_breakdown: dict[str, int] = {}
		self.macro_counts_other: dict[str, int] = {}
		self.widget_counts_other: dict[str, int] = {}
		self.evaluator_counts_other: dict[str, int] = {}

		self.type_by_widget: dict[tuple[str, str], int] = {}
		self.type_by_evaluator: dict[tuple[str, str], int] = {}
		self.widget_by_evaluator: dict[tuple[str, str], int] = {}
		self.coverage: dict[str, int] = {
			"widgets=none,eval=none": 0,
			"widgets=none,eval=ans_only": 0,
			"widgets=none,eval=pgml_only": 0,
			"widgets=none,eval=both": 0,
			"widgets=some,eval=none": 0,
			"widgets=some,eval=ans_only": 0,
			"widgets=some,eval=pgml_only": 0,
			"widgets=some,eval=both": 0,
		}

		self.needs_review_bucket_counts: dict[str, int] = {}
		self.needs_review_type_counts: dict[str, int] = {}
		self.needs_review_macro_counts: dict[str, int] = {}

		self.evaluator_coverage_reasons: dict[str, int] = {}
		self.ans_token_hist: dict[str, int] = {}

		self.evaluator_source_counts: dict[str, int] = {}
		self.pgml_payload_evaluator_counts: dict[str, int] = {}
		self.pgml_star_spec_evaluator_counts: dict[str, int] = {}
		self.subtype_tag_counts: dict[str, int] = {}
		self.type_by_evaluator_source: dict[tuple[str, str], int] = {}

		self.macro_counts_unknown_pgml_blank: dict[str, int] = {}
		self.macro_counts_eval_none_numeric_entry: dict[str, int] = {}
		self.macro_counts_eval_none_multiple_choice: dict[str, int] = {}

		self.unknown_signature_counts: dict[str, int] = {}
		self.other_signature_counts: dict[str, int] = {}
		self._unknown_signature_files: dict[str, list[str]] = {}
		self._other_signature_files: dict[str, list[str]] = {}
		self._unknown_file_info: dict[str, dict] = {}
		self._other_file_info: dict[str, dict] = {}

		self._needs_review_total_limit = needs_review_limit
		self._needs_review_per_bucket_limit = 40
		self._needs_review_by_bucket: dict[str, list[tuple[float, str, float, str, str, int, int, int, int, str, str, str, int, str]]] = {}

		self._other_low_conf_heap: list[tuple[float, str, float, str, str]] = []
		self._other_high_blank_heap: list[tuple[int, str, float, str, str]] = []
		self._other_applet_heap: list[tuple[float, str, float, str, str]] = []
		self._bucket_writers = BucketWriters(out_dir) if isinstance(out_dir, str) and out_dir else None

	def add_record(self, record: dict) -> None:
		self.total_files += 1
		if int(record.get("has_matchlist_token", 0) or 0) > 0:
			self.matchlist_files += 1

		self._add_discipline(record)
		self._add_path_provenance(record)
		self._add_resources(record)
		self._add_randomization(record)
		self._add_duplicates(record)
		self._add_asset_signals(record)
		self._add_content_hint_summaries(record)

		types = record.get("types", [])
		confidence = record.get("confidence", 0.0)
		load_macros = record.get("loadMacros", [])
		widget_kinds = record.get("widget_kinds", [])
		evaluator_kinds = record.get("evaluator_kinds", [])
		input_count = record.get("input_count", 0)
		ans_count = record.get("ans_count", 0)
		needs_review = record.get("needs_review", False)
		pgml_blank_marker_count = record.get("pgml_blank_marker_count", 0)
		ans_token_count = int(record.get("ans_token_count", 0) or 0)

		if isinstance(types, list):
			for t in types:
				if isinstance(t, str):
					_inc(self.type_counts, t)

		if isinstance(confidence, float) or isinstance(confidence, int):
			_inc(self.confidence_bins, confidence_bin(float(confidence)))

		if isinstance(load_macros, list):
			for macro in load_macros:
				if isinstance(macro, str):
					_inc(self.macro_counts, macro)

		self._add_widget_file_counts(record)
		if isinstance(widget_kinds, list):
			for kind in widget_kinds:
				if isinstance(kind, str):
					_inc(self.widget_counts, kind)

		if isinstance(evaluator_kinds, list):
			for kind in evaluator_kinds:
				if isinstance(kind, str):
					_inc(self.evaluator_counts, kind)

		if isinstance(input_count, int):
			_inc(self.input_hist, count_bucket(input_count))

		if isinstance(types, list) and ("multipart" in types) and isinstance(input_count, int):
			_inc(self.multipart_input_hist, count_bucket(input_count))

		if isinstance(ans_count, int):
			_inc(self.ans_hist, count_bucket(ans_count))

		if isinstance(pgml_blank_marker_count, int):
			_inc(self.pgml_blank_hist, count_bucket(pgml_blank_marker_count))

		if isinstance(ans_token_count, int):
			_inc(self.ans_token_hist, count_bucket(ans_token_count))

		self._add_evaluator_sources(record)
		self._add_subtypes(record)
		self._add_eval_coverage(record)
		self._add_subset_macro_counts(record)
		self._add_signatures(record)

		is_other = isinstance(types, list) and ("other" in types)
		if is_other:
			self._add_other(record)

		self._add_cross_tabs(record)

		if self._bucket_writers is not None:
			self._bucket_writers.write_record(record)

		if needs_review:
			self._add_needs_review(record)

	def close(self) -> None:
		if self._bucket_writers is not None:
			self._bucket_writers.close()

	def _add_cross_tabs(self, record: dict) -> None:
		types = record.get("types", [])
		widgets = record.get("widget_kinds", [])
		evals = record.get("evaluator_kinds", [])

		if not isinstance(types, list) or not types:
			types = ["other"]
		if not isinstance(widgets, list) or not widgets:
			widgets = ["none"]
		if not isinstance(evals, list) or not evals:
			evals = ["none"]

		type_set = sorted({t for t in types if isinstance(t, str) and t})
		widget_set = sorted({w for w in widgets if isinstance(w, str) and w})
		eval_set = sorted({e for e in evals if isinstance(e, str) and e})

		if not type_set:
			type_set = ["other"]
		if not widget_set:
			widget_set = ["none"]
		if not eval_set:
			eval_set = ["none"]

		has_widgets = not (len(widget_set) == 1 and widget_set[0] == "none")
		eval_cov = self._eval_coverage_bucket(record)

		for t in type_set:
			for w in widget_set:
				self.type_by_widget[(t, w)] = self.type_by_widget.get((t, w), 0) + 1
			for e in eval_set:
				self.type_by_evaluator[(t, e)] = self.type_by_evaluator.get((t, e), 0) + 1
			self.type_by_eval_coverage[(t, eval_cov)] = self.type_by_eval_coverage.get((t, eval_cov), 0) + 1

		for w in widget_set:
			for e in eval_set:
				self.widget_by_evaluator[(w, e)] = self.widget_by_evaluator.get((w, e), 0) + 1

		self._add_coverage(record, has_widgets=has_widgets)

	def _add_widget_file_counts(self, record: dict) -> None:
		widgets = record.get("widget_kinds", [])
		if not isinstance(widgets, list) or not widgets:
			_inc(self.widget_file_counts, "none")
			return
		kind_set = {w for w in widgets if isinstance(w, str) and w}
		if not kind_set:
			_inc(self.widget_file_counts, "none")
			return
		for k in sorted(kind_set):
			_inc(self.widget_file_counts, k)

	def _eval_coverage_bucket(self, record: dict) -> str:
		ans_call_count = int(record.get("ans_call_evaluator_count", 0) or 0)
		pgml_payload_count = int(record.get("pgml_payload_evaluator_count", 0) or 0)
		pgml_star_spec_count = int(record.get("pgml_star_spec_evaluator_count", 0) or 0)
		pgml_count = pgml_payload_count + pgml_star_spec_count

		if ans_call_count > 0 and pgml_count > 0:
			return "both"
		if ans_call_count > 0:
			return "ans_only"
		if pgml_count > 0:
			return "pgml_only"
		return "none"

	def _add_coverage(self, record: dict, *, has_widgets: bool) -> None:
		ans_call_count = int(record.get("ans_call_evaluator_count", 0) or 0)
		pgml_payload_count = int(record.get("pgml_payload_evaluator_count", 0) or 0)
		pgml_star_spec_count = int(record.get("pgml_star_spec_evaluator_count", 0) or 0)
		pgml_count = pgml_payload_count + pgml_star_spec_count

		if ans_call_count > 0 and pgml_count > 0:
			eval_bucket = "both"
		elif ans_call_count > 0:
			eval_bucket = "ans_only"
		elif pgml_count > 0:
			eval_bucket = "pgml_only"
		else:
			eval_bucket = "none"

		widget_bucket = "some" if has_widgets else "none"
		_inc(self.coverage, f"widgets={widget_bucket},eval={eval_bucket}")

	def _add_evaluator_sources(self, record: dict) -> None:
		evaluator_sources = record.get("evaluator_sources", [])
		if isinstance(evaluator_sources, list):
			for s in evaluator_sources:
				if isinstance(s, str) and s:
					_inc(self.evaluator_source_counts, s)

		pgml_kinds = record.get("pgml_payload_evaluator_kinds", [])
		if isinstance(pgml_kinds, list):
			for k in pgml_kinds:
				if isinstance(k, str) and k:
					_inc(self.pgml_payload_evaluator_counts, k)

		star_kinds = record.get("pgml_star_spec_evaluator_kinds", [])
		if isinstance(star_kinds, list):
			for k in star_kinds:
				if isinstance(k, str) and k:
					_inc(self.pgml_star_spec_evaluator_counts, k)

		types = record.get("types", [])
		if not isinstance(types, list) or not types:
			types = ["other"]

		ans_call_count = int(record.get("ans_call_evaluator_count", 0) or 0)
		pgml_payload_count = int(record.get("pgml_payload_evaluator_count", 0) or 0)
		pgml_star_spec_count = int(record.get("pgml_star_spec_evaluator_count", 0) or 0)

		sources: list[str] = []
		if ans_call_count > 0:
			sources.append("ans_call")
		if pgml_payload_count > 0:
			sources.append("pgml_payload")
		if pgml_star_spec_count > 0:
			sources.append("pgml_star_spec")
		if not sources:
			sources = ["none"]

		type_set = sorted({t for t in types if isinstance(t, str) and t})
		for t in type_set:
			for s in sources:
				self.type_by_evaluator_source[(t, s)] = self.type_by_evaluator_source.get((t, s), 0) + 1

	def _add_subtypes(self, record: dict) -> None:
		subtypes = record.get("subtype_tags", [])
		if not isinstance(subtypes, list):
			return
		for t in subtypes:
			if isinstance(t, str) and t:
				_inc(self.subtype_tag_counts, t)

	def _add_other(self, record: dict) -> None:
		bucket = other_bucket(record)
		_inc(self.other_breakdown, bucket)

		load_macros = record.get("loadMacros", [])
		if isinstance(load_macros, list):
			for macro in load_macros:
				if isinstance(macro, str):
					_inc(self.macro_counts_other, macro)

		widget_kinds = record.get("widget_kinds", [])
		if isinstance(widget_kinds, list):
			for kind in widget_kinds:
				if isinstance(kind, str):
					_inc(self.widget_counts_other, kind)

		evaluator_kinds = record.get("evaluator_kinds", [])
		if isinstance(evaluator_kinds, list):
			for kind in evaluator_kinds:
				if isinstance(kind, str):
					_inc(self.evaluator_counts_other, kind)

		pgml_blank_marker_count = record.get("pgml_blank_marker_count", 0)
		if isinstance(pgml_blank_marker_count, int):
			_inc(self.other_pgml_blank_hist, count_bucket(pgml_blank_marker_count))

		self._sample_other(record, bucket)

	def _sample_other(self, record: dict, bucket: str) -> None:
		file_path = record.get("file", "")
		confidence = float(record.get("confidence", 0.0))
		macros_top3 = ",".join(_macros_top3(record.get("loadMacros", [])))

		if not isinstance(file_path, str):
			return

		heapq.heappush(self._other_low_conf_heap, (-confidence, file_path, confidence, bucket, macros_top3))
		if len(self._other_low_conf_heap) > 20:
			heapq.heappop(self._other_low_conf_heap)

		blank_count = int(record.get("pgml_blank_marker_count", 0) or 0)
		heapq.heappush(self._other_high_blank_heap, (blank_count, file_path, confidence, bucket, macros_top3))
		if len(self._other_high_blank_heap) > 20:
			heapq.heappop(self._other_high_blank_heap)

		if bucket == "other_applet_like":
			heapq.heappush(self._other_applet_heap, (-confidence, file_path, confidence, bucket, macros_top3))
			if len(self._other_applet_heap) > 20:
				heapq.heappop(self._other_applet_heap)

	def _add_needs_review(self, record: dict) -> None:
		file_path = record.get("file", "")
		confidence = float(record.get("confidence", 0.0))
		types = record.get("types", [])
		reasons = record.get("reasons", [])
		load_macros = record.get("loadMacros", [])
		widget_kinds = record.get("widget_kinds", [])
		evaluator_kinds = record.get("evaluator_kinds", [])
		input_count = int(record.get("input_count", 0) or 0)
		ans_count = int(record.get("ans_count", 0) or 0)
		pgml_blank_markers = int(record.get("pgml_blank_marker_count", 0) or 0)

		if not isinstance(file_path, str):
			return

		bucket = record.get("needs_review_bucket", "")
		if not isinstance(bucket, str) or not bucket:
			bucket = needs_review_bucket(record) or "low_confidence_misc"

		_inc(self.needs_review_bucket_counts, bucket)

		if isinstance(types, list):
			for t in types:
				if isinstance(t, str) and t:
					_inc(self.needs_review_type_counts, t)

		if isinstance(load_macros, list):
			for macro in load_macros:
				if isinstance(macro, str) and macro:
					_inc(self.needs_review_macro_counts, macro)

		types_text = ",".join(t for t in types if isinstance(t, str))
		reasons_text = reasons_to_text(reasons if isinstance(reasons, list) else [])

		has_widgets = 1 if (input_count > 0 or (isinstance(widget_kinds, list) and bool(widget_kinds))) else 0
		has_evaluators = 1 if (ans_count > 0 or (isinstance(evaluator_kinds, list) and bool(evaluator_kinds))) else 0

		widget_kinds_text = ",".join(sorted({w for w in widget_kinds if isinstance(w, str) and w})) if isinstance(widget_kinds, list) else ""
		evaluator_kinds_text = ",".join(sorted({e for e in evaluator_kinds if isinstance(e, str) and e})) if isinstance(evaluator_kinds, list) else ""
		macros_top3 = ",".join(_macros_top3(load_macros if isinstance(load_macros, list) else []))

		heap = self._needs_review_by_bucket.setdefault(bucket, [])
		heapq.heappush(
			heap,
			(
				-confidence,
				file_path,
				confidence,
				bucket,
				types_text,
				has_widgets,
				has_evaluators,
				input_count,
				ans_count,
				widget_kinds_text,
				evaluator_kinds_text,
				macros_top3,
				pgml_blank_markers,
				reasons_text,
			),
		)
		if len(heap) > self._needs_review_per_bucket_limit:
			heapq.heappop(heap)

	def render_reports(self) -> dict[str, str]:
		out: dict[str, str] = {}
		out["counts_all.tsv"] = self._render_counts_all_tsv()
		out["cross_tabs_all.tsv"] = self._render_cross_tabs_all_tsv()
		out["corpus_profile.tsv"] = self._render_corpus_profile_tsv()
		out["histograms_all.tsv"] = self._render_histograms_all_tsv()
		out["macro_counts_segmented.tsv"] = self._render_macro_counts_segmented_tsv()
		out["duplicate_clusters_top.tsv"] = self._render_duplicate_clusters_top_tsv(top_n=25)
		out["discipline_counts.tsv"] = self._render_discipline_counts_tsv()
		out["discipline_subject_counts.tsv"] = self._render_discipline_subject_counts_tsv(top_n=50)
		out["discipline_unclassified_subject_counts.tsv"] = self._render_discipline_unclassified_subject_counts_tsv(top_n=50)
		out["discipline_samples.tsv"] = self._render_discipline_samples_tsv(per_bucket=25)
		out["discipline_coverage.tsv"] = self._render_discipline_coverage_tsv()
		out["chem_terms_count.tsv"] = self._render_content_hints_tsv(self._chem_hint_rows)
		out["bio_terms_count.tsv"] = self._render_content_hints_tsv(self._bio_hint_rows)
		out["needs_review.tsv"] = self._render_needs_review_tsv()
		out["needs_review_bucket_counts.tsv"] = _render_counts_tsv(list(self.needs_review_bucket_counts.items()), key_name="bucket")
		out["needs_review_type_counts.tsv"] = _render_counts_tsv(list(self.needs_review_type_counts.items()), key_name="type")
		out["needs_review_macro_counts.tsv"] = _render_counts_tsv(list(self.needs_review_macro_counts.items()), key_name="macro")
		out["other_breakdown.tsv"] = _render_counts_tsv(list(self.other_breakdown.items()), key_name="bucket")
		out["widget_counts_other.tsv"] = _render_counts_tsv(list(self.widget_counts_other.items()), key_name="widget_kind")
		out["evaluator_counts_other.tsv"] = _render_counts_tsv(list(self.evaluator_counts_other.items()), key_name="evaluator_kind")
		out["coverage.tsv"] = _render_counts_tsv(list(self.coverage.items()), key_name="bucket")
		out["unknown_pgml_blank_signature_counts.tsv"] = self._render_signature_counts_tsv(self.unknown_signature_counts, category="unknown_pgml_blank", top_n=25)
		out["unknown_pgml_blank_signature_samples.tsv"] = self._render_signature_samples_tsv(
			self.unknown_signature_counts,
			self._unknown_signature_files,
			self._unknown_file_info,
			category="unknown_pgml_blank",
			total_cap=2000,
		)
		out["other_signature_counts.tsv"] = self._render_signature_counts_tsv(self.other_signature_counts, category="other", top_n=25)
		out["other_signature_samples.tsv"] = self._render_signature_samples_tsv(
			self.other_signature_counts,
			self._other_signature_files,
			self._other_file_info,
			category="other",
			total_cap=500,
		)
		out["evaluator_coverage_reasons.tsv"] = _render_counts_tsv(list(self.evaluator_coverage_reasons.items()), key_name="reason")
		return out

	def _render_duplicate_clusters_top_tsv(self, *, top_n: int) -> str:
		"""
		Render a small list of the largest duplicate clusters.

		This is intended as a human-scale summary and debugging aid.
		"""
		lines: list[str] = ["hash_type\tgroup_size\thash\trepresentative_file"]

		def _emit(hash_type: str, counts: dict[str, int], examples: dict[str, str]) -> None:
			items: list[tuple[int, str, str]] = []
			for h, c in counts.items():
				if c <= 1:
					continue
				ex = examples.get(h, "")
				items.append((int(c), h, ex))
			items_sorted = sorted(items, key=lambda x: (-x[0], x[2], x[1]))[:top_n]
			for c, h, ex in items_sorted:
				lines.append(f"{hash_type}\t{c}\t{h}\t{ex}")

		_emit("sha256", self._sha256_counts, self._sha256_example)
		_emit("sha256_ws", self._sha256_ws_counts, self._sha256_ws_example)
		return "\n".join(lines) + "\n"

	def _add_discipline(self, record: dict) -> None:
		dbsubject_pairs = record.get("dbsubject_pairs", [])
		if not isinstance(dbsubject_pairs, list):
			dbsubject_pairs = []

		lines_total = int(record.get("dbsubject_lines_total", len(dbsubject_pairs)) or 0)
		lines_blank = int(record.get("dbsubject_lines_blank", 0) or 0)
		has_dbsubject = int(record.get("has_dbsubject", 0) or 0) > 0
		has_dbsubject_nonblank = int(record.get("has_dbsubject_nonblank", 0) or 0) > 0

		if has_dbsubject:
			self.files_with_dbsubject += 1
		if has_dbsubject_nonblank:
			self.files_with_dbsubject_nonblank += 1
		self.dbsubject_lines_total += lines_total
		self.dbsubject_lines_blank += lines_blank

		for item in dbsubject_pairs:
			if not (isinstance(item, tuple) and len(item) == 2):
				continue
			raw, norm = item
			if not isinstance(raw, str) or not isinstance(norm, str):
				continue
			raw2 = raw.strip()
			norm2 = norm.strip()
			self.dbsubject_raw_distinct.add(raw2)
			self.dbsubject_norm_distinct.add(norm2)
			if raw2 != norm2:
				self.dbsubject_lines_changed_by_normalization += 1

			discipline = pg_analyze.discipline.bucket_subject(norm2)
			if discipline not in self.discipline_line_counts:
				discipline = "other"
			self.discipline_line_counts[discipline] += 1
			key = (discipline, raw2, norm2)
			self.discipline_subject_counts[key] = self.discipline_subject_counts.get(key, 0) + 1

		dbchapter_pairs = record.get("dbchapter_pairs", [])
		if not isinstance(dbchapter_pairs, list):
			dbchapter_pairs = []
		dbchapter_total = int(record.get("dbchapter_lines_total", len(dbchapter_pairs)) or 0)
		dbchapter_blank = int(record.get("dbchapter_lines_blank", 0) or 0)
		has_dbchapter = int(record.get("has_dbchapter", 0) or 0) > 0
		has_dbchapter_nonblank = int(record.get("has_dbchapter_nonblank", 0) or 0) > 0
		if has_dbchapter:
			self.files_with_dbchapter += 1
		if has_dbchapter_nonblank:
			self.files_with_dbchapter_nonblank += 1
		self.dbchapter_lines_total += dbchapter_total
		self.dbchapter_lines_blank += dbchapter_blank
		for item in dbchapter_pairs:
			if not (isinstance(item, tuple) and len(item) == 2):
				continue
			raw, norm = item
			if not isinstance(raw, str) or not isinstance(norm, str):
				continue
			raw2 = raw.strip()
			norm2 = norm.strip()
			self.dbchapter_raw_distinct.add(raw2)
			self.dbchapter_norm_distinct.add(norm2)
			if raw2 != norm2:
				self.dbchapter_lines_changed_by_normalization += 1

		dbsection_pairs = record.get("dbsection_pairs", [])
		if not isinstance(dbsection_pairs, list):
			dbsection_pairs = []
		dbsection_total = int(record.get("dbsection_lines_total", len(dbsection_pairs)) or 0)
		dbsection_blank = int(record.get("dbsection_lines_blank", 0) or 0)
		has_dbsection = int(record.get("has_dbsection", 0) or 0) > 0
		has_dbsection_nonblank = int(record.get("has_dbsection_nonblank", 0) or 0) > 0
		if has_dbsection:
			self.files_with_dbsection += 1
		if has_dbsection_nonblank:
			self.files_with_dbsection_nonblank += 1
		self.dbsection_lines_total += dbsection_total
		self.dbsection_lines_blank += dbsection_blank
		for item in dbsection_pairs:
			if not (isinstance(item, tuple) and len(item) == 2):
				continue
			raw, norm = item
			if not isinstance(raw, str) or not isinstance(norm, str):
				continue
			raw2 = raw.strip()
			norm2 = norm.strip()
			self.dbsection_raw_distinct.add(raw2)
			self.dbsection_norm_distinct.add(norm2)
			if raw2 != norm2:
				self.dbsection_lines_changed_by_normalization += 1

		primary = record.get("discipline_primary", "other")
		if not isinstance(primary, str) or not primary:
			primary = "other"
		if primary not in self.discipline_line_counts:
			primary = "other"

		primary_subject = record.get("discipline_primary_subject_raw", "")
		if not isinstance(primary_subject, str):
			primary_subject = ""
		primary_subject = primary_subject.strip()
		primary_key = (primary, primary_subject)
		self.discipline_primary_subject_counts[primary_key] = self.discipline_primary_subject_counts.get(primary_key, 0) + 1

		file_path = record.get("file", "")
		if isinstance(file_path, str) and file_path:
			samples = self.discipline_sample_files.setdefault(primary, [])
			if len(samples) < 25:
				samples.append((file_path, primary_subject))

		self._add_content_hints(record)

	def _add_content_hints(self, record: dict) -> None:
		file_path = record.get("file", "")
		if not isinstance(file_path, str) or not file_path:
			return

		chem = record.get("chem_hint")
		if (
			chem
			and isinstance(chem, tuple)
			and len(chem) == 3
			and len(self._chem_hint_rows) < self._chem_hint_cap
		):
			term, line, snippet = chem
			if isinstance(term, str) and isinstance(line, int) and isinstance(snippet, str):
				self._chem_hint_rows.append((file_path, line, term, snippet))

		bio = record.get("bio_hint")
		if (
			bio
			and isinstance(bio, tuple)
			and len(bio) == 3
			and len(self._bio_hint_rows) < self._bio_hint_cap
		):
			term, line, snippet = bio
			if isinstance(term, str) and isinstance(line, int) and isinstance(snippet, str):
				self._bio_hint_rows.append((file_path, line, term, snippet))

	def _add_path_provenance(self, record: dict) -> None:
		rel = record.get("file_rel", "")
		if not isinstance(rel, str) or not rel:
			return
		rel2 = rel.replace(os.sep, "/")
		parts = [p for p in rel2.split("/") if p and p != "."]
		if not parts:
			return
		_inc(self.path_top_counts, parts[0])

	def _add_resources(self, record: dict) -> None:
		exts = record.get("resource_exts", [])
		if not isinstance(exts, list) or not exts:
			return
		self.files_with_resources += 1
		for ext in sorted({e for e in exts if isinstance(e, str) and e}):
			_inc(self.resource_ext_counts, ext)

	def _add_randomization(self, record: dict) -> None:
		if int(record.get("has_randomization", 0) or 0) > 0:
			self.files_with_randomization += 1

	def _add_duplicates(self, record: dict) -> None:
		file_rel = record.get("file_rel", "")
		if not isinstance(file_rel, str) or not file_rel:
			file_rel = record.get("file", "")
		if not isinstance(file_rel, str):
			file_rel = ""

		h = record.get("sha256")
		if isinstance(h, str) and h:
			self._sha256_counts[h] = self._sha256_counts.get(h, 0) + 1
			if h not in self._sha256_example and file_rel:
				self._sha256_example[h] = file_rel
		h2 = record.get("sha256_ws")
		if isinstance(h2, str) and h2:
			self._sha256_ws_counts[h2] = self._sha256_ws_counts.get(h2, 0) + 1
			if h2 not in self._sha256_ws_example and file_rel:
				self._sha256_ws_example[h2] = file_rel

	def _add_content_hint_summaries(self, record: dict) -> None:
		rel = record.get("file_rel", "")
		prefix = _path_prefix(rel, depth=2)

		chem_terms = record.get("chem_terms_present", [])
		if isinstance(chem_terms, list) and any(isinstance(t, str) and t for t in chem_terms):
			self.chem_files_with_hit += 1
			if prefix:
				_inc(self.chem_prefix_counts, prefix)
			for t in sorted({t for t in chem_terms if isinstance(t, str) and t}):
				_inc(self.chem_term_counts, t)

		bio_terms = record.get("bio_terms_present", [])
		if isinstance(bio_terms, list) and any(isinstance(t, str) and t for t in bio_terms):
			self.bio_files_with_hit += 1
			if prefix:
				_inc(self.bio_prefix_counts, prefix)
			for t in sorted({t for t in bio_terms if isinstance(t, str) and t}):
				_inc(self.bio_term_counts, t)

	def _add_asset_signals(self, record: dict) -> None:
		signals = record.get("asset_signals", [])
		if not isinstance(signals, list) or not signals:
			return
		for s in sorted({x for x in signals if isinstance(x, str) and x}):
			_inc(self.asset_signal_file_counts, s)

	def _render_discipline_counts_tsv(self) -> str:
		lines: list[str] = ["discipline\tcount"]
		for d in pg_analyze.discipline.DISCIPLINES:
			lines.append(f"{d}\t{self.discipline_line_counts.get(d, 0)}")
		return "\n".join(lines) + "\n"

	def _render_discipline_subject_counts_tsv(self, *, top_n: int) -> str:
		lines: list[str] = ["discipline\tsubject_raw\tsubject_norm\tcount"]
		for d in pg_analyze.discipline.DISCIPLINES:
			items = [
				(raw, norm, count)
				for (disc, raw, norm), count in self.discipline_subject_counts.items()
				if disc == d
			]
			items_sorted = sorted(items, key=lambda x: (-x[2], x[0], x[1]))[:top_n]
			for raw, norm, count in items_sorted:
				lines.append(f"{d}\t{raw}\t{norm}\t{count}")
		return "\n".join(lines) + "\n"

	def _render_discipline_unclassified_subject_counts_tsv(self, *, top_n: int) -> str:
		lines: list[str] = ["subject_raw\tsubject_norm\tcount"]
		items = [
			(raw, norm, count)
			for (disc, raw, norm), count in self.discipline_subject_counts.items()
			if disc == "other"
		]
		items_sorted = sorted(items, key=lambda x: (-x[2], x[0], x[1]))[:top_n]
		for raw, norm, count in items_sorted:
			lines.append(f"{raw}\t{norm}\t{count}")
		return "\n".join(lines) + "\n"

	def _render_discipline_samples_tsv(self, *, per_bucket: int) -> str:
		lines: list[str] = ["discipline\tfile\tprimary_subject"]
		for d in pg_analyze.discipline.DISCIPLINES:
			samples = self.discipline_sample_files.get(d, [])
			for file_path, primary_subject in samples[:per_bucket]:
				lines.append(f"{d}\t{file_path}\t{primary_subject}")
		return "\n".join(lines) + "\n"

	def _render_content_hints_tsv(self, rows: list[tuple[str, int, str, str]]) -> str:
		lines: list[str] = ["file\tline\tterm\tsnippet"]
		for file_path, line, term, snippet in rows:
			lines.append(f"{file_path}\t{line}\t{term}\t{snippet}")
		return "\n".join(lines) + "\n"

	def _render_discipline_coverage_tsv(self) -> str:
		files_total = self.total_files
		files_with = self.files_with_dbsubject
		files_without = files_total - files_with
		lines: list[str] = ["metric\tcount"]
		lines.append(f"files_total\t{files_total}")
		lines.append(f"files_with_dbsubject\t{files_with}")
		lines.append(f"files_with_dbsubject_nonblank\t{self.files_with_dbsubject_nonblank}")
		lines.append(f"files_without_dbsubject\t{files_without}")
		lines.append(f"dbsubject_lines_total\t{self.dbsubject_lines_total}")
		lines.append(f"dbsubject_lines_blank\t{self.dbsubject_lines_blank}")
		lines.append(f"dbsubject_lines_changed_by_normalization\t{self.dbsubject_lines_changed_by_normalization}")
		lines.append(f"dbsubject_raw_distinct\t{len(self.dbsubject_raw_distinct)}")
		lines.append(f"dbsubject_norm_distinct\t{len(self.dbsubject_norm_distinct)}")

		lines.append(f"files_with_dbchapter\t{self.files_with_dbchapter}")
		lines.append(f"files_with_dbchapter_nonblank\t{self.files_with_dbchapter_nonblank}")
		lines.append(f"dbchapter_lines_total\t{self.dbchapter_lines_total}")
		lines.append(f"dbchapter_lines_blank\t{self.dbchapter_lines_blank}")
		lines.append(f"dbchapter_lines_changed_by_normalization\t{self.dbchapter_lines_changed_by_normalization}")
		lines.append(f"dbchapter_raw_distinct\t{len(self.dbchapter_raw_distinct)}")
		lines.append(f"dbchapter_norm_distinct\t{len(self.dbchapter_norm_distinct)}")

		lines.append(f"files_with_dbsection\t{self.files_with_dbsection}")
		lines.append(f"files_with_dbsection_nonblank\t{self.files_with_dbsection_nonblank}")
		lines.append(f"dbsection_lines_total\t{self.dbsection_lines_total}")
		lines.append(f"dbsection_lines_blank\t{self.dbsection_lines_blank}")
		lines.append(f"dbsection_lines_changed_by_normalization\t{self.dbsection_lines_changed_by_normalization}")
		lines.append(f"dbsection_raw_distinct\t{len(self.dbsection_raw_distinct)}")
		lines.append(f"dbsection_norm_distinct\t{len(self.dbsection_norm_distinct)}")
		return "\n".join(lines) + "\n"

	def _render_corpus_profile_tsv(self) -> str:
		"""
		Write a small, stable corpus-profile table for quick orientation.
		"""
		key_macros = [
			"MathObjects.pl",
			"PGchoicemacros.pl",
			"PGML.pl",
			"PGgraphmacros.pl",
			"parserPopUp.pl",
			"parserRadioButtons.pl",
			"parserAssignment.pl",
			"parserMatch.pl",
		]

		lines: list[str] = ["metric\tvalue"]
		lines.append(f"total_files\t{self.total_files}")
		lines.append(f"files_with_dbsubject\t{self.files_with_dbsubject}")
		lines.append(f"files_with_dbsubject_nonblank\t{self.files_with_dbsubject_nonblank}")
		lines.append(f"files_with_dbchapter\t{self.files_with_dbchapter}")
		lines.append(f"files_with_dbchapter_nonblank\t{self.files_with_dbchapter_nonblank}")
		lines.append(f"files_with_dbsection\t{self.files_with_dbsection}")
		lines.append(f"files_with_dbsection_nonblank\t{self.files_with_dbsection_nonblank}")

		for macro in key_macros:
			lines.append(f"macro_files:{macro}\t{self.macro_counts.get(macro, 0)}")

		lines.append(f"token_files:MatchList\t{self.matchlist_files}")
		lines.append(f"files_with_resources\t{self.files_with_resources}")
		lines.append(f"files_with_randomization\t{self.files_with_randomization}")

		lines.append(f"input_count_p50_bucket\t{_bucket_percentile(self.input_hist, percentile=0.50)}")
		lines.append(f"input_count_p90_bucket\t{_bucket_percentile(self.input_hist, percentile=0.90)}")
		lines.append(f"input_count_p99_bucket\t{_bucket_percentile(self.input_hist, percentile=0.99)}")

		exact = _duplicate_stats(self._sha256_counts)
		ws = _duplicate_stats(self._sha256_ws_counts)
		lines.append(f"sha256_unique\t{exact['unique']}")
		lines.append(f"sha256_dup_groups\t{exact['dup_groups']}")
		lines.append(f"sha256_dup_files\t{exact['dup_files']}")
		lines.append(f"sha256_max_group\t{exact['max_group']}")
		lines.append(f"sha256_ws_unique\t{ws['unique']}")
		lines.append(f"sha256_ws_dup_groups\t{ws['dup_groups']}")
		lines.append(f"sha256_ws_dup_files\t{ws['dup_files']}")
		lines.append(f"sha256_ws_max_group\t{ws['max_group']}")
		return "\n".join(lines) + "\n"

	def _render_counts_all_tsv(self) -> str:
		rows: list[tuple[str, str, str, int]] = []

		rows.extend([("evaluator_kind", "all", k, v) for k, v in self.evaluator_counts.items()])
		rows.extend([("evaluator_kind", "pgml_payload_only", k, v) for k, v in self.pgml_payload_evaluator_counts.items()])
		rows.extend([("evaluator_kind", "pgml_star_spec_only", k, v) for k, v in self.pgml_star_spec_evaluator_counts.items()])
		rows.extend([("widget_kind", "all", k, v) for k, v in self.widget_counts.items()])
		rows.extend([("widget_kind_file", "all", k, v) for k, v in self.widget_file_counts.items()])
		rows.extend([("macro_load", "all", k, v) for k, v in self.macro_counts.items()])
		rows.extend([("type", "all", k, v) for k, v in self.type_counts.items()])
		rows.extend([("evaluator_source", "all", k, v) for k, v in self.evaluator_source_counts.items()])
		rows.extend([("subtype_tag", "all", k, v) for k, v in self.subtype_tag_counts.items()])
		rows.extend([("path_top", "all", k, v) for k, v in self.path_top_counts.items()])

		rows.extend(
			[
				("db_tag_file", "all", "dbsubject_line", self.files_with_dbsubject),
				("db_tag_file", "all", "dbsubject_nonblank", self.files_with_dbsubject_nonblank),
				("db_tag_file", "all", "dbchapter_line", self.files_with_dbchapter),
				("db_tag_file", "all", "dbchapter_nonblank", self.files_with_dbchapter_nonblank),
				("db_tag_file", "all", "dbsection_line", self.files_with_dbsection),
				("db_tag_file", "all", "dbsection_nonblank", self.files_with_dbsection_nonblank),
				("db_tag_lines", "all", "dbsubject", self.dbsubject_lines_total),
				("db_tag_lines", "all", "dbchapter", self.dbchapter_lines_total),
				("db_tag_lines", "all", "dbsection", self.dbsection_lines_total),
				("db_tag_blank_lines", "all", "dbsubject", self.dbsubject_lines_blank),
				("db_tag_blank_lines", "all", "dbchapter", self.dbchapter_lines_blank),
				("db_tag_blank_lines", "all", "dbsection", self.dbsection_lines_blank),
				("db_tag_distinct_raw", "all", "dbsubject", len(self.dbsubject_raw_distinct)),
				("db_tag_distinct_raw", "all", "dbchapter", len(self.dbchapter_raw_distinct)),
				("db_tag_distinct_raw", "all", "dbsection", len(self.dbsection_raw_distinct)),
				("db_tag_distinct_norm", "all", "dbsubject", len(self.dbsubject_norm_distinct)),
				("db_tag_distinct_norm", "all", "dbchapter", len(self.dbchapter_norm_distinct)),
				("db_tag_distinct_norm", "all", "dbsection", len(self.dbsection_norm_distinct)),
				("db_tag_changed_lines", "all", "dbsubject", self.dbsubject_lines_changed_by_normalization),
				("db_tag_changed_lines", "all", "dbchapter", self.dbchapter_lines_changed_by_normalization),
				("db_tag_changed_lines", "all", "dbsection", self.dbsection_lines_changed_by_normalization),
			]
		)

		rows.append(("resource_file", "all", "has_resources", self.files_with_resources))
		rows.extend([("resource_ext", "all", k, v) for k, v in self.resource_ext_counts.items()])
		rows.append(("randomization_file", "all", "has_randomization", self.files_with_randomization))
		rows.extend([("asset_signal_file", "all", k, v) for k, v in self.asset_signal_file_counts.items()])

		exact = _duplicate_stats(self._sha256_counts)
		ws = _duplicate_stats(self._sha256_ws_counts)
		rows.extend(
			[
				("duplicate", "all", "sha256_unique", exact["unique"]),
				("duplicate", "all", "sha256_dup_groups", exact["dup_groups"]),
				("duplicate", "all", "sha256_dup_files", exact["dup_files"]),
				("duplicate", "all", "sha256_max_group", exact["max_group"]),
				("duplicate", "all", "sha256_ws_unique", ws["unique"]),
				("duplicate", "all", "sha256_ws_dup_groups", ws["dup_groups"]),
				("duplicate", "all", "sha256_ws_dup_files", ws["dup_files"]),
				("duplicate", "all", "sha256_ws_max_group", ws["max_group"]),
			]
		)

		rows.append(("content_hint_files", "chem", "files_with_hit", self.chem_files_with_hit))
		rows.append(("content_hint_files", "bio", "files_with_hit", self.bio_files_with_hit))
		rows.extend([("content_hint_term", "chem", k, v) for k, v in self.chem_term_counts.items()])
		rows.extend([("content_hint_term", "bio", k, v) for k, v in self.bio_term_counts.items()])
		rows.extend([("content_hint_prefix", "chem", k, v) for k, v in self.chem_prefix_counts.items()])
		rows.extend([("content_hint_prefix", "bio", k, v) for k, v in self.bio_prefix_counts.items()])

		return _render_long_counts_tsv(rows)

	def _render_cross_tabs_all_tsv(self) -> str:
		rows: list[tuple[str, str, str, str, int]] = []
		rows.extend([("type", "widget_kind", a, b, c) for (a, b), c in self.type_by_widget.items()])
		rows.extend([("type", "evaluator_kind", a, b, c) for (a, b), c in self.type_by_evaluator.items()])
		rows.extend([("type", "evaluator_source", a, b, c) for (a, b), c in self.type_by_evaluator_source.items()])
		rows.extend([("type", "evaluator_coverage", a, b, c) for (a, b), c in self.type_by_eval_coverage.items()])
		rows.extend([("widget_kind", "evaluator_kind", a, b, c) for (a, b), c in self.widget_by_evaluator.items()])
		return _render_long_cross_tabs_tsv(rows)

	def _render_histograms_all_tsv(self) -> str:
		rows: list[tuple[str, str, int]] = []
		rows.extend([("input_count", k, v) for k, v in self.input_hist.items()])
		rows.extend([("input_count_multipart", k, v) for k, v in self.multipart_input_hist.items()])
		rows.extend([("ans_count", k, v) for k, v in self.ans_hist.items()])
		rows.extend([("pgml_blank_marker_count", k, v) for k, v in self.pgml_blank_hist.items()])
		rows.extend([("ans_token_count", k, v) for k, v in self.ans_token_hist.items()])
		rows.extend([("confidence_bin", k, v) for k, v in self.confidence_bins.items()])
		rows.extend([("other_pgml_blank_marker_count", k, v) for k, v in self.other_pgml_blank_hist.items()])

		sha_hist = _duplicate_group_size_hist(self._sha256_counts)
		rows.extend([("sha256_dup_group_size", k, v) for k, v in sha_hist.items()])
		sha_ws_hist = _duplicate_group_size_hist(self._sha256_ws_counts)
		rows.extend([("sha256_ws_dup_group_size", k, v) for k, v in sha_ws_hist.items()])

		return _render_long_histograms_tsv(rows)

	def _render_macro_counts_segmented_tsv(self) -> str:
		lines: list[str] = ["segment\tmacro\tcount"]
		rows: list[tuple[str, str, int]] = []
		rows.extend([("all", m, c) for m, c in self.macro_counts.items()])
		rows.extend([("unknown_pgml_blank", m, c) for m, c in self.macro_counts_unknown_pgml_blank.items()])
		rows.extend([("eval_none_numeric_entry", m, c) for m, c in self.macro_counts_eval_none_numeric_entry.items()])
		rows.extend([("eval_none_multiple_choice", m, c) for m, c in self.macro_counts_eval_none_multiple_choice.items()])
		rows.extend([("other", m, c) for m, c in self.macro_counts_other.items()])

		rows_sorted = sorted(rows, key=lambda x: (x[0], -x[2], x[1]))
		for segment, macro, count in rows_sorted:
			lines.append(f"{segment}\t{macro}\t{count}")
		return "\n".join(lines) + "\n"

	def _render_signature_counts_tsv(self, counts: dict[str, int], *, category: str, top_n: int) -> str:
		total = sum(counts.values())
		items = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:top_n]
		lines: list[str] = ["signature\tcount\tpct_of_category"]
		for sig, count in items:
			pct = (count / total * 100.0) if total else 0.0
			lines.append(f"{sig}\t{count}\t{pct:.2f}")
		return "\n".join(lines) + "\n"

	def _render_signature_samples_tsv(
		self,
		counts: dict[str, int],
		sig_to_files: dict[str, list[str]],
		file_info: dict[str, dict],
		*,
		category: str,
		total_cap: int,
	) -> str:
		lines: list[str] = [
			"signature\tfile\ttop_macros\tpgml_blank_marker_count\thas_payload\tevaluator_sources\tevaluator_kinds\tconfidence"
		]

		signatures = [s for s, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:25]]
		total_written = 0

		for sig in signatures:
			if total_written >= total_cap:
				break
			files = sorted(sig_to_files.get(sig, []))
			if not files:
				continue
			picks = _even_spaced_picks(files, limit=50)
			for file_path in picks:
				if total_written >= total_cap:
					break
				info = file_info.get(file_path, {})
				top_macros = info.get("top_macros", "")
				pgml_blank_marker_count = int(info.get("pgml_blank_marker_count", 0) or 0)
				has_payload = int(info.get("has_payload", 0) or 0)
				evaluator_sources = info.get("evaluator_sources", "none")
				evaluator_kinds = info.get("evaluator_kinds", "none")
				confidence = float(info.get("confidence", 0.0))
				lines.append(
					f"{sig}\t{file_path}\t{top_macros}\t{pgml_blank_marker_count}\t{has_payload}\t{evaluator_sources}\t{evaluator_kinds}\t{confidence:.2f}"
				)
				total_written += 1

		return "\n".join(lines) + "\n"

	def _add_eval_coverage(self, record: dict) -> None:
		evaluator_kinds = record.get("evaluator_kinds", [])
		if isinstance(evaluator_kinds, list) and evaluator_kinds:
			return

		pgml_blank_markers = int(record.get("pgml_blank_marker_count", 0) or 0)
		has_ans_token = int(record.get("has_ans_token", 0) or 0)
		has_cmp_token = int(record.get("has_cmp_token", 0) or 0)
		has_answer_ctor = int(record.get("has_answer_ctor", 0) or 0)
		has_named_ans_rule_token = int(record.get("has_named_ans_rule_token", 0) or 0)
		has_named_ans_token = int(record.get("has_named_ans_token", 0) or 0)
		has_ans_num_to_name = int(record.get("has_ans_num_to_name", 0) or 0)
		has_install_problem_grader = int(record.get("has_install_problem_grader", 0) or 0)

		if pgml_blank_markers > 0:
			_inc(self.evaluator_coverage_reasons, "none_pgml_blank_only")
			return
		if has_cmp_token:
			_inc(self.evaluator_coverage_reasons, "none_but_cmp_present")
			return
		if has_ans_token:
			_inc(self.evaluator_coverage_reasons, "none_but_ans_present_unparsed")
			return
		if has_named_ans_rule_token or has_named_ans_token:
			_inc(self.evaluator_coverage_reasons, "none_but_named_ans_present")
			return
		if has_ans_num_to_name:
			_inc(self.evaluator_coverage_reasons, "none_but_ans_num_to_name_present")
			return
		if has_install_problem_grader:
			_inc(self.evaluator_coverage_reasons, "none_but_custom_grader_present")
			return
		if has_answer_ctor:
			_inc(self.evaluator_coverage_reasons, "none_but_answer_ctor_present")
			return
		_inc(self.evaluator_coverage_reasons, "none_true_no_signals")

	def _add_subset_macro_counts(self, record: dict) -> None:
		file_types = record.get("types", [])
		load_macros = record.get("loadMacros", [])
		evaluator_kinds = record.get("evaluator_kinds", [])

		if not isinstance(file_types, list):
			return
		if not isinstance(load_macros, list):
			return

		has_evaluators = bool(isinstance(evaluator_kinds, list) and evaluator_kinds)

		if "unknown_pgml_blank" in file_types:
			for macro in load_macros:
				if isinstance(macro, str) and macro:
					_inc(self.macro_counts_unknown_pgml_blank, macro)

		if (not has_evaluators) and ("numeric_entry" in file_types):
			for macro in load_macros:
				if isinstance(macro, str) and macro:
					_inc(self.macro_counts_eval_none_numeric_entry, macro)

		if (not has_evaluators) and ("multiple_choice" in file_types):
			for macro in load_macros:
				if isinstance(macro, str) and macro:
					_inc(self.macro_counts_eval_none_multiple_choice, macro)

	def _add_signatures(self, record: dict) -> None:
		file_path = record.get("file", "")
		if not isinstance(file_path, str) or not file_path:
			return

		types = record.get("types", [])
		if not isinstance(types, list):
			return

		load_macros = record.get("loadMacros", [])
		macros_top3 = ",".join(_macros_top3(load_macros if isinstance(load_macros, list) else []))
		pgml_blank_markers = int(record.get("pgml_blank_marker_count", 0) or 0)
		has_payload = 1 if int(record.get("pgml_payload_evaluator_count", 0) or 0) > 0 else 0
		confidence = float(record.get("confidence", 0.0))

		evaluator_sources = record.get("evaluator_sources", [])
		if isinstance(evaluator_sources, list) and evaluator_sources:
			src_set = sorted({s for s in evaluator_sources if isinstance(s, str) and s})
			evaluator_sources_text = ",".join(src_set)
		else:
			evaluator_sources_text = "none"

		evaluator_kinds = record.get("evaluator_kinds", [])
		if isinstance(evaluator_kinds, list) and evaluator_kinds:
			kind_set = sorted({k for k in evaluator_kinds if isinstance(k, str) and k})
			evaluator_kinds_text = ",".join(kind_set)
		else:
			evaluator_kinds_text = "none"

		info = {
			"file": file_path,
			"top_macros": macros_top3,
			"pgml_blank_marker_count": pgml_blank_markers,
			"has_payload": has_payload,
			"evaluator_sources": evaluator_sources_text,
			"evaluator_kinds": evaluator_kinds_text,
			"confidence": confidence,
		}

		if "unknown_pgml_blank" in types:
			sig = unknown_pgml_blank_signature(record)
			_inc(self.unknown_signature_counts, sig)
			self._unknown_signature_files.setdefault(sig, []).append(file_path)
			self._unknown_file_info[file_path] = info

		if "other" in types:
			sig = other_signature(record)
			_inc(self.other_signature_counts, sig)
			self._other_signature_files.setdefault(sig, []).append(file_path)
			self._other_file_info[file_path] = info

	def top_unknown_signatures(self, *, limit: int = 10) -> list[str]:
		items = sorted(self.unknown_signature_counts.items(), key=lambda x: (-x[1], x[0]))
		return [s for s, _ in items[:limit]]

	def files_for_unknown_signatures(self, signatures: list[str]) -> list[tuple[str, str]]:
		rows: list[tuple[str, str]] = []
		for sig in signatures:
			files = sorted(self._unknown_signature_files.get(sig, []))
			for f in files:
				rows.append((sig, f))
		return rows

	def _render_needs_review_tsv(self) -> str:
		lines: list[str] = [
			"file\tconfidence\tbucket\ttypes\thas_widgets\thas_evaluators\tinput_count\tans_count\twidget_kinds\tevaluator_kinds\ttop_macros\tpgml_blank_markers\treasons"
		]

		bucket_lists: dict[str, list[tuple[float, str, float, str, str, int, int, int, int, str, str, str, int, str]]] = {}
		for bucket, heap in self._needs_review_by_bucket.items():
			items = [(-neg_conf, file_path, conf, b, types_text, hw, he, ic, ac, wk, ek, macros, pgml, reasons) for neg_conf, file_path, conf, b, types_text, hw, he, ic, ac, wk, ek, macros, pgml, reasons in heap]
			items_sorted = sorted(items, key=lambda x: (x[0], x[1]))
			bucket_lists[bucket] = items_sorted

		buckets_sorted = sorted(bucket_lists.keys())
		rows: list[tuple[float, str, float, str, str, int, int, int, int, str, str, str, int, str]] = []
		i = 0
		while len(rows) < self._needs_review_total_limit:
			any_added = False
			for bucket in buckets_sorted:
				items = bucket_lists.get(bucket, [])
				if i < len(items):
					rows.append(items[i])
					any_added = True
					if len(rows) >= self._needs_review_total_limit:
						break
			if not any_added:
				break
			i += 1

		for conf, file_path, _conf2, bucket, types_text, has_widgets, has_evaluators, input_count, ans_count, widget_kinds, evaluator_kinds, macros_top3, pgml_blank_markers, reasons_text in rows:
			lines.append(
				f"{file_path}\t{conf:.2f}\t{bucket}\t{types_text}\t{has_widgets}\t{has_evaluators}\t{input_count}\t{ans_count}\t{widget_kinds}\t{evaluator_kinds}\t{macros_top3}\t{pgml_blank_markers}\t{reasons_text}"
			)
		return "\n".join(lines) + "\n"

	def _render_other_samples_tsv(self) -> str:
		seen: set[str] = set()
		rows: list[tuple[float, str, str, str]] = []

		low_conf = sorted([(-neg, file_path, bucket, macros) for neg, file_path, _, bucket, macros in self._other_low_conf_heap], key=lambda x: (x[0], x[1]))
		high_blank = sorted([(blank, file_path, bucket, macros, conf) for blank, file_path, conf, bucket, macros in self._other_high_blank_heap], key=lambda x: (-x[0], x[1]))
		applet = sorted([(-neg, file_path, bucket, macros) for neg, file_path, _, bucket, macros in self._other_applet_heap], key=lambda x: (x[0], x[1]))

		for conf, file_path, bucket, macros in low_conf:
			if file_path in seen:
				continue
			seen.add(file_path)
			rows.append((conf, file_path, bucket, macros))
			if len(rows) >= 50:
				break

		if len(rows) < 50:
			for blank, file_path, bucket, macros, conf in high_blank:
				if file_path in seen:
					continue
				seen.add(file_path)
				rows.append((conf, file_path, bucket, macros))
				if len(rows) >= 50:
					break

		if len(rows) < 50:
			for conf, file_path, bucket, macros in applet:
				if file_path in seen:
					continue
				seen.add(file_path)
				rows.append((conf, file_path, bucket, macros))
				if len(rows) >= 50:
					break

		lines: list[str] = ["file\tconfidence\tmacros_top3\tother_bucket"]
		for conf, file_path, bucket, macros in rows:
			lines.append(f"{file_path}\t{conf:.2f}\t{macros}\t{bucket}")
		return "\n".join(lines) + "\n"

	def _render_pair_counts_tsv(self, counter: dict[tuple[str, str], int], *, left: str, right: str) -> str:
		lines: list[str] = [f"{left}\t{right}\tcount"]
		rows = [((a, b), c) for (a, b), c in counter.items()]
		rows_sorted = sorted(rows, key=lambda x: (-x[1], x[0][0], x[0][1]))
		for (a, b), c in rows_sorted:
			lines.append(f"{a}\t{b}\t{c}")
		return "\n".join(lines) + "\n"


#============================================


def _macros_top3(load_macros: list[str]) -> list[str]:
	top: list[str] = []
	for m in load_macros:
		if not isinstance(m, str):
			continue
		if m in top:
			continue
		top.append(m)
		if len(top) >= 3:
			break
	return top


#============================================


def other_bucket(record: dict) -> str:
	"""
	Return a single bucket label for a record already labeled "other".
	"""
	load_macros = record.get("loadMacros", [])
	widget_kinds = record.get("widget_kinds", [])
	evaluator_kinds = record.get("evaluator_kinds", [])
	input_count = int(record.get("input_count", 0) or 0)
	ans_count = int(record.get("ans_count", 0) or 0)
	pgml_block_count = int(record.get("pgml_block_count", 0) or 0)
	pgml_blank_marker_count = int(record.get("pgml_blank_marker_count", 0) or 0)

	if _is_applet_like(load_macros):
		return "other_applet_like"
	if _is_graph_like(load_macros):
		return "other_graph_like"
	if isinstance(evaluator_kinds, list) and ("custom" in evaluator_kinds):
		return "other_custom_evaluator"
	if ans_count > 0 and input_count == 0:
		return "other_widgetless_ans"
	if isinstance(evaluator_kinds, list) and ("cmp" in evaluator_kinds) and input_count == 0:
		return "other_cmp_only"
	if pgml_block_count > 0 and pgml_blank_marker_count == 0:
		return "other_pgml_present_no_detected_blanks"
	if ans_count == 0 and input_count == 0 and (not widget_kinds) and (not evaluator_kinds):
		return "other_no_signals"
	return "other_uncategorized"


#============================================


def _is_applet_like(load_macros: list[str]) -> bool:
	if not isinstance(load_macros, list):
		return False
	for m in load_macros:
		if not isinstance(m, str):
			continue
		low = m.lower()
		if "applet" in low or "geogebra" in low or "wwapplet" in low:
			return True
	return False


#============================================


def _is_graph_like(load_macros: list[str]) -> bool:
	if not isinstance(load_macros, list):
		return False
	for m in load_macros:
		if not isinstance(m, str):
			continue
		low = m.lower()
		if "pggraphmacros" in low or "graph" in low:
			return True
	return False


#============================================


def unknown_pgml_blank_signature(record: dict) -> str:
	pgml_blank_markers = int(record.get("pgml_blank_marker_count", 0) or 0)
	has_payload = (int(record.get("pgml_payload_evaluator_count", 0) or 0) > 0) or (int(record.get("pgml_star_spec_evaluator_count", 0) or 0) > 0)
	has_star_spec = int(record.get("pgml_star_spec_evaluator_count", 0) or 0) > 0
	has_named_ans_rule = int(record.get("has_named_ans_rule_token", 0) or 0) > 0
	has_ans_rule = int(record.get("has_ans_rule_token", 0) or 0) > 0
	has_named_popup = int(record.get("has_named_popup_list_token", 0) or 0) > 0
	has_cmp = int(record.get("has_cmp_token", 0) or 0) > 0
	has_ctor = int(record.get("has_answer_ctor", 0) or 0) > 0
	has_ans_call = int(record.get("has_ans_token", 0) or 0) > 0

	if pgml_blank_markers <= 0:
		return "no_pgml_blank_markers"

	if has_star_spec:
		if int(record.get("pgml_payload_evaluator_count", 0) or 0) <= 0:
			return "pgml_blank_star_spec_only"
		return "pgml_blank_star_spec_present"

	if (not has_payload) and has_named_ans_rule:
		return "pgml_blank_no_payload_named_ans_rule"
	if (not has_payload) and has_ans_rule:
		return "pgml_blank_no_payload_ans_rule"
	if (not has_payload) and has_named_popup:
		return "pgml_blank_no_payload_named_popup"
	if has_payload and has_ctor and (not has_cmp):
		return "pgml_blank_payload_has_ctor_no_cmp"
	if has_payload and has_cmp:
		return "pgml_blank_payload_has_cmp"
	if has_ans_call:
		return "pgml_blank_ans_call_present_but_untyped"
	return "pgml_blank_no_grading_signals"


def other_signature(record: dict) -> str:
	load_macros = record.get("loadMacros", [])
	if not isinstance(load_macros, list):
		load_macros = []
	macros = {m for m in load_macros if isinstance(m, str)}

	evaluator_kinds = record.get("evaluator_kinds", [])
	has_evals = bool(isinstance(evaluator_kinds, list) and evaluator_kinds)
	widget_kinds = record.get("widget_kinds", [])
	has_widgets = bool(isinstance(widget_kinds, list) and widget_kinds)
	custom = (isinstance(evaluator_kinds, list) and ("custom" in evaluator_kinds)) or (int(record.get("has_install_problem_grader", 0) or 0) > 0)

	if "PGgraphmacros.pl" in macros or "PCCgraphMacros.pl" in macros:
		return "graph_like_pggraphmacros"
	if "PGessaymacros.pl" in macros:
		return "essay_like_pgessaymacros"
	if "PGchoicemacros.pl" in macros:
		return "choice_like_pgchoicemacros"
	if custom:
		return "custom_grader"
	if (not has_widgets) and has_evals:
		return "no_widgets_has_evaluator"
	if (not has_widgets) and (not has_evals):
		return "no_signals"
	return "misc_other"


#============================================


def _even_spaced_picks(items: list[str], *, limit: int) -> list[str]:
	if limit <= 0 or not items:
		return []
	if len(items) <= limit:
		return items

	step = len(items) / float(limit)
	out: list[str] = []
	seen: set[int] = set()
	for i in range(limit):
		idx = int(i * step)
		if idx in seen:
			continue
		seen.add(idx)
		out.append(items[idx])
	return out


#============================================


class BucketWriters:
	"""
	Write curated, category-level file lists for sampling/grepping.

	Each list is a single text file containing one path per line.
	"""

	def __init__(self, out_dir: str):
		import os

		self._base = os.path.join(out_dir, "lists")
		self._handles: dict[tuple[str, str], object] = {}
		self._ensure_dirs()

	def _ensure_dirs(self) -> None:
		import os
		os.makedirs(os.path.join(self._base, "type"), exist_ok=True)
		os.makedirs(os.path.join(self._base, "subtype"), exist_ok=True)
		os.makedirs(os.path.join(self._base, "discipline"), exist_ok=True)
		os.makedirs(os.path.join(self._base, "widget"), exist_ok=True)
		os.makedirs(os.path.join(self._base, "evaluator"), exist_ok=True)

	def _get_handle(self, category: str, name: str):
		import os
		key = (category, name)
		h = self._handles.get(key)
		if h is not None:
			return h
		path = os.path.join(self._base, category, f"{name}_files.txt")
		h = open(path, "w", encoding="utf-8")
		self._handles[key] = h
		return h

	def write_record(self, record: dict) -> None:
		file_path = record.get("file", "")
		if not isinstance(file_path, str) or not file_path:
			return

		types = record.get("types", [])
		if not isinstance(types, list) or not types:
			types = ["other"]

		widgets = record.get("widget_kinds", [])
		if not isinstance(widgets, list) or not widgets:
			widgets = ["none"]

		evals = record.get("evaluator_kinds", [])
		if not isinstance(evals, list) or not evals:
			evals = ["none"]

		for t in sorted({x for x in types if isinstance(x, str) and x}):
			self._get_handle("type", t).write(file_path + "\n")

		subtypes = record.get("subtype_tags", [])
		if isinstance(subtypes, list) and subtypes:
			for st in sorted({x for x in subtypes if isinstance(x, str) and x}):
				self._get_handle("subtype", st).write(file_path + "\n")

		discipline = record.get("discipline_primary", "other")
		if not isinstance(discipline, str) or not discipline:
			discipline = "other"
		self._get_handle("discipline", discipline).write(file_path + "\n")

		for w in sorted({x for x in widgets if isinstance(x, str) and x}):
			self._get_handle("widget", w).write(file_path + "\n")

		for e in sorted({x for x in evals if isinstance(x, str) and x}):
			self._get_handle("evaluator", e).write(file_path + "\n")

	def close(self) -> None:
		for h in self._handles.values():
			try:
				h.close()
			except Exception:
				pass
		self._handles.clear()
