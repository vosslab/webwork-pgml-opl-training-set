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
	reasons: list[str] = []

	load_macros = macros.get("loadMacros", [])

	widget_kinds = [w.get("kind") for w in widgets if isinstance(w.get("kind"), str)]
	widget_kind_counts = collections.Counter(widget_kinds)

	eval_kinds = [e.get("kind") for e in evaluators if isinstance(e.get("kind"), str)]
	eval_kind_counts = collections.Counter(eval_kinds)

	ctor_names = [a.get("ctor") for a in answers if isinstance(a.get("ctor"), str)]
	ctor_counts = collections.Counter(ctor_names)

	input_count = sum(1 for w in widgets if w.get("kind") in {"blank", "popup", "radio", "checkbox", "matching", "ordering"})
	ans_count = len(evaluators)

	if widget_kind_counts.get("radio", 0) > 0 or "parserRadioButtons.pl" in load_macros:
		types.append("multiple_choice")
		if "parserRadioButtons.pl" in load_macros:
			reasons.append("macro:parserRadioButtons.pl")
		if widget_kind_counts.get("radio", 0) > 0:
			reasons.append("widget:radio")

	if widget_kind_counts.get("matching", 0) > 0:
		types.append("matching")
		reasons.append("widget:matching")

	if widget_kind_counts.get("ordering", 0) > 0:
		types.append("ordering")
		reasons.append("widget:ordering")

	if input_count >= 2 or ans_count >= 2:
		types.append("multipart")
		reasons.append("count:multipart")

	if eval_kind_counts.get("str_cmp", 0) > 0 or ctor_counts.get("String", 0) > 0:
		types.append("fib_word")
		reasons.append("evaluator_or_ctor:string")

	if (
		eval_kind_counts.get("num_cmp", 0) > 0
		or eval_kind_counts.get("formula_cmp", 0) > 0
		or ctor_counts.get("Real", 0) > 0
		or ctor_counts.get("Formula", 0) > 0
		or ctor_counts.get("Compute", 0) > 0
	):
		types.append("numeric_entry")
		reasons.append("evaluator_or_ctor:numeric")

	if not types:
		types = ["other"]
		reasons.append("no_signals")

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
	reasons: list[str],
	widgets: list[dict],
	evaluators: list[dict],
	wiring: list[dict],
	pgml: dict,
) -> float:
	score = 0.2

	if any(r.startswith("macro:") for r in reasons) and any(r.startswith("widget:") for r in reasons):
		score += 0.4

	if any(r.startswith("evaluator_or_ctor:") for r in reasons):
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

