#!/usr/bin/env python3
"""
Batch-render PG files via the renderer API and classify render results.

Sends every .pg file under a directory to the local webwork-pg-renderer
(PG 2.17) and records whether it renders without errors.  Results go
into a TSV that can be resumed after interruption.

For a fresh run, delete the output directory first.
"""

# Standard Library
import os
import re
import sys
import json
import html
import time
import random
import argparse
import urllib.error
import urllib.request

# Module-level timer set in main(), read-only after that
START_TIME = 0.0

# Regex patterns for redacting JWT tokens from log output
JWT_PATTERN = re.compile(
	r"(?<![A-Za-z0-9_-])"
	r"([A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
	r"(?![A-Za-z0-9_-])"
)
JWT_INPUT_PATTERN = re.compile(
	r"<input\b[^>]*\bname=[\"'][A-Za-z]+JWT[\"'][^>]*\bvalue=[\"'][^\"']+[\"'][^>]*>",
	re.IGNORECASE,
)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Batch-render PG files via the renderer API and classify results."
	)
	parser.add_argument(
		"-d", "--directory",
		dest="input_dir",
		default="problems",
		help="Root directory to scan for .pg files (default: problems).",
	)
	parser.add_argument(
		"-o", "--out-dir",
		dest="out_dir",
		default="output/renderer_lint",
		help="Directory to write result TSVs (default: output/renderer_lint).",
	)
	parser.add_argument(
		"-b", "--base-url",
		dest="base_url",
		default="http://localhost:3000",
		help="Renderer base URL (default: http://localhost:3000).",
	)
	parser.add_argument(
		"-s", "--seed",
		dest="problem_seed",
		type=int,
		default=1234,
		help="Fixed problem seed for all renders (default: 1234).",
	)
	# File ordering: shuffle for sampling or sorted for deterministic runs
	order_group = parser.add_mutually_exclusive_group()
	order_group.add_argument(
		"-S", "--shuffle",
		dest="shuffle",
		action="store_true",
		help="Randomize file processing order.",
	)
	order_group.add_argument(
		"-A", "--sorted",
		dest="shuffle",
		action="store_false",
		help="Process files in sorted alphabetical order (default).",
	)
	parser.set_defaults(shuffle=False)
	# Limit total files to process (useful for sampling)
	parser.add_argument(
		"-l", "--limit",
		dest="limit",
		type=int,
		default=0,
		help="Stop after processing this many files (default: 0 = no limit).",
	)
	args = parser.parse_args()
	return args


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
		# Sort dirs for deterministic walk order, skip .git
		dirnames[:] = sorted(d for d in dirnames if d != ".git")
		for filename in sorted(filenames):
			if filename.endswith(".pg"):
				found.append(os.path.join(dirpath, filename))
	paths = sorted(set(found))
	return paths


#============================================
def read_source(path: str) -> str:
	"""
	Read a PG source file using latin-1 encoding.

	Some .pg files in the OPL contain non-UTF-8 bytes, so latin-1
	is the safer choice for this corpus (matches pg_analyze).

	Args:
		path: File path to read.

	Returns:
		File contents as a string.
	"""
	with open(path, "rb") as handle:
		raw = handle.read()
	text = raw.decode("latin-1")
	return text


#============================================
def build_payload(source_text: str, problem_seed: int, output_format: str) -> dict:
	"""
	Build the JSON payload for the render request.

	Args:
		source_text: Raw PG source code.
		problem_seed: Integer seed for randomization.
		output_format: Output format template id.

	Returns:
		Dict ready to serialize as JSON.
	"""
	payload = {
		"problemSource": source_text,
		"problemSeed": problem_seed,
		"outputFormat": output_format,
	}
	return payload


#============================================
def redact_jwt(text: str) -> str:
	"""
	Redact JWT-like strings from output to keep logs readable.

	Args:
		text: Input string that may contain JWTs.

	Returns:
		String with JWTs replaced by a placeholder.
	"""
	if not text:
		return text
	redacted = JWT_INPUT_PATTERN.sub("", text)
	redacted = JWT_PATTERN.sub("<REDACTED_JWT>", redacted)
	return redacted


