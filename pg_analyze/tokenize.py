# Standard Library
import bisect
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


def build_newline_index(text: str) -> list[int]:
	"""
	Return sorted positions of '\n' characters.
	"""
	newlines: list[int] = []
	pos = text.find("\n")
	while pos != -1:
		newlines.append(pos)
		pos = text.find("\n", pos + 1)
	return newlines


#============================================


def pos_to_line(newlines: list[int], pos: int) -> int:
	"""
	Map a byte offset to 1-based line number using a newline index.
	"""
	return bisect.bisect_left(newlines, pos) + 1


#============================================


def strip_comments(text: str) -> str:
	"""
	Remove Perl line comments, preserving strings and heredocs.
	"""
	out_lines: list[str] = []
	heredoc_end: str | None = None

	for line in text.splitlines(keepends=True):
		if heredoc_end is not None:
			out_lines.append(line)
			if line.strip() == heredoc_end:
				heredoc_end = None
			continue

		heredoc_end = _scan_heredoc_terminator(line)
		out_lines.append(_strip_line_comment_preserving_strings(line))

	return "".join(out_lines)


#============================================


def _scan_heredoc_terminator(line: str) -> str | None:
	"""
	Detect a heredoc introducer outside of strings and return its terminator token.
	"""
	in_sq = False
	in_dq = False
	escape = False

	i = 0
	while i < len(line) - 1:
		ch = line[i]
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

		if (not in_sq) and (not in_dq) and (ch == "<") and (line[i + 1] == "<"):
			j = i + 2
			if j < len(line) and line[j] == "-":
				j += 1
			while j < len(line) and line[j].isspace():
				j += 1
			if j >= len(line):
				return None

			if line[j] in ("'", '"'):
				quote = line[j]
				j += 1
				start = j
				while j < len(line) and line[j] != quote:
					j += 1
				if j >= len(line):
					return None
				return line[start:j]

			start = j
			if not (line[j].isalpha() or line[j] == "_"):
				return None
			j += 1
			while j < len(line) and (line[j].isalnum() or line[j] == "_"):
				j += 1
			return line[start:j]

		i += 1

	return None


#============================================


def _strip_line_comment_preserving_strings(line: str) -> str:
	in_sq = False
	in_dq = False
	escape = False
	for i, ch in enumerate(line):
		if escape:
			escape = False
			continue
		if ch == "\\":
			escape = True
			continue
		if (not in_dq) and (ch == "'") and (not in_sq):
			in_sq = True
			continue
		if in_sq and ch == "'":
			in_sq = False
			continue
		if (not in_sq) and (ch == '"') and (not in_dq):
			in_dq = True
			continue
		if in_dq and ch == '"':
			in_dq = False
			continue
		if (not in_sq) and (not in_dq) and ch == "#":
			return line[:i] + ("\n" if line.endswith("\n") else "")
	return line


#============================================


def _compile_name_rx(names: set[str]) -> re.Pattern:
	cache_key = frozenset(names)
	cached = _NAME_RX_CACHE.get(cache_key)
	if cached is not None:
		return cached

	parts: list[str] = []
	for name in sorted(names):
		parts.append(re.escape(name))
	pat = r"(?:" + "|".join(parts) + r")"
	compiled = re.compile(r"(?<!\w)" + pat + r"(?!\w)")
	_NAME_RX_CACHE[cache_key] = compiled
	return compiled


_NAME_RX_CACHE: dict[frozenset[str], re.Pattern] = {}


#============================================


def iter_calls(text: str, names: set[str], newlines: list[int] | None = None) -> list[Call]:
	"""
	Find function-like calls name(...) with balanced parentheses.
	Assumes comments already stripped.
	"""
	if not names:
		return []

	if newlines is None:
		newlines = build_newline_index(text)

	name_rx = _compile_name_rx(names)
	calls: list[Call] = []
	i = 0
	while True:
		m = name_rx.search(text, i)
		if not m:
			break

		name = m.group(0)
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
								line=pos_to_line(newlines, m.start()),
							)
						)
						i = k + 1
						break
			k += 1
		else:
			i = m.end()

	return calls
