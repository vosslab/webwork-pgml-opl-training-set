# Standard Library
import collections


#============================================


def classify(report: dict) -> tuple[dict, bool]:
	"""
	Return (labels, needs_review).
	"""
	macros = report.get("macros", {})
	widgets = report.get("widgets", [])
	evaluators = report.get("evaluators", [])
	answers = report.get("answers", [])
	wiring = report.get("wiring", [])
	pgml = report.get("pgml", {})

	types: list[str] = []
	reasons: list[dict] = []

	load_macros = macros.get("loadMacros", [])
	has_multianswer = bool(report.get("has_multianswer", False))

	widget_kinds = [w.get("kind") for w in widgets if isinstance(w.get("kind"), str)]
	widget_kind_counts = collections.Counter(widget_kinds)

	eval_kinds = [e.get("kind") for e in evaluators if isinstance(e.get("kind"), str)]
	eval_kind_counts = collections.Counter(eval_kinds)

	ctor_names = [a.get("ctor") for a in answers if isinstance(a.get("ctor"), str)]
	ctor_counts = collections.Counter(ctor_names)

	input_count = sum(1 for w in widgets if w.get("kind") in {"blank", "popup", "radio", "checkbox", "matching", "ordering"})
	ans_count = len(evaluators)

	def add_reason(kind: str, value: str) -> None:
		reasons.append({"kind": kind, "value": value})

	if "PGgraphmacros.pl" in load_macros or "PCCgraphMacros.pl" in load_macros:
		types.append("graph_like")
		if "PGgraphmacros.pl" in load_macros:
			add_reason("macro", "PGgraphmacros.pl")
		if "PCCgraphMacros.pl" in load_macros:
			add_reason("macro", "PCCgraphMacros.pl")

	if "PGessaymacros.pl" in load_macros:
		types.append("essay")
		add_reason("macro", "PGessaymacros.pl")

	if (
		widget_kind_counts.get("radio", 0) > 0
		or widget_kind_counts.get("popup", 0) > 0
		or widget_kind_counts.get("checkbox", 0) > 0
		or eval_kind_counts.get("radio_cmp", 0) > 0
		or eval_kind_counts.get("checkbox_cmp", 0) > 0
		or eval_kind_counts.get("popup_cmp", 0) > 0
		or "parserRadioButtons.pl" in load_macros
		or "parserPopUp.pl" in load_macros
		or "parserCheckboxList.pl" in load_macros
		or "PGchoicemacros.pl" in load_macros
	):
		types.append("multiple_choice")
		if "parserRadioButtons.pl" in load_macros:
			add_reason("macro", "parserRadioButtons.pl")
		if "parserPopUp.pl" in load_macros:
			add_reason("macro", "parserPopUp.pl")
		if "parserCheckboxList.pl" in load_macros:
			add_reason("macro", "parserCheckboxList.pl")
		if "PGchoicemacros.pl" in load_macros:
			add_reason("macro", "PGchoicemacros.pl")
		if widget_kind_counts.get("radio", 0) > 0:
			add_reason("widget", "radio")
		if widget_kind_counts.get("popup", 0) > 0:
			add_reason("widget", "popup")
		if widget_kind_counts.get("checkbox", 0) > 0:
			add_reason("widget", "checkbox")
		if eval_kind_counts.get("radio_cmp", 0) > 0:
			add_reason("evaluator", "radio_cmp")
		if eval_kind_counts.get("checkbox_cmp", 0) > 0:
			add_reason("evaluator", "checkbox_cmp")
		if eval_kind_counts.get("popup_cmp", 0) > 0:
			add_reason("evaluator", "popup_cmp")

	if widget_kind_counts.get("matching", 0) > 0:
		types.append("matching")
		add_reason("widget", "matching")

	if widget_kind_counts.get("ordering", 0) > 0:
		types.append("ordering")
		add_reason("widget", "ordering")

	if input_count >= 2 or ans_count >= 2:
		types.append("multipart")
		add_reason("count", "multipart")

	if ("parserMultiAnswer.pl" in load_macros) or has_multianswer:
		if "multipart" not in types:
			types.append("multipart")
		if "parserMultiAnswer.pl" in load_macros:
			add_reason("macro", "parserMultiAnswer.pl")
		if has_multianswer:
			add_reason("multianswer", "MultiAnswer")

	if eval_kind_counts.get("str_cmp", 0) > 0 or ctor_counts.get("String", 0) > 0:
		types.append("fib_word")
		add_reason("evaluator_or_ctor", "string")

	if (
		eval_kind_counts.get("num_cmp", 0) > 0
		or eval_kind_counts.get("formula_cmp", 0) > 0
		or ctor_counts.get("Real", 0) > 0
		or ctor_counts.get("Formula", 0) > 0
		or ctor_counts.get("Compute", 0) > 0
	):
		types.append("numeric_entry")
		add_reason("evaluator_or_ctor", "numeric")

	if not types:
		pgml_blank_count = int(pgml.get("blank_count", 0) or 0)
		if (len(widgets) == 0) and (len(evaluators) == 0) and (pgml_blank_count > 0):
			types = ["unknown_pgml_blank"]
			add_reason("pgml", "blank_markers")
		else:
			types = ["other"]
			add_reason("other", "no_signals")

	confidence = _confidence(types=types, reasons=reasons, widgets=widgets, evaluators=evaluators, wiring=wiring, pgml=pgml)
	needs_review = (confidence < 0.55) or ((not wiring) and (ans_count >= 2))

	labels = {
		"types": types,
		"confidence": confidence,
		"reasons": reasons,
	}

	return labels, needs_review


#============================================


def _confidence(
	*,
	types: list[str],
	reasons: list[dict],
	widgets: list[dict],
	evaluators: list[dict],
	wiring: list[dict],
	pgml: dict,
) -> float:
	score = 0.2

	kinds = {r.get("kind") for r in reasons if isinstance(r, dict)}
	if ("macro" in kinds) and ("widget" in kinds):
		score += 0.4

	if "evaluator_or_ctor" in kinds:
		score += 0.2

	if wiring:
		score += 0.1

	if pgml.get("has_pgml_block") and pgml.get("blank_count", 0) >= 1:
		score += 0.05

	if len(types) >= 2 and "other" not in types:
		score += 0.05

	if score > 0.95:
		score = 0.95

	return round(score, 2)