#============================================
def request_render(base_url: str, payload: dict) -> dict:
	"""
	Post to /render-api and return the decoded JSON response.

	On HTTP errors, timeouts, or connection failures returns a
	sentinel dict with an '_http_error' key instead of raising.

	Args:
		base_url: Renderer base URL (no trailing slash).
		payload: JSON-serializable request body.

	Returns:
		Parsed JSON response dict, or sentinel dict on error.
	"""
	# _format=json must be a query param, not in the JSON body
	url = f"{base_url}/render-api?_format=json"
	body = json.dumps(payload).encode("utf-8")
	headers = {"Content-Type": "application/json"}
	# Throttle API calls per repo coding style
	time.sleep(random.random())
	request = urllib.request.Request(url, data=body, headers=headers, method="POST")
	try:
		response = urllib.request.urlopen(request, timeout=90)
	except (urllib.error.URLError, TimeoutError) as err:
		error_dict = {"_http_error": str(err), "flags": {}, "errors": [str(err)]}
		return error_dict
	raw_body = response.read().decode("utf-8")
	try:
		json_body = json.loads(raw_body)
	except json.JSONDecodeError:
		json_body = {"renderedHTML": raw_body, "warnings": ["non-JSON response"]}
	return json_body


#============================================
def normalize_messages(value) -> list[str]:
	"""
	Normalize a response field into a flat list of strings.

	Args:
		value: A string, list, None, or other value from JSON.

	Returns:
		List of non-None string representations.
	"""
	if value is None:
		return []
	if isinstance(value, list):
		return [str(item) for item in value if item is not None]
	return [str(value)]


#============================================
def collect_lint_messages(response: dict) -> list[str]:
	"""
	Collect lint messages from the layered response fields.

	Checks top-level error/warning fields, then debug sub-fields,
	then falls back to scanning renderedHTML for error markers.

	Args:
		response: Parsed JSON response from the renderer.

	Returns:
		List of lint message strings (may be empty).
	"""
	messages: list[str] = []
	# Top-level error and warning fields
	messages += normalize_messages(response.get("errors"))
	messages += normalize_messages(response.get("warnings"))
	messages += normalize_messages(response.get("error"))
	messages += normalize_messages(response.get("warning"))
	messages += normalize_messages(response.get("message"))
	# Debug sub-fields
	debug = response.get("debug", {}) if isinstance(response.get("debug"), dict) else {}
	messages += normalize_messages(debug.get("pg_warn"))
	messages += normalize_messages(debug.get("internal"))
	messages += normalize_messages(debug.get("debug"))
	if messages:
		return messages
	# Fallback: scan rendered HTML for error markers
	rendered_html = response.get("renderedHTML", "")
	if not rendered_html:
		return messages
	error_match = re.search(
		r'id=[\'"]error-block[\'"][^>]*text="([^"]+)"',
		rendered_html,
		flags=re.IGNORECASE,
	)
	if error_match:
		messages.append(f"renderer error page: {html.unescape(error_match.group(1))}")
	warning_terms = ("Translator errors", "Warning messages")
	for term in warning_terms:
		if term in rendered_html:
			messages.append(f"renderedHTML contains '{term}' section")
	return messages


#============================================
def is_error_flagged(response: dict) -> bool:
	"""
	Check whether the response flags an error.

	Args:
		response: Parsed JSON response from the renderer.

	Returns:
		True if the response indicates an error condition.
	"""
	flags = response.get("flags", {}) if isinstance(response.get("flags"), dict) else {}
	error_flag = bool(flags.get("error_flag"))
	if error_flag:
		return True
	if response.get("errors"):
		return True
	if response.get("error"):
		return True
	return False


