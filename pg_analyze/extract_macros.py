# Standard Library
import re

# Local modules
import pg_analyze.tokenize


MACRO_CALL_NAMES = {
	"loadMacros",
	"includePGproblem",
}

FILENAME_RX = re.compile(r"""['"]([^'"]+\.(?:pl|pg))['"]""")


#============================================


def extract(stripped_text: str) -> dict:
	"""
	Extract macro usage from stripped (comment-free) text.
	"""
	calls = pg_analyze.tokenize.iter_calls(stripped_text, MACRO_CALL_NAMES)

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
