# Standard Library
import dataclasses
import re


@dataclasses.dataclass(frozen=True)
class Call:
	name: str
	arg_text: str
	start: int
	end: int
	line: int


#============================================


def strip_comments(text: str) -> str:
	"""
	Remove Perl line comments, preserving strings.
	"""
	out: list[str] = []
	in_sq = False
	in_dq = False
	escape = False
	i = 0
	while i < len(text):
		ch = text[i]
		if escape:
			out.append(ch)
			escape = False
			i += 1
			continue
		if ch == "\\":
			out.append(ch)
			escape = True
			i += 1
			continue
		if (not in_dq) and (ch == "'") and (not in_sq):
			in_sq = True
			out.append(ch)
			i += 1
			continue
		if in_sq and ch == "'":
			in_sq = False
			out.append(ch)
			i += 1
			continue
		if (not in_sq) and (ch == '"') and (not in_dq):
			in_dq = True
			out.append(ch)
			i += 1
			continue
		if in_dq and ch == '"':
			in_dq = False
			out.append(ch)
			i += 1
			continue
		if (not in_sq) and (not in_dq) and ch == "#":
			while i < len(text) and text[i] != "\n":
				i += 1
			out.append("\n")
			i += 1
			continue
		out.append(ch)
		i += 1
	return "".join(out)


#============================================


def _line_number(text: str, pos: int) -> int:
	return text.count("\n", 0, pos) + 1


#============================================


def iter_calls(text: str, names: set[str]) -> list[Call]:
	"""
	Find function-like calls name(...) with balanced parentheses.
	Assumes comments already stripped.
	"""
	if not names:
		return []

	name_rx = re.compile(r"\\b(" + "|".join(re.escape(n) for n in sorted(names)) + r")\\b")
	calls: list[Call] = []
	i = 0
	while True:
		m = name_rx.search(text, i)
		if not m:
			break

		name = m.group(1)
		j = m.end()
		while j < len(text) and text[j].isspace():
			j += 1
		if j >= len(text) or text[j] != "(":
			i = m.end()
			continue

		start = j
		depth = 0
		in_sq = False
		in_dq = False
		escape = False
		k = j
		while k < len(text):
			ch = text[k]
			if escape:
				escape = False
				k += 1
				continue
			if ch == "\\":
				escape = True
				k += 1
				continue
			if (not in_dq) and (ch == "'") and (not in_sq):
				in_sq = True
				k += 1
				continue
			if in_sq and ch == "'":
				in_sq = False
				k += 1
				continue
			if (not in_sq) and (ch == '"') and (not in_dq):
				in_dq = True
				k += 1
				continue
			if in_dq and ch == '"':
				in_dq = False
				k += 1
				continue

			if (not in_sq) and (not in_dq):
				if ch == "(":
					depth += 1
				elif ch == ")":
					depth -= 1
					if depth == 0:
						arg_text = text[start + 1:k]
						calls.append(
							Call(
								name=name,
								arg_text=arg_text,
								start=m.start(),
								end=k + 1,
								line=_line_number(text, m.start()),
							)
						)
						i = k + 1
						break
			k += 1
		else:
			i = m.end()

	return calls