#============================================
def classify_response(response: dict) -> tuple:
	"""
	Classify a renderer response as PASS, WARN, or FAIL.

	Args:
		response: Parsed JSON response (or sentinel dict).

	Returns:
		Tuple of (status, message_count, first_message, all_messages).
	"""
	# Check for HTTP-level errors first
	http_error = response.get("_http_error", "")
	if http_error:
		first_msg = redact_jwt(http_error[:200])
		return ("FAIL", 1, first_msg, [http_error])
	error_flagged = is_error_flagged(response)
	messages = collect_lint_messages(response)
	msg_count = len(messages)
	first_msg = redact_jwt(messages[0][:200]) if messages else ""
	if error_flagged:
		status = "FAIL"
	elif msg_count > 0:
		status = "WARN"
	else:
		status = "PASS"
	return (status, msg_count, first_msg, messages)


#============================================
def load_completed_files(tsv_path: str) -> set[str]:
	"""
	Read an existing results TSV and return the set of processed file paths.

	This enables resume: files already in the TSV are skipped on re-run.

	Args:
		tsv_path: Path to the results TSV file.

	Returns:
		Set of file path strings already recorded.
	"""
	completed: set[str] = set()
	if not os.path.exists(tsv_path):
		return completed
	with open(tsv_path, "r", encoding="utf-8") as handle:
		for line in handle:
			# Skip comment headers and the column header row
			if line.startswith("#") or line.startswith("file\t"):
				continue
			parts = line.split("\t")
			if parts:
				completed.add(parts[0])
	return completed


#============================================
def write_result_row(handle, file_path: str, status: str, msg_count: int,
	first_msg: str, elapsed: float) -> None:
	"""
	Write a single TSV result row and flush immediately.

	Args:
		handle: Open file handle for the results TSV.
		file_path: Path to the .pg file that was rendered.
		status: Classification result (PASS, WARN, FAIL).
		msg_count: Number of lint messages collected.
		first_msg: First lint message (truncated, sanitized).
		elapsed: Render time in seconds.
	"""
	# Sanitize the message for TSV safety
	clean_msg = first_msg.replace("\t", " ").replace("\n", " ").replace("\r", "")
	row = f"{file_path}\t{status}\t{msg_count}\t{elapsed:.2f}\t{clean_msg}\n"
	handle.write(row)
	handle.flush()


#============================================
def write_detail_entry(handle, file_path: str, status: str, messages: list[str]) -> None:
	"""
	Write full warning/error messages for one file to the detail log.

	Only called for WARN and FAIL files so PASS files are omitted.

	Args:
		handle: Open file handle for the detail log.
		file_path: Path to the .pg file.
		status: Classification result (WARN or FAIL).
		messages: Complete list of lint/error messages.
	"""
	handle.write(f"== {status}: {file_path}\n")
	for msg in messages:
		# Redact JWTs and keep one message per line
		clean = redact_jwt(msg).replace("\r", "")
		handle.write(f"   {clean}\n")
	handle.write("\n")
	handle.flush()


#============================================
def write_tsv_header(handle) -> None:
	"""
	Write the TSV comment header and column names.

	Follows the repo convention of 5-line comment headers.

	Args:
		handle: Open file handle for the results TSV.
	"""
	handle.write("# Population: all .pg files under input directory\n")
	handle.write("# Unit: one row per .pg file render attempt\n")
	handle.write("# Notes: PASS=no errors or warnings; "
		"WARN=warnings but no error flag; "
		"FAIL=error flag or HTTP error\n")
	handle.write("# Sorted: file path alphabetical\n")
	handle.write("# ----\n")
	handle.write("file\tstatus\tmessage_count\trender_seconds\tfirst_message\n")
	handle.flush()


#============================================
def compute_summary_from_results(results_path: str) -> dict:
	"""
	Re-scan the completed results TSV for cumulative counts.

	This is accurate even after resume (counts all rows, not just
	the current session).

	Args:
		results_path: Path to the results TSV file.

	Returns:
		Dict with keys: total, pass, warn, fail.
	"""
	counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
	total = 0
	with open(results_path, "r", encoding="utf-8") as handle:
		for line in handle:
			if line.startswith("#") or line.startswith("file\t"):
				continue
			parts = line.split("\t")
			if len(parts) >= 2:
				status = parts[1]
				counts[status] = counts.get(status, 0) + 1
				total += 1
	result = {
		"total": total,
		"pass": counts["PASS"],
		"warn": counts["WARN"],
		"fail": counts["FAIL"],
	}
	return result


