#!/usr/bin/env python3

# Standard Library
import argparse
import json
import os
import subprocess
import sys

# Determine repo root and add to path for local imports
REPO_ROOT = subprocess.run(
	["git", "rev-parse", "--show-toplevel"],
	capture_output=True,
	text=True,
	check=True,
).stdout.strip()
if REPO_ROOT not in sys.path:
	sys.path.insert(0, REPO_ROOT)

# Local modules
import pgml_lint.core
import pgml_lint.engine
import pgml_lint.registry
import pgml_lint.rules


#============================================


def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.

	Returns:
		argparse.Namespace: Parsed arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Run a static lint pass on WeBWorK .pg files with PGML checks.",
	)
	parser.add_argument(
		"-i",
		"--input",
		dest="input_file",
		help="Path to a single .pg file to lint.",
	)
	parser.add_argument(
		"-d",
		"--directory",
		dest="input_dir",
		default=".",
		help="Directory to scan for .pg files (default: current directory).",
	)
	parser.add_argument(
		"-e",
		"--extensions",
		dest="extensions",
		default=".pg",
		help="Comma-separated list of file extensions (default: .pg).",
	)
	parser.add_argument(
		"-r",
		"--rules",
		dest="rules_file",
		help="Optional JSON file defining block and macro rules.",
	)
	parser.add_argument(
		"--plugin",
		dest="plugin_paths",
		action="append",
		default=[],
		help="Path to a plugin module file (repeatable).",
	)
	parser.add_argument(
		"--enable",
		dest="enable_plugins",
		action="append",
		default=[],
		help="Comma-separated plugin ids to enable.",
	)
	parser.add_argument(
		"--disable",
		dest="disable_plugins",
		action="append",
		default=[],
		help="Comma-separated plugin ids to disable.",
	)
	parser.add_argument(
		"--only",
		dest="only_plugins",
		action="append",
		default=[],
		help="Comma-separated plugin ids to run exclusively.",
	)
	parser.add_argument(
		"--list-plugins",
		dest="list_plugins",
		action="store_true",
		help="List available plugins and exit.",
	)
	parser.add_argument(
		"--show-plugin",
		dest="show_plugin",
		action="store_true",
		help="Include plugin id in line output.",
	)
	parser.add_argument(
		"--json",
		dest="json_output",
		action="store_true",
		help="Emit issues and summaries as JSON.",
	)
	parser.add_argument(
		"--fail-on-warn",
		dest="fail_on_warn",
		action="store_true",
		help="Exit non-zero if warnings are found.",
	)
	parser.set_defaults(fail_on_warn=False, json_output=False, list_plugins=False)
	args = parser.parse_args()
	return args


#============================================


def _split_csv(values: list[str]) -> set[str]:
	"""
	Split comma-separated lists into a set.

	Args:
		values: List of CSV strings.

	Returns:
		set[str]: Normalized ids.
	"""
	items: set[str] = set()
	for value in values:
		for raw in value.split(","):
			item = raw.strip()
			if item:
				items.add(item)
	return items


#============================================


def normalize_extensions(extensions: str) -> list[str]:
	"""
	Normalize comma-separated extensions into a list.

	Args:
		extensions: Raw comma-separated string.

	Returns:
		list[str]: Normalized extensions.
	"""
	extensions_list = [ext.strip() for ext in extensions.split(",") if ext.strip()]
	normalized: list[str] = []
	for ext in extensions_list:
		if ext.startswith("."):
			normalized.append(ext.lower())
		else:
			normalized.append(f".{ext.lower()}")
	return normalized


#============================================


def find_files(input_dir: str, extensions: list[str]) -> list[str]:
	"""
	Find files under input_dir matching extensions.

	Args:
		input_dir: Root directory to scan.
		extensions: File extensions to include.

	Returns:
		list[str]: Sorted file paths.
	"""
	matches: list[str] = []
	for root, dirs, files in os.walk(input_dir):
		dirs.sort()
		files.sort()
		for filename in files:
			ext = os.path.splitext(filename)[1].lower()
			if ext in extensions:
				matches.append(os.path.join(root, filename))
	paths = sorted(matches)
	return paths


#============================================


def list_plugins(registry: pgml_lint.registry.Registry) -> None:
	"""
	Print available plugins.

	Args:
		registry: Plugin registry.
	"""
	for plugin in registry.list_plugins():
		plugin_id = str(plugin.get("id"))
		plugin_name = str(plugin.get("name"))
		default_flag = "default" if plugin.get("default_enabled") is True else "optional"
		print(f"{plugin_id}: {plugin_name} ({default_flag})")


#============================================


def main() -> None:
	"""
	Run the lint checker.
	"""
	args = parse_args()
	block_rules, macro_rules = pgml_lint.rules.load_rules(args.rules_file)
	registry = pgml_lint.registry.build_registry()

	for plugin_path in args.plugin_paths:
		registry.load_plugin_path(plugin_path)

	if args.list_plugins:
		list_plugins(registry)
		return

	only_ids = _split_csv(args.only_plugins)
	enable_ids = _split_csv(args.enable_plugins)
	disable_ids = _split_csv(args.disable_plugins)
	plugins = registry.resolve_plugins(only_ids, enable_ids, disable_ids)

	issues: list[dict[str, object]] = []
	files_checked: list[str] = []

	if args.input_file:
		files_checked.append(args.input_file)
		file_issues = pgml_lint.engine.lint_file(
			args.input_file,
			block_rules,
			macro_rules,
			plugins,
		)
		issues.extend(file_issues)
		if not args.json_output:
			for issue in file_issues:
				print(pgml_lint.core.format_issue(args.input_file, issue, args.show_plugin))
	else:
		extensions = normalize_extensions(args.extensions)
		files_to_check = find_files(args.input_dir, extensions)
		files_checked.extend(files_to_check)
		for file_path in files_to_check:
			file_issues = pgml_lint.engine.lint_file(
				file_path,
				block_rules,
				macro_rules,
				plugins,
			)
			issues.extend(file_issues)
			if not args.json_output:
				for issue in file_issues:
					print(pgml_lint.core.format_issue(file_path, issue, args.show_plugin))

	error_count, warn_count = pgml_lint.core.summarize_issues(issues)

	if args.json_output:
		plugin_ids = [str(plugin.get("id")) for plugin in plugins]
		summary = {
			"files_checked": len(files_checked),
			"errors": error_count,
			"warnings": warn_count,
			"plugins": plugin_ids,
			"issues": issues,
		}
		print(json.dumps(summary, indent=2))
	else:
		if issues:
			print(f"Found {error_count} errors and {warn_count} warnings.")

	if error_count > 0:
		raise SystemExit(1)
	if args.fail_on_warn and warn_count > 0:
		raise SystemExit(1)


if __name__ == "__main__":
	main()
