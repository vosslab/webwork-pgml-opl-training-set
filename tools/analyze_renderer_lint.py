#!/usr/bin/env python3
"""
Analyze renderer lint results produced by batch_renderer_lint.py.

Reads warn_messages.log and fail_messages.log, classifies each file
into a warning/error category, and writes summary TSVs and file lists
for triage.
"""

# Standard Library
import os
import re
import sys
import argparse

# Regex patterns for classifying warning/error messages
UNDEFINED_SUB_RE = re.compile(r"Undefined subroutine &main::(\w+) called")
MISSING_AUX_RE = re.compile(r"cannot find the file: \|[^|]+\.(\w+)\|")
UNKNOWN_BLOCK_RE = re.compile(r"unknown block type '(\w+)'")
EXTRA_OPTION_RE = re.compile(r"Error: extra option '([^']*)'")
NO_PGCORE_RE = re.compile(r"no PGcore received")

# Entry header pattern: == STATUS: filepath
ENTRY_HEADER_RE = re.compile(r"^== (WARN|FAIL): (.+)$")

# Boilerplate lines to strip from messages
BOILERPLATE_PATTERNS = (
	"<br/>------",
	"==================",
	"__________________________",
)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Analyze renderer lint results and write classification reports."
	)
	parser.add_argument(
		"-d", "--input-dir",
		dest="input_dir",
		default="output/renderer_lint",
		help="Directory with renderer lint output (default: output/renderer_lint).",
	)
	parser.add_argument(
		"-o", "--out-dir",
		dest="out_dir",
		default="",
		help="Output directory for analysis TSVs (default: same as input-dir).",
	)
	args = parser.parse_args()
	# Default out_dir to input_dir if not specified
	if not args.out_dir:
		args.out_dir = args.input_dir
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
def _is_boilerplate(line: str) -> bool:
	"""
	Check whether a message line is boilerplate that should be stripped.

	Args:
		line: Stripped message line.

	Returns:
		True if the line is boilerplate.
	"""
	for pattern in BOILERPLATE_PATTERNS:
		if line.startswith(pattern):
			return True
	# Strip PGML eval header lines like "---- PGML (eval 633) 1504 ------"
	if line.startswith("---- PGML (eval "):
		return True
	# Strip "Errors parsing PGML:" header
	if line == "Errors parsing PGML:":
		return True
	return False


#============================================
def parse_message_log(path: str) -> list[dict]:
	"""
	Read a warn_messages.log or fail_messages.log file.

	Parses the == STATUS: filepath header lines and collects the
	indented message lines for each entry.

	Args:
		path: Path to the log file.

	Returns:
		List of dicts with keys: file, status, messages.
	"""
	entries: list[dict] = []
	if not os.path.exists(path):
		_log(f"analyze_lint: log file not found: {path}")
		return entries
	current_entry = None
	with open(path, "r", encoding="utf-8") as handle:
		for raw_line in handle:
			line = raw_line.rstrip("\n").rstrip("\r")
			# Check for entry header
			header_match = ENTRY_HEADER_RE.match(line)
			if header_match:
				# Save previous entry
				if current_entry is not None:
					entries.append(current_entry)
				status = header_match.group(1)
				filepath = header_match.group(2)
				current_entry = {
					"file": filepath,
					"status": status,
					"messages": [],
				}
				continue
			# Collect indented message lines for the current entry
			if current_entry is None:
				continue
			# Strip the 3-space indent
			if line.startswith("   "):
				content = line[3:]
			else:
				content = line.strip()
			# Skip empty and boilerplate lines
			if not content:
				continue
			if _is_boilerplate(content):
				continue
			current_entry["messages"].append(content)
	# Save the last entry
	if current_entry is not None:
		entries.append(current_entry)
	return entries


