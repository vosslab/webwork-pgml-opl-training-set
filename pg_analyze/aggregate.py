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
			"widgets=none,evaluators=none": 0,
			"widgets=none,evaluators=some": 0,
			"widgets=some,evaluators=none": 0,
			"widgets=some,evaluators=some": 0,
		}

		self.needs_review_bucket_counts: dict[str, int] = {}
		self.needs_review_type_counts: dict[str, int] = {}
		self.needs_review_macro_counts: dict[str, int] = {}

		self.evaluator_coverage_reasons: dict[str, int] = {}
		self.ans_token_hist: dict[str, int] = {}

		self.macro_counts_unknown_pgml_blank: dict[str, int] = {}
		self.macro_counts_eval_none_numeric_entry: dict[str, int] = {}
		self.macro_counts_eval_none_multiple_choice: dict[str, int] = {}

		self._samples_unknown_pgml_blank: list[tuple[str, int, int, int, str, float]] = []
		self._samples_eval_none_numeric_entry: list[tuple[str, int, int, int, str, float]] = []

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

		self._add_eval_coverage(record)
		self._add_subset_macro_counts(record)
		self._add_subset_samples(record)

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
		has_evals = not (len(eval_set) == 1 and eval_set[0] == "none")

		for t in type_set:
			for w in widget_set:
				self.type_by_widget[(t, w)] = self.type_by_widget.get((t, w), 0) + 1
			for e in eval_set:
				self.type_by_evaluator[(t, e)] = self.type_by_evaluator.get((t, e), 0) + 1

		for w in widget_set:
			for e in eval_set:
				self.widget_by_evaluator[(w, e)] = self.widget_by_evaluator.get((w, e), 0) + 1

		if has_widgets and has_evals:
			_inc(self.coverage, "widgets=some,evaluators=some")
		elif has_widgets and (not has_evals):
			_inc(self.coverage, "widgets=some,evaluators=none")
		elif (not has_widgets) and has_evals:
			_inc(self.coverage, "widgets=none,evaluators=some")
		else:
			_inc(self.coverage, "widgets=none,evaluators=none")

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
		out["needs_review.tsv"] = self._render_needs_review_tsv()
		out["needs_review_bucket_counts.tsv"] = _render_counts_tsv(list(self.needs_review_bucket_counts.items()), key_name="bucket")
		out["needs_review_type_counts.tsv"] = _render_counts_tsv(list(self.needs_review_type_counts.items()), key_name="type")
		out["needs_review_macro_counts.tsv"] = _render_counts_tsv(list(self.needs_review_macro_counts.items()), key_name="macro")
		out["macro_counts_unknown_pgml_blank.tsv"] = _render_counts_tsv(list(self.macro_counts_unknown_pgml_blank.items()), key_name="macro")
		out["macro_counts_eval_none_numeric_entry.tsv"] = _render_counts_tsv(list(self.macro_counts_eval_none_numeric_entry.items()), key_name="macro")
		out["macro_counts_eval_none_multiple_choice.tsv"] = _render_counts_tsv(list(self.macro_counts_eval_none_multiple_choice.items()), key_name="macro")
		out["samples_unknown_pgml_blank.tsv"] = self._render_samples_tsv(self._samples_unknown_pgml_blank)
		out["samples_eval_none_numeric_entry.tsv"] = self._render_samples_tsv(self._samples_eval_none_numeric_entry)
		out["other_breakdown.tsv"] = _render_counts_tsv(list(self.other_breakdown.items()), key_name="bucket")
		out["macro_counts_other.tsv"] = _render_counts_tsv(list(self.macro_counts_other.items()), key_name="macro")
		out["widget_counts_other.tsv"] = _render_counts_tsv(list(self.widget_counts_other.items()), key_name="widget_kind")
		out["evaluator_counts_other.tsv"] = _render_counts_tsv(list(self.evaluator_counts_other.items()), key_name="evaluator_kind")
		out["other_pgml_blank_hist.tsv"] = _render_counts_tsv(list(self.other_pgml_blank_hist.items()), key_name="bucket")
		out["other_samples.tsv"] = self._render_other_samples_tsv()
		out["type_by_widget.tsv"] = self._render_pair_counts_tsv(self.type_by_widget, left="type", right="widget_kind")
		out["type_by_evaluator.tsv"] = self._render_pair_counts_tsv(self.type_by_evaluator, left="type", right="evaluator_kind")
		out["widget_by_evaluator.tsv"] = self._render_pair_counts_tsv(self.widget_by_evaluator, left="widget_kind", right="evaluator_kind")
		out["coverage.tsv"] = _render_counts_tsv(list(self.coverage.items()), key_name="bucket")
		return out

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

	def _add_subset_samples(self, record: dict) -> None:
		file_path = record.get("file", "")
		if not isinstance(file_path, str) or not file_path:
			return

		file_types = record.get("types", [])
		if not isinstance(file_types, list):
			return

		evaluator_kinds = record.get("evaluator_kinds", [])
		has_evaluators = bool(isinstance(evaluator_kinds, list) and evaluator_kinds)

		pgml_blank_markers = int(record.get("pgml_blank_marker_count", 0) or 0)
		has_ans_token = int(record.get("has_ans_token", 0) or 0)
		has_cmp_token = int(record.get("has_cmp_token", 0) or 0)
		macros_top3 = ",".join(_macros_top3(record.get("loadMacros", [])))
		confidence = float(record.get("confidence", 0.0))

		row = (file_path, pgml_blank_markers, has_ans_token, has_cmp_token, macros_top3, confidence)

		if ("unknown_pgml_blank" in file_types) and (len(self._samples_unknown_pgml_blank) < 50):
			self._samples_unknown_pgml_blank.append(row)

		if (not has_evaluators) and ("numeric_entry" in file_types) and (len(self._samples_eval_none_numeric_entry) < 50):
			self._samples_eval_none_numeric_entry.append(row)

	def _render_samples_tsv(self, rows: list[tuple[str, int, int, int, str, float]]) -> str:
		lines: list[str] = ["file\tpgml_blank_markers\thas_ans_call\thas_cmp_token\ttop_macros\tconfidence"]
		for file_path, pgml_blank_markers, has_ans_token, has_cmp_token, macros_top3, confidence in rows:
			lines.append(f"{file_path}\t{pgml_blank_markers}\t{has_ans_token}\t{has_cmp_token}\t{macros_top3}\t{confidence:.2f}")
		return "\n".join(lines) + "\n"

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


class BucketWriters:
	"""
	Write curated, category-level file lists for sampling/grepping.

	Each list is a single text file containing one path per line.
	"""

	def __init__(self, out_dir: str):
		self._base = out_dir
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
