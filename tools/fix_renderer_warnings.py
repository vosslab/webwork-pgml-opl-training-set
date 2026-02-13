#!/usr/bin/env python3
"""
Remove display-only helper calls that trigger renderer warnings.

Fixes three categories of undefined subroutine warnings from
batch_renderer_lint.py by removing non-essential display helper calls:

  - AnswerFormatHelp("...")       -- answer format help links
  - KeyboardInstructions(...)     -- keyboard input tips
  - EnlargeImageStatementPGML()   -- "click to enlarge" text
  - numberWord(expr)              -- replaced with just expr (numeric value)

Also removes the "AnswerFormatHelp.pl" macro load line when present.

These helpers produce student-facing hint text that is not required
for the problem to function correctly.  numberWord() converts integers
to English words; replacing it with the raw value is sufficient for
training purposes.
"""

# Standard Library
import os
import re
import sys
import argparse

# Regex patterns for PGML inline helper calls: [@ FuncName(...) @]* or @]**
# AnswerFormatHelp always takes a simple quoted string argument
ANSWER_FORMAT_HELP_RE = re.compile(
	r"\[@\s*AnswerFormatHelp\([^)]*\)\s*@\]\*{1,2}"
)
# KeyboardInstructions can have complex arguments (q!...! or "...")
# Greedy .* matches to the last ) before @] on the line
KEYBOARD_INSTRUCTIONS_RE = re.compile(
	r"\[@\s*KeyboardInstructions\(.*\)\s*@\]\*{1,2}"
)
# EnlargeImageStatementPGML always takes no arguments
ENLARGE_IMAGE_RE = re.compile(
	r"\[@\s*EnlargeImageStatementPGML\(\)\s*@\]\*{1,2}"
)
# numberWord(expr) or numberWord(expr, named=>args) -- keep first arg only
NUMBER_WORD_RE = re.compile(
	r"numberWord\(([^,)]+)(?:,[^)]*?)?\)"
)
# Macro load line: "AnswerFormatHelp.pl" with optional trailing comma
MACRO_LOAD_RE = re.compile(
	r'^\s*"AnswerFormatHelp\.pl"\s*,?\s*$'
)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Remove display-only helper calls that trigger renderer warnings."
	)
	parser.add_argument(
		"-d", "--directory",
		dest="input_dir",
		default="problems",
		help="Root directory to scan for .pg files (default: problems).",
	)
	# Dry run vs write mode
	mode_group = parser.add_mutually_exclusive_group()
	mode_group.add_argument(
		"-n", "--dry-run",
		dest="dry_run",
		action="store_true",
		help="Show what would be changed without modifying files (default).",
	)
	mode_group.add_argument(
		"-w", "--write",
		dest="dry_run",
		action="store_false",
		help="Actually modify files in place.",
	)
	parser.set_defaults(dry_run=True)
	args = parser.parse_args()
	return args


#============================================
def _log(msg: str) -> None:
	"""
	Print a log message to stderr.

	Args:
		msg: Message string.
	"""
	print(msg, file=sys.stderr, flush=True)


#============================================
def scan_pg_files(input_dir: str) -> list[str]:
	"""
	Find all .pg files under input_dir, sorted alphabetically.

	Args:
		input_dir: Root directory to scan.

	Returns:
		Sorted list of .pg file paths.
	"""
	found: list[str] = []
	for dirpath, dirnames, filenames in os.walk(input_dir):
		dirnames[:] = sorted(d for d in dirnames if d != ".git")
		for filename in sorted(filenames):
			if filename.endswith(".pg"):
				found.append(os.path.join(dirpath, filename))
	paths = sorted(set(found))
	return paths


