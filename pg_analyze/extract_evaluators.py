# Standard Library
import re

# Local modules
import pg_analyze.tokenize


EVALUATOR_CALL_NAMES = {
	"ANS",
}

VAR_RX = re.compile(r"\\$([A-Za-z_]\\w*)")


#============================================


def extract(stripped_text: str) -> list[dict]:
	evaluators: list[dict] = []
	calls = pg_analyze.tokenize.iter_calls(stripped_text, EVALUATOR_CALL_NAMES)
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
	if re.search(r"\\bnum_cmp\\s*\\(", expr):
		return "num_cmp"
	if re.search(r"\\bfun_cmp\\s*\\(", expr):
		return "fun_cmp"
	if re.search(r"\\bformula_cmp\\s*\\(", expr):
		return "formula_cmp"
	if re.search(r"\\b(str_cmp|string_cmp)\\s*\\(", expr):
		return "str_cmp"
	if re.search(r"\\bchecker\\s*=>\\s*sub\\s*\\{", expr):
		return "custom"
	return "other"

