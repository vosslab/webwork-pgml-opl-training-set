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

PGML_BEGIN_RX = re.compile(r"^[ \t]*BEGIN_PGML\\b", re.MULTILINE)
PGML_END_RX = re.compile(r"^[ \t]*END_PGML\\b", re.MULTILINE)
PGML_BLANK_RX = re.compile(r"\\[[^\\]]*_{1,}[^\\]]*\\]\\s*\\{")


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
	m = re.search(r"\\$([A-Za-z_]\\w*)\\s*=\\s*$", prefix)
	if not m:
		return None
	return m.group(1)


#============================================


def extract(stripped_text: str) -> tuple[list[dict], dict]:
	"""
	Return (widgets, pgml_info).
	"""
	widgets: list[dict] = []
	calls = pg_analyze.tokenize.iter_calls(stripped_text, WIDGET_CALL_NAMES)
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

	pgml_info = _extract_pgml_info(stripped_text)
	return widgets, pgml_info


#============================================


def _extract_pgml_info(stripped_text: str) -> dict:
	begin_m = PGML_BEGIN_RX.search(stripped_text)
	end_m = PGML_END_RX.search(stripped_text)
	has_pgml = bool(begin_m and end_m and begin_m.start() < end_m.start())

	blank_count = 0
	first_blank_line: int | None = None
	if has_pgml:
		begin_index = begin_m.end()
		end_index = end_m.start()
		pgml_block = stripped_text[begin_index:end_index]
		blank_matches = list(PGML_BLANK_RX.finditer(pgml_block))
		blank_count = len(blank_matches)
		if blank_matches:
			first_blank_pos = begin_index + blank_matches[0].start()
			first_blank_line = stripped_text.count("\n", 0, first_blank_pos) + 1

	return {
		"has_pgml_block": has_pgml,
		"blank_count": blank_count,
		"first_blank_line": first_blank_line,
	}