#============================================
def classify_entry(entry: dict) -> dict:
	"""
	Classify a parsed log entry into a warning/error category.

	Applies regex patterns in priority order. A file with multiple
	categories gets the highest-priority one as primary.

	Priority: undefined_subroutine > missing_auxiliary >
	          unknown_block_type > pgml_extra_option > no_pgcore > other

	Args:
		entry: Dict with keys: file, status, messages.

	Returns:
		Dict with keys: file, status, category, subcategory, detail.
	"""
	filepath = entry["file"]
	status = entry["status"]
	messages = entry["messages"]
	joined = "\n".join(messages)
	# Track all matches found, pick highest priority
	category = "other"
	subcategory = ""
	detail = ""
	# Check patterns in priority order (first match wins)
	# 1. undefined_subroutine
	match = UNDEFINED_SUB_RE.search(joined)
	if match:
		category = "undefined_subroutine"
		subcategory = match.group(1)
		detail = match.group(1)
		result = {
			"file": filepath,
			"status": status,
			"category": category,
			"subcategory": subcategory,
			"detail": detail,
		}
		return result
	# 2. missing_auxiliary
	match = MISSING_AUX_RE.search(joined)
	if match:
		category = "missing_auxiliary"
		subcategory = match.group(1)
		detail = match.group(1)
		result = {
			"file": filepath,
			"status": status,
			"category": category,
			"subcategory": subcategory,
			"detail": detail,
		}
		return result
	# 3. unknown_block_type
	match = UNKNOWN_BLOCK_RE.search(joined)
	if match:
		category = "unknown_block_type"
		subcategory = match.group(1)
		detail = match.group(1)
		result = {
			"file": filepath,
			"status": status,
			"category": category,
			"subcategory": subcategory,
			"detail": detail,
		}
		return result
	# 4. pgml_extra_option
	match = EXTRA_OPTION_RE.search(joined)
	if match:
		category = "pgml_extra_option"
		subcategory = match.group(1)
		detail = match.group(1)
		result = {
			"file": filepath,
			"status": status,
			"category": category,
			"subcategory": subcategory,
			"detail": detail,
		}
		return result
	# 5. no_pgcore
	match = NO_PGCORE_RE.search(joined)
	if match:
		category = "no_pgcore"
		result = {
			"file": filepath,
			"status": status,
			"category": category,
			"subcategory": subcategory,
			"detail": detail,
		}
		return result
	# 6. other -- use first message as detail
	if messages:
		detail = messages[0][:120]
	result = {
		"file": filepath,
		"status": status,
		"category": category,
		"subcategory": subcategory,
		"detail": detail,
	}
	return result


#============================================
def write_file_classifications_tsv(out_dir: str, classifications: list[dict]) -> None:
	"""
	Write per-file classification TSV.

	One row per WARN/FAIL file with category, subcategory, and detail.

	Args:
		out_dir: Output directory path.
		classifications: List of classification dicts.
	"""
	path = os.path.join(out_dir, "warn_fail_classifications.tsv")
	# Sort by file path
	sorted_rows = sorted(classifications, key=lambda c: c["file"])
	with open(path, "w", encoding="utf-8") as handle:
		handle.write("# Population: WARN and FAIL files from renderer lint\n")
		handle.write("# Unit: one row per classified file\n")
		handle.write("# Notes: category=primary warning class; "
			"subcategory=specific pattern; detail=extracted value\n")
		handle.write("# Sorted: file path alphabetical\n")
		handle.write("# ----\n")
		handle.write("file\tstatus\tcategory\tsubcategory\tdetail\n")
		for row in sorted_rows:
			# Sanitize detail for TSV
			clean_detail = row["detail"].replace("\t", " ").replace("\n", " ")
			line = (f"{row['file']}\t{row['status']}\t{row['category']}\t"
				f"{row['subcategory']}\t{clean_detail}\n")
			handle.write(line)
	_log(f"analyze_lint: wrote {path} ({len(sorted_rows)} rows)")