#============================================
def fix_file(path: str) -> dict:
	"""
	Apply display-helper removal fixes to a single .pg file.

	Reads the file, removes matching patterns line by line, and
	returns the result without writing. Lines that become blank
	after removal are dropped.

	Args:
		path: Path to the .pg file.

	Returns:
		Dict with keys: modified (bool), original (str),
		fixed (str), counts (dict of pattern names to int).
	"""
	with open(path, "rb") as handle:
		raw = handle.read()
	original = raw.decode("latin-1")
	lines = original.split("\n")
	output_lines: list[str] = []
	counts = {
		"answer_format_help_call": 0,
		"keyboard_instructions_call": 0,
		"enlarge_image_call": 0,
		"number_word_call": 0,
		"answer_format_help_macro": 0,
	}
	for line in lines:
		modified_line = line
		# Remove AnswerFormatHelp calls
		if "AnswerFormatHelp" in modified_line:
			# Check for macro load line first
			if MACRO_LOAD_RE.match(modified_line):
				counts["answer_format_help_macro"] += 1
				continue
			# Remove inline calls
			new_line = ANSWER_FORMAT_HELP_RE.sub("", modified_line)
			if new_line != modified_line:
				counts["answer_format_help_call"] += 1
				modified_line = new_line
		# Remove KeyboardInstructions calls
		if "KeyboardInstructions" in modified_line:
			new_line = KEYBOARD_INSTRUCTIONS_RE.sub("", modified_line)
			if new_line != modified_line:
				counts["keyboard_instructions_call"] += 1
				modified_line = new_line
		# Remove EnlargeImageStatementPGML calls
		if "EnlargeImageStatementPGML" in modified_line:
			new_line = ENLARGE_IMAGE_RE.sub("", modified_line)
			if new_line != modified_line:
				counts["enlarge_image_call"] += 1
				modified_line = new_line
		# Replace numberWord(expr) with just expr
		if "numberWord" in modified_line:
			new_line = NUMBER_WORD_RE.sub(r"\1", modified_line)
			if new_line != modified_line:
				counts["number_word_call"] += 1
				modified_line = new_line
		# Strip trailing whitespace from modified lines
		if modified_line != line:
			modified_line = modified_line.rstrip()
		# Drop lines that became blank after removal
		if modified_line != line and modified_line.strip() == "":
			continue
		output_lines.append(modified_line)
	fixed = "\n".join(output_lines)
	modified = (fixed != original)
	total = sum(counts.values())
	result = {
		"modified": modified,
		"original": original,
		"fixed": fixed,
		"counts": counts,
		"total_fixes": total,
	}
	return result


#============================================
def main() -> None:
	"""
	Scan .pg files and remove display-only helper calls.
	"""
	args = parse_args()
	# Verify input directory exists
	if not os.path.isdir(args.input_dir):
		raise FileNotFoundError(f"Directory not found: {args.input_dir}")
	mode_label = "DRY RUN" if args.dry_run else "WRITE"
	_log(f"fix_warnings: mode={mode_label}")
	# Scan for .pg files
	pg_files = scan_pg_files(args.input_dir)
	_log(f"fix_warnings: found {len(pg_files)} .pg files under {args.input_dir}")
	# Process each file
	files_modified = 0
	total_counts = {
		"answer_format_help_call": 0,
		"keyboard_instructions_call": 0,
		"enlarge_image_call": 0,
		"number_word_call": 0,
		"answer_format_help_macro": 0,
	}
	for path in pg_files:
		result = fix_file(path)
		if not result["modified"]:
			continue
		files_modified += 1
		# Accumulate counts
		for key in total_counts:
			total_counts[key] += result["counts"][key]
		# Write the fixed file
		if not args.dry_run:
			with open(path, "wb") as handle:
				handle.write(result["fixed"].encode("latin-1"))
		# Log each modified file
		parts = []
		for key, val in result["counts"].items():
			if val > 0:
				parts.append(f"{key}={val}")
		detail = ", ".join(parts)
		_log(f"  {path} ({detail})")
	# Summary
	_log(f"fix_warnings: {files_modified} files {'would be ' if args.dry_run else ''}modified")
	for key, val in total_counts.items():
		if val > 0:
			_log(f"  {key}: {val}")
	if args.dry_run and files_modified > 0:
		_log("fix_warnings: re-run with --write to apply changes")


if __name__ == "__main__":
	main()
