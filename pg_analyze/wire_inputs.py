# Standard Library
import re


NAMED_REF_RX = re.compile(r"\\b(?:named_ans_rule|NAMED_ANS_RULE)\\s*\\(\\s*['\"]([^'\"]+)['\"]")


#============================================


def wire(widgets: list[dict], evaluators: list[dict]) -> list[dict]:
	"""
	Heuristic wiring between widget indices and evaluator indices.

	- input_index refers to the index into the widgets list.
	- evaluator_index refers to the index into the evaluators list.
	"""
	wiring: list[dict] = []

	name_to_widget_index: dict[str, int] = {}
	for i, w in enumerate(widgets):
		name = w.get("name")
		if isinstance(name, str) and name and (name not in name_to_widget_index):
			name_to_widget_index[name] = i

	used_widgets: set[int] = set()
	used_evaluators: set[int] = set()

	for ei, ev in enumerate(evaluators):
		m = NAMED_REF_RX.search(ev.get("expr", ""))
		if not m:
			continue
		name = m.group(1)
		wi = name_to_widget_index.get(name)
		if wi is None:
			continue
		wiring.append(
			{
				"input_index": wi,
				"evaluator_index": ei,
				"method": "named",
				"name": name,
			}
		)
		used_widgets.add(wi)
		used_evaluators.add(ei)

	input_indices = [i for i, w in enumerate(widgets) if _is_input(w)]
	eval_indices = list(range(len(evaluators)))

	remaining_inputs = [i for i in input_indices if i not in used_widgets]
	remaining_evals = [i for i in eval_indices if i not in used_evaluators]

	if remaining_inputs and remaining_evals and (len(remaining_inputs) == len(remaining_evals)):
		for wi, ei in zip(remaining_inputs, remaining_evals, strict=True):
			wiring.append(
				{
					"input_index": wi,
					"evaluator_index": ei,
					"method": "order",
				}
			)

	return wiring


#============================================


def _is_input(widget: dict) -> bool:
	return widget.get("kind") in {
		"blank",
		"popup",
		"radio",
		"checkbox",
		"matching",
		"ordering",
	}

