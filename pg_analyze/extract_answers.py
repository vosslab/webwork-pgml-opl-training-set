# Standard Library
import re


CTOR_NAMES = (
	"Real",
	"Formula",
	"Compute",
	"String",
	"List",
	"Vector",
	"Point",
)

ASSIGN_RX = re.compile(
	r"\$([A-Za-z_]\w*)\s*=\s*(" + "|".join(CTOR_NAMES) + r")\s*\(",
	re.MULTILINE,
)


#============================================


def extract(stripped_text: str) -> list[dict]:
	answers: list[dict] = []
	for m in ASSIGN_RX.finditer(stripped_text):
		var = m.group(1)
		ctor = m.group(2)
		ctor_start = m.start(2)
		paren_open = m.end() - 1
		paren_close = _find_matching_paren(stripped_text, paren_open)
		line = stripped_text.count("\n", 0, ctor_start) + 1
		expr = stripped_text[ctor_start : paren_close + 1]
		answers.append(
			{
				"var": var,
				"ctor": ctor,
				"expr": " ".join(expr.split()),
				"line": line,
			}
		)
	return answers


#============================================


def build_symbol_table(answers: list[dict]) -> dict[str, str]:
	table: dict[str, str] = {}
	for entry in answers:
		table[entry["var"]] = entry["ctor"]
	return table


#============================================


def _find_matching_paren(text: str, open_paren_index: int) -> int:
	in_sq = False
	in_dq = False
	escape = False
	depth = 0
	i = open_paren_index
	while i < len(text):
		ch = text[i]
		if escape:
			escape = False
			i += 1
			continue
		if ch == "\\":
			escape = True
			i += 1
			continue
		if (not in_dq) and (ch == "'") and (not in_sq):
			in_sq = True
			i += 1
			continue
		if in_sq and ch == "'":
			in_sq = False
			i += 1
			continue
		if (not in_sq) and (ch == '"') and (not in_dq):
			in_dq = True
			i += 1
			continue
		if in_dq and ch == '"':
			in_dq = False
			i += 1
			continue

		if (not in_sq) and (not in_dq):
			if ch == "(":
				depth += 1
			elif ch == ")":
				depth -= 1
				if depth == 0:
					return i
		i += 1

	return open_paren_index