#============================================
def write_summary(out_dir: str, counts: dict, elapsed_total: float) -> None:
	"""
	Write summary TSV and per-status file lists.

	Args:
		out_dir: Output directory path.
		counts: Dict from compute_summary_from_results().
		elapsed_total: Total elapsed time in seconds.
	"""
	# Write summary TSV
	summary_path = os.path.join(out_dir, "renderer_lint_summary.tsv")
	lines = [
		"# Population: all .pg files under input directory",
		"# Unit: aggregate counts from batch renderer lint",
		"# Notes: PASS=no errors; WARN=warnings only; FAIL=error flag or HTTP error",
		"# Sorted: fixed row order",
		"# ----",
		"metric\tvalue",
		f"total_files\t{counts['total']}",
		f"pass\t{counts['pass']}",
		f"warn\t{counts['warn']}",
		f"fail\t{counts['fail']}",
		f"elapsed_seconds\t{elapsed_total:.1f}",
	]
	content = "\n".join(lines) + "\n"
	with open(summary_path, "w", encoding="utf-8") as handle:
		handle.write(content)
	# Write per-status file lists
	results_path = os.path.join(out_dir, "renderer_lint_results.tsv")
	status_files: dict[str, list[str]] = {"PASS": [], "WARN": [], "FAIL": []}
	with open(results_path, "r", encoding="utf-8") as handle:
		for line in handle:
			if line.startswith("#") or line.startswith("file\t"):
				continue
			parts = line.split("\t")
			if len(parts) >= 2:
				file_path = parts[0]
				status = parts[1]
				if status in status_files:
					status_files[status].append(file_path)
	# Write one file per status category
	for status, label in [("PASS", "pass"), ("WARN", "warn"), ("FAIL", "fail")]:
		list_path = os.path.join(out_dir, f"{label}_files.txt")
		file_list = sorted(status_files[status])
		with open(list_path, "w", encoding="utf-8") as handle:
			for file_path in file_list:
				handle.write(file_path + "\n")


#============================================
def log_progress(last_log: float, done: int, total: int,
	pass_count: int, warn_count: int, fail_count: int,
	session_processed: int) -> float:
	"""
	Print progress to stderr every 5 seconds with ETA.

	Args:
		last_log: Time of last progress message (perf_counter).
		done: Number of files completed (including resumed).
		total: Total number of files in this batch.
		pass_count: Running PASS count.
		warn_count: Running WARN count.
		fail_count: Running FAIL count.
		session_processed: Files rendered this session (excludes resumed).

	Returns:
		Updated last_log timestamp.
	"""
	now = time.perf_counter()
	if now - last_log < 5.0:
		return last_log
	pct = 100.0 * done / total if total > 0 else 0.0
	# Estimate time remaining using only this session's rate
	elapsed = now - START_TIME
	rate = session_processed / elapsed if elapsed > 0 else 0
	files_left = total - done
	remaining = files_left / rate if rate > 0 else 0
	remaining_min = remaining / 60.0
	msg = (f"renderer_lint: {done}/{total} ({pct:.1f}%) "
		f"P={pass_count} W={warn_count} F={fail_count} "
		f"~{remaining_min:.0f}m left")
	print(msg, file=sys.stderr, flush=True)
	return now


#============================================
def _log(msg: str) -> None:
	"""
	Print a log message to stderr.

	Args:
		msg: Message string.
	"""
	print(msg, file=sys.stderr, flush=True)


