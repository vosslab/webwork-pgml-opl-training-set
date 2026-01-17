# Standard Library
import re

# Local modules
import pg_analyze.tokenize


EVALUATOR_CALL_NAMES = {
	"ANS",
}

MACRO_CALL_NAMES = {
	"loadMacros",
	"includePGproblem",
}

VAR_RX = re.compile(r"\$([A-Za-z_]\w*)")
FILENAME_RX = re.compile(r"""['"]([^'"]+\.(?:pl|pg))['"]""")


#============================================


def extract_macros(stripped_text: str, *, newlines: list[int]) -> dict:
	"""
	Extract macro usage from stripped (comment-free) text.
	"""
	calls = pg_analyze.tokenize.iter_calls(stripped_text, MACRO_CALL_NAMES, newlines=newlines)

	load_macros: list[str] = []
	include_pgproblem: list[str] = []

	for call in calls:
		matches = [m.group(1) for m in FILENAME_RX.finditer(call.arg_text)]
		if call.name == "loadMacros":
			for filename in matches:
				if filename not in load_macros:
					load_macros.append(filename)
		elif call.name == "includePGproblem":
			for filename in matches:
				if filename not in include_pgproblem:
					include_pgproblem.append(filename)

	return {
		"loadMacros": load_macros,
		"includePGproblem": include_pgproblem,
	}


#============================================


def extract(stripped_text: str, *, newlines: list[int]) -> list[dict]:
	evaluators: list[dict] = []
	calls = pg_analyze.tokenize.iter_calls(stripped_text, EVALUATOR_CALL_NAMES, newlines=newlines)
	for call in calls:
		expr = _normalize_ws(call.arg_text)
		evaluators.append(
			{
				"kind": _classify(expr),
				"expr": expr,
				"vars": _extract_vars(expr),
				"line": call.line,
			}
		)
	return evaluators


#============================================


def _normalize_ws(text: str) -> str:
	return " ".join(text.split())


#============================================


def _extract_vars(expr: str) -> list[str]:
	vars_found: list[str] = []
	for m in VAR_RX.finditer(expr):
		v = m.group(1)
		if v not in vars_found:
			vars_found.append(v)
	return vars_found


#============================================


def _classify(expr: str) -> str:
	if "->cmp(" in expr or expr.endswith("->cmp()") or "->cmp()" in expr:
		return "cmp"
	if re.search(r"\bnamed_ans_rule\s*\(", expr):
		return "named_rule"
	if re.search(r"\bradio_cmp\s*\(", expr):
		return "radio_cmp"
	if re.search(r"\bcheckbox_cmp\s*\(", expr):
		return "checkbox_cmp"
	if re.search(r"\bpopup_cmp\s*\(", expr):
		return "popup_cmp"
	if re.search(r"\bnum_cmp\s*\(", expr):
		return "num_cmp"
	if re.search(r"\bfun_cmp\s*\(", expr):
		return "fun_cmp"
	if re.search(r"\bformula_cmp\s*\(", expr):
		return "formula_cmp"
	if re.search(r"\b(str_cmp|string_cmp)\s*\(", expr):
		return "str_cmp"
	if re.search(r"\bchecker\s*=>\s*sub\s*\{", expr):
		return "custom"
	return "other"
