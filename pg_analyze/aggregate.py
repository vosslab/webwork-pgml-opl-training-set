# Standard Library
import heapq


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


def _render_counts_tsv(rows: list[tuple[str, int]], *, key_name: str) -> str:
	lines: list[str] = [f"{key_name}\tcount"]
	for key, count in sorted(rows, key=lambda x: (-x[1], x[0])):
		lines.append(f"{key}\t{count}")
	return "\n".join(lines) + "\n"


#============================================

OUTPUT_PATHS: dict[str, str] = {
	# summary/
	"counts_by_type.tsv": "summary/type_counts_all_files.tsv",
	"confidence_bins.tsv": "summary/confidence_bins.tsv",
	"coverage.tsv": "summary/coverage_widgets_vs_evaluator_source.tsv",
	"evaluator_source_counts.tsv": "summary/evaluator_source_counts_all_files.tsv",

	# counts/
	"macro_counts.tsv": "counts/macro_load_counts_all_files.tsv",
	"widget_counts.tsv": "counts/widget_kind_counts_all_files.tsv",
	"evaluator_counts.tsv": "counts/evaluator_kind_counts_all_files.tsv",
	"pgml_payload_evaluator_counts.tsv": "counts/evaluator_kind_counts_pgml_payload_only.tsv",

	# cross_tabs/
	"type_by_widget.tsv": "cross_tabs/type_x_widget_kind_counts.tsv",
	"type_by_evaluator.tsv": "cross_tabs/type_x_evaluator_kind_counts.tsv",
	"type_by_evaluator_source.tsv": "cross_tabs/type_x_evaluator_source_counts.tsv",
	"widget_by_evaluator.tsv": "cross_tabs/widget_kind_x_evaluator_kind_counts.tsv",

	# histograms/
	"input_count_hist.tsv": "histograms/input_count_hist.tsv",
	"ans_count_hist.tsv": "histograms/ans_count_hist.tsv",
	"ans_token_hist.tsv": "histograms/ans_token_hist.tsv",
	"pgml_blank_marker_hist.tsv": "histograms/pgml_blank_marker_hist.tsv",
	"other_pgml_blank_hist.tsv": "histograms/other_pgml_blank_hist.tsv",

	# needs_review/
	"needs_review.tsv": "needs_review/needs_review_samples_topN.tsv",
	"needs_review_bucket_counts.tsv": "needs_review/needs_review_bucket_counts.tsv",
	"needs_review_type_counts.tsv": "needs_review/needs_review_type_counts.tsv",
	"needs_review_macro_counts.tsv": "needs_review/needs_review_macro_counts.tsv",
	"evaluator_coverage_reasons.tsv": "needs_review/evaluator_missing_reasons_counts.tsv",

	# macros/
	"macro_counts_other.tsv": "macros/macro_counts_other.tsv",
	"macro_counts_unknown_pgml_blank.tsv": "macros/macro_counts_unknown_pgml_blank.tsv",
	"macro_counts_eval_none_numeric_entry.tsv": "macros/macro_counts_eval_none_numeric_entry.tsv",
	"macro_counts_eval_none_multiple_choice.tsv": "macros/macro_counts_eval_none_multiple_choice.tsv",

	# other/
	"other_breakdown.tsv": "other/other_breakdown.tsv",
	"widget_counts_other.tsv": "other/widget_counts_other.tsv",
	"evaluator_counts_other.tsv": "other/evaluator_counts_other.tsv",

	# samples/
	"unknown_pgml_blank_signature_counts.tsv": "samples/unknown_pgml_blank_signature_counts.tsv",
	"unknown_pgml_blank_signature_samples.tsv": "samples/unknown_pgml_blank_signature_samples.tsv",
	"other_signature_counts.tsv": "samples/other_signature_counts.tsv",
	"other_signature_samples.tsv": "samples/other_signature_samples.tsv",
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
		self.type_counts: dict[str, int] = {}
		self.confidence_bins: dict[str, int] = {}
		self.macro_counts: dict[str, int] = {}
		self.widget_counts: dict[str, int] = {}
		self.evaluator_counts: dict[str, int] = {}
		self.input_hist: dict[str, int] = {}
		self.ans_hist: dict[str, int] = {}
		self.pgml_blank_hist: dict[str, int] = {}
		self.other_pgml_blank_hist: dict[str, int] = {}

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

		if isinstance(ans_count, int):
			_inc(self.ans_hist, count_bucket(ans_count))

		if isinstance(pgml_blank_marker_count, int):
			_inc(self.pgml_blank_hist, count_bucket(pgml_blank_marker_count))

		if isinstance(ans_token_count, int):
			_inc(self.ans_token_hist, count_bucket(ans_token_count))

		self._add_evaluator_sources(record)
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

		for t in type_set:
			for w in widget_set:
				self.type_by_widget[(t, w)] = self.type_by_widget.get((t, w), 0) + 1
			for e in eval_set:
				self.type_by_evaluator[(t, e)] = self.type_by_evaluator.get((t, e), 0) + 1

		for w in widget_set:
			for e in eval_set:
				self.widget_by_evaluator[(w, e)] = self.widget_by_evaluator.get((w, e), 0) + 1

		self._add_coverage(record, has_widgets=has_widgets)

	def _add_coverage(self, record: dict, *, has_widgets: bool) -> None:
		ans_call_count = int(record.get("ans_call_evaluator_count", 0) or 0)
		pgml_payload_count = int(record.get("pgml_payload_evaluator_count", 0) or 0)

		if ans_call_count > 0 and pgml_payload_count > 0:
			eval_bucket = "both"
		elif ans_call_count > 0:
			eval_bucket = "ans_only"
		elif pgml_payload_count > 0:
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

		types = record.get("types", [])
		if not isinstance(types, list) or not types:
			types = ["other"]

		ans_call_count = int(record.get("ans_call_evaluator_count", 0) or 0)
		pgml_payload_count = int(record.get("pgml_payload_evaluator_count", 0) or 0)

		sources: list[str] = []
		if ans_call_count > 0:
			sources.append("ans_call")
		if pgml_payload_count > 0:
			sources.append("pgml_payload")
		if not sources:
			sources = ["none"]

		type_set = sorted({t for t in types if isinstance(t, str) and t})
		for t in type_set:
			for s in sources:
				self.type_by_evaluator_source[(t, s)] = self.type_by_evaluator_source.get((t, s), 0) + 1

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
		out["counts_by_type.tsv"] = _render_counts_tsv(list(self.type_counts.items()), key_name="type")
		out["confidence_bins.tsv"] = _render_counts_tsv(list(self.confidence_bins.items()), key_name="bin")
		out["macro_counts.tsv"] = _render_counts_tsv(list(self.macro_counts.items()), key_name="macro")
		out["widget_counts.tsv"] = _render_counts_tsv(list(self.widget_counts.items()), key_name="widget_kind")
		out["evaluator_counts.tsv"] = _render_counts_tsv(list(self.evaluator_counts.items()), key_name="evaluator_kind")
		out["input_count_hist.tsv"] = _render_counts_tsv(list(self.input_hist.items()), key_name="bucket")
		out["ans_count_hist.tsv"] = _render_counts_tsv(list(self.ans_hist.items()), key_name="bucket")
		out["pgml_blank_marker_hist.tsv"] = _render_counts_tsv(list(self.pgml_blank_hist.items()), key_name="bucket")
		out["ans_token_hist.tsv"] = _render_counts_tsv(list(self.ans_token_hist.items()), key_name="bucket")
		out["evaluator_coverage_reasons.tsv"] = _render_counts_tsv(list(self.evaluator_coverage_reasons.items()), key_name="reason")
		out["evaluator_source_counts.tsv"] = _render_counts_tsv(list(self.evaluator_source_counts.items()), key_name="source")
		out["pgml_payload_evaluator_counts.tsv"] = _render_counts_tsv(list(self.pgml_payload_evaluator_counts.items()), key_name="evaluator_kind")
		out["type_by_evaluator_source.tsv"] = self._render_pair_counts_tsv(self.type_by_evaluator_source, left="type", right="evaluator_source")
		out["needs_review.tsv"] = self._render_needs_review_tsv()
		out["needs_review_bucket_counts.tsv"] = _render_counts_tsv(list(self.needs_review_bucket_counts.items()), key_name="bucket")
		out["needs_review_type_counts.tsv"] = _render_counts_tsv(list(self.needs_review_type_counts.items()), key_name="type")
		out["needs_review_macro_counts.tsv"] = _render_counts_tsv(list(self.needs_review_macro_counts.items()), key_name="macro")
		out["macro_counts_unknown_pgml_blank.tsv"] = _render_counts_tsv(list(self.macro_counts_unknown_pgml_blank.items()), key_name="macro")
		out["macro_counts_eval_none_numeric_entry.tsv"] = _render_counts_tsv(list(self.macro_counts_eval_none_numeric_entry.items()), key_name="macro")
		out["macro_counts_eval_none_multiple_choice.tsv"] = _render_counts_tsv(list(self.macro_counts_eval_none_multiple_choice.items()), key_name="macro")
		out["other_breakdown.tsv"] = _render_counts_tsv(list(self.other_breakdown.items()), key_name="bucket")
		out["macro_counts_other.tsv"] = _render_counts_tsv(list(self.macro_counts_other.items()), key_name="macro")
		out["widget_counts_other.tsv"] = _render_counts_tsv(list(self.widget_counts_other.items()), key_name="widget_kind")
		out["evaluator_counts_other.tsv"] = _render_counts_tsv(list(self.evaluator_counts_other.items()), key_name="evaluator_kind")
		out["other_pgml_blank_hist.tsv"] = _render_counts_tsv(list(self.other_pgml_blank_hist.items()), key_name="bucket")
		out["type_by_widget.tsv"] = self._render_pair_counts_tsv(self.type_by_widget, left="type", right="widget_kind")
		out["type_by_evaluator.tsv"] = self._render_pair_counts_tsv(self.type_by_evaluator, left="type", right="evaluator_kind")
		out["widget_by_evaluator.tsv"] = self._render_pair_counts_tsv(self.widget_by_evaluator, left="widget_kind", right="evaluator_kind")
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
		return out

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
	has_payload = int(record.get("pgml_payload_evaluator_count", 0) or 0) > 0
	has_named_ans_rule = int(record.get("has_named_ans_rule_token", 0) or 0) > 0
	has_ans_rule = int(record.get("has_ans_rule_token", 0) or 0) > 0
	has_named_popup = int(record.get("has_named_popup_list_token", 0) or 0) > 0
	has_cmp = int(record.get("has_cmp_token", 0) or 0) > 0
	has_ctor = int(record.get("has_answer_ctor", 0) or 0) > 0
	has_ans_call = int(record.get("has_ans_token", 0) or 0) > 0

	if pgml_blank_markers <= 0:
		return "no_pgml_blank_markers"

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