#============================================
def main() -> None:
	"""
	Run the batch renderer lint workflow.
	"""
	global START_TIME
	START_TIME = time.perf_counter()
	args = parse_args()
	base_url = args.base_url.rstrip("/")

	# Scan for .pg files
	pg_files = scan_pg_files(args.input_dir)
	_log(f"renderer_lint: found {len(pg_files)} .pg files under {args.input_dir}")

	if len(pg_files) == 0:
		_log("renderer_lint: no .pg files found, nothing to do")
		return

	# Apply shuffle or keep sorted order
	if args.shuffle:
		random.shuffle(pg_files)
		_log("renderer_lint: shuffled file order")

	# Apply limit if set
	if args.limit > 0 and args.limit < len(pg_files):
		pg_files = pg_files[:args.limit]
		_log(f"renderer_lint: limited to {args.limit} files")
	total = len(pg_files)

	# Prepare output directory
	os.makedirs(args.out_dir, exist_ok=True)
	results_path = os.path.join(args.out_dir, "renderer_lint_results.tsv")

	# Load already-completed files for resume
	completed = load_completed_files(results_path)
	# Only count files in our current batch that are already done
	skip_count = sum(1 for f in pg_files if f in completed)
	remaining = total - skip_count
	if skip_count > 0:
		_log(f"renderer_lint: resuming, {skip_count} already done, {remaining} remaining")

	if remaining == 0:
		_log("renderer_lint: all files already processed, rewriting summary")
		counts = compute_summary_from_results(results_path)
		elapsed_total = time.perf_counter() - START_TIME
		write_summary(args.out_dir, counts, elapsed_total)
		_log(f"renderer_lint: PASS={counts['pass']} WARN={counts['warn']} FAIL={counts['fail']}")
		return

	# Pre-flight: confirm the renderer is reachable before starting
	_log(f"renderer_lint: pre-flight check against {base_url}...")
	test_payload = build_payload("DOCUMENT(); ENDDOCUMENT();", args.problem_seed, "classic")
	test_response = request_render(base_url, test_payload)
	if test_response.get("_http_error"):
		raise ConnectionError(
			f"Cannot reach renderer at {base_url}: {test_response['_http_error']}"
		)
	_log("renderer_lint: pre-flight OK, renderer is reachable")

	# Decide whether to write header (fresh file) or append
	write_header = not os.path.exists(results_path) or skip_count == 0
	mode = "w" if write_header else "a"
	handle = open(results_path, mode, encoding="utf-8")
	if write_header:
		write_tsv_header(handle)

	# Open separate detail logs for warnings and errors (append for resume)
	warn_log_path = os.path.join(args.out_dir, "warn_messages.log")
	fail_log_path = os.path.join(args.out_dir, "fail_messages.log")
	warn_log = open(warn_log_path, mode, encoding="utf-8")
	fail_log = open(fail_log_path, mode, encoding="utf-8")

	# Batch processing loop
	pass_count = 0
	warn_count = 0
	fail_count = 0
	done = skip_count
	session_processed = 0
	last_log = time.perf_counter()

	for file_path in pg_files:
		# Skip files already processed in a prior run
		if file_path in completed:
			continue
		# Read and render
		source_text = read_source(file_path)
		payload = build_payload(source_text, args.problem_seed, "classic")
		render_start = time.perf_counter()
		response = request_render(base_url, payload)
		render_elapsed = time.perf_counter() - render_start
		# Classify and record
		status, msg_count, first_msg, messages = classify_response(response)
		if status == "PASS":
			pass_count += 1
		elif status == "WARN":
			warn_count += 1
			write_detail_entry(warn_log, file_path, status, messages)
		else:
			fail_count += 1
			write_detail_entry(fail_log, file_path, status, messages)
		write_result_row(handle, file_path, status, msg_count, first_msg, render_elapsed)
		done += 1
		session_processed += 1
		last_log = log_progress(
			last_log, done, total, pass_count, warn_count, fail_count, session_processed
		)

	handle.close()
	warn_log.close()
	fail_log.close()

	# Compute cumulative summary from the full results file
	counts = compute_summary_from_results(results_path)
	elapsed_total = time.perf_counter() - START_TIME
	write_summary(args.out_dir, counts, elapsed_total)

	_log(f"renderer_lint: done in {elapsed_total:.1f}s")
	_log(f"renderer_lint: PASS={counts['pass']} WARN={counts['warn']} FAIL={counts['fail']}")
	_log(f"renderer_lint: results at {results_path}")


if __name__ == "__main__":
	main()
