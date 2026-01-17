# Standard Library
import re

# Local modules
import pg_analyze.tokenize


WIDGET_CALL_NAMES = {
	"RadioButtons",
	"parserRadioButtons",
	"PopUp",
	"parserPopUp",
	"CheckboxList",
	"parserCheckboxList",
	"new_multiple_choice",
	"new_checkbox_multiple_choice",
	"new_select_list",
	"new_match_list",
	"Match",
	"match_list",
	"matching",
	"Sort",
	"sortable",
	"draggableProof",
	"parserAssignment",
	"ans_rule",
	"ans_box",
	"answerRule",
	"NAMED_ANS_RULE",
	"named_ans_rule",
}

NAME_RX = re.compile(r"""['"]([^'"]+)['"]""")

PGML_BLANK_RX = re.compile(r"\[[ \t]*_+[ \t]*\]")


#============================================


def _normalize_kind(call_name: str) -> str:
	if call_name in ("ans_rule", "ans_box", "answerRule", "NAMED_ANS_RULE", "named_ans_rule"):
		return "blank"
	if call_name in ("RadioButtons", "parserRadioButtons"):
		return "radio"
	if call_name in ("PopUp", "parserPopUp"):
		return "popup"
	if call_name in ("CheckboxList", "parserCheckboxList"):
		return "checkbox"
	if call_name == "new_multiple_choice":
		return "radio"
	if call_name == "new_checkbox_multiple_choice":
		return "checkbox"
	if call_name == "new_select_list":
		return "popup"
	if call_name == "new_match_list":
		return "matching"
	if call_name in ("Match", "match_list", "matching"):
		return "matching"
	if call_name in ("Sort", "sortable", "draggableProof", "parserAssignment"):
		return "ordering"
	return "other"


#============================================


def _extract_named_rule(call: pg_analyze.tokenize.Call) -> str | None:
	if call.name not in ("NAMED_ANS_RULE", "named_ans_rule"):
		return None
	m = NAME_RX.search(call.arg_text)
	if not m:
		return None
	return m.group(1)


#============================================


def _extract_assignment_name(text: str, call: pg_analyze.tokenize.Call) -> str | None:
	line_start = text.rfind("\n", 0, call.start) + 1
	prefix = text[line_start:call.start]
	m = re.search(r"\$([A-Za-z_]\w*)\s*=\s*$", prefix)
	if not m:
		return None
	return m.group(1)


#============================================


def extract(stripped_text: str, *, newlines: list[int]) -> tuple[list[dict], dict]:
	"""
	Return (widgets, pgml_info).
	"""
	widgets: list[dict] = []
	calls = pg_analyze.tokenize.iter_calls(stripped_text, WIDGET_CALL_NAMES, newlines=newlines)
	for call in calls:
		name = _extract_named_rule(call)
		if name is None:
			name = _extract_assignment_name(stripped_text, call)
		widgets.append(
			{
				"kind": _normalize_kind(call.name),
				"name": name,
				"source": call.name,
				"line": call.line,
			}
		)

	pgml_info = _extract_pgml_info(stripped_text, newlines=newlines)
	return widgets, pgml_info


#============================================


def _extract_pgml_info(stripped_text: str, *, newlines: list[int]) -> dict:
	blocks = _extract_pgml_blocks(stripped_text)

	blank_count = 0
	first_blank_line: int | None = None
	for start, end in blocks:
		block_text = stripped_text[start:end]
		for m in PGML_BLANK_RX.finditer(block_text):
			blank_count += 1
			if first_blank_line is None:
				first_blank_line = pg_analyze.tokenize.pos_to_line(newlines, start + m.start())

	return {
		"has_pgml_block": bool(blocks),
		"blank_count": blank_count,
		"first_blank_line": first_blank_line,
		"block_count": len(blocks),
	}


#============================================


def _extract_pgml_blocks(stripped_text: str) -> list[tuple[int, int]]:
	"""
	Return a list of (start, end) spans containing PGML block content.
	"""
	blocks: list[tuple[int, int]] = []
	stack: list[tuple[str, int]] = []

	for m in re.finditer(r"(?m)^[ \t]*(BEGIN|END)_PGML(?:_(SOLUTION|HINT))?\b", stripped_text):
		kind = m.group(1)
		suffix = m.group(2) or ""
		tag = f"PGML_{suffix}" if suffix else "PGML"

		if kind == "BEGIN":
			stack.append((tag, m.end()))
			continue

		if kind == "END":
			if not stack:
				continue
			open_tag, open_pos = stack.pop()
			if open_pos < m.start():
				blocks.append((open_pos, m.start()))

	return blocks