#============================================
def write_category_summary_tsv(out_dir: str, classifications: list[dict]) -> None:
	"""
	Write aggregate category counts TSV.

	One row per category+subcategory combination with file counts.

	Args:
		out_dir: Output directory path.
		classifications: List of classification dicts.
	"""
	path = os.path.join(out_dir, "warn_fail_category_counts.tsv")
	# Count distinct files per category+subcategory
	counts: dict[tuple, int] = {}
	for row in classifications:
		key = (row["category"], row["subcategory"])
		counts[key] = counts.get(key, 0) + 1
	# Sort by file_count descending
	sorted_keys = sorted(counts.keys(), key=lambda k: -counts[k])
	with open(path, "w", encoding="utf-8") as handle:
		handle.write("# Population: WARN and FAIL files from renderer lint\n")
		handle.write("# Unit: one row per category+subcategory combination\n")
		handle.write("# Notes: file_count=distinct files with this pattern\n")
		handle.write("# Sorted: file_count descending\n")
		handle.write("# ----\n")
		handle.write("category\tsubcategory\tfile_count\n")
		for key in sorted_keys:
			line = f"{key[0]}\t{key[1]}\t{counts[key]}\n"
			handle.write(line)
	_log(f"analyze_lint: wrote {path} ({len(sorted_keys)} categories)")


#============================================
def write_category_file_lists(out_dir: str, classifications: list[dict]) -> None:
	"""
	Write per-category file lists under a lists/ subdirectory.

	Each file contains one file path per line, sorted alphabetically.
	Filenames follow the pattern: {status}_{category}_{subcategory}.txt
	or {status}_{category}.txt when there is no subcategory.

	Args:
		out_dir: Output directory path.
		classifications: List of classification dicts.
	"""
	lists_dir = os.path.join(out_dir, "lists")
	os.makedirs(lists_dir, exist_ok=True)
	# Group files by (status_lower, category, subcategory)
	groups: dict[tuple, list[str]] = {}
	for row in classifications:
		status_lower = row["status"].lower()
		cat = row["category"]
		subcat = row["subcategory"]
		key = (status_lower, cat, subcat)
		if key not in groups:
			groups[key] = []
		groups[key].append(row["file"])
	# Write one file per group
	file_count = 0
	for key, files in sorted(groups.items()):
		status_lower, cat, subcat = key
		if subcat:
			filename = f"{status_lower}_{cat}_{subcat}.txt"
		else:
			filename = f"{status_lower}_{cat}.txt"
		path = os.path.join(lists_dir, filename)
		sorted_files = sorted(files)
		with open(path, "w", encoding="utf-8") as handle:
			for filepath in sorted_files:
				handle.write(filepath + "\n")
		file_count += 1
	_log(f"analyze_lint: wrote {file_count} file lists under {lists_dir}/")


#============================================
def main() -> None:
	"""
	Parse renderer lint logs, classify entries, and write reports.
	"""
	args = parse_args()
	input_dir = args.input_dir
	out_dir = args.out_dir
	# Verify input directory exists
	if not os.path.isdir(input_dir):
		raise FileNotFoundError(f"Input directory not found: {input_dir}")
	os.makedirs(out_dir, exist_ok=True)
	# Parse both log files
	warn_path = os.path.join(input_dir, "warn_messages.log")
	fail_path = os.path.join(input_dir, "fail_messages.log")
	_log(f"analyze_lint: reading {warn_path}")
	warn_entries = parse_message_log(warn_path)
	_log(f"analyze_lint: parsed {len(warn_entries)} WARN entries")
	_log(f"analyze_lint: reading {fail_path}")
	fail_entries = parse_message_log(fail_path)
	_log(f"analyze_lint: parsed {len(fail_entries)} FAIL entries")
	# Classify all entries
	all_entries = warn_entries + fail_entries
	classifications = []
	for entry in all_entries:
		classified = classify_entry(entry)
		classifications.append(classified)
	_log(f"analyze_lint: classified {len(classifications)} files total")
	# Write outputs
	write_file_classifications_tsv(out_dir, classifications)
	write_category_summary_tsv(out_dir, classifications)
	write_category_file_lists(out_dir, classifications)
	_log("analyze_lint: done")


if __name__ == "__main__":
	main()
