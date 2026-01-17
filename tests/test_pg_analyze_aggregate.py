# Standard Library
# Local modules
import pg_analyze.aggregate
import pg_analyze.main


def _parse_simple_counts_tsv(tsv_text: str) -> dict[str, int]:
	lines = [l for l in tsv_text.splitlines() if l.strip()]
	assert lines
	assert "\t" in lines[0]
	out: dict[str, int] = {}
	for line in lines[1:]:
		key, count_text = line.split("\t", 1)
		out[key] = int(count_text)
	return out


def _parse_counts_all_tsv(tsv_text: str) -> dict[tuple[str, str, str], int]:
	lines = [l for l in tsv_text.splitlines() if l.strip()]
	assert lines
	assert lines[0] == "group\tscope\tkey\tcount"
	out: dict[tuple[str, str, str], int] = {}
	for line in lines[1:]:
		group, scope, key, count_text = line.split("\t")
		out[(group, scope, key)] = int(count_text)
	return out


def _parse_histograms_all_tsv(tsv_text: str) -> dict[tuple[str, str], int]:
	lines = [l for l in tsv_text.splitlines() if l.strip()]
	assert lines
	assert lines[0] == "histogram\tbin\tcount"
	out: dict[tuple[str, str], int] = {}
	for line in lines[1:]:
		hist_name, bin_name, count_text = line.split("\t")
		out[(hist_name, bin_name)] = int(count_text)
	return out


def _parse_cross_tabs_all_tsv(tsv_text: str) -> dict[tuple[str, str, str, str], int]:
	lines = [l for l in tsv_text.splitlines() if l.strip()]
	assert lines
	assert lines[0] == "row_dim\tcol_dim\trow\tcol\tcount"
	out: dict[tuple[str, str, str, str], int] = {}
	for line in lines[1:]:
		row_dim, col_dim, row, col, count_text = line.split("\t")
		out[(row_dim, col_dim, row, col)] = int(count_text)
	return out


def _parse_macro_counts_segmented_tsv(tsv_text: str) -> dict[tuple[str, str], int]:
	lines = [l for l in tsv_text.splitlines() if l.strip()]
	assert lines
	assert lines[0] == "segment\tmacro\tcount"
	out: dict[tuple[str, str], int] = {}
	for line in lines[1:]:
		segment, macro, count_text = line.split("\t")
		out[(segment, macro)] = int(count_text)
	return out


def test_aggregate_reports_from_synthetic_pg_like_strings() -> None:
	aggregator = pg_analyze.aggregate.Aggregator(needs_review_limit=200)

	numeric_text = (
		'loadMacros("PGstandard.pl", "MathObjects.pl");\n'
		"Context('Numeric');\n"
		"$a = Real(3);\n"
		"ans_rule(20);\n"
		"ANS($a->cmp());\n"
	)
	mc_text = (
		'loadMacros("PGstandard.pl", "parserRadioButtons.pl");\n'
		"$rb = RadioButtons([\"A\", \"B\"], \"A\");\n"
		"ANS($rb->cmp());\n"
	)
	multipart_text = (
		'loadMacros("PGstandard.pl", "MathObjects.pl");\n'
		"$a = Real(1);\n"
		"$b = Real(2);\n"
		"ans_rule(20);\n"
		"ans_rule(20);\n"
		"ANS($a->cmp());\n"
		"ANS($b->cmp());\n"
	)
	other_text = (
		'loadMacros("AppletObjects.pl");\n'
	)
	unknown_pgml_blank_text = (
		"BEGIN_PGML\n"
		"[_]\n"
		"END_PGML\n"
	)

	records = [
		pg_analyze.main.analyze_text(text=numeric_text, file_path="a.pg"),
		pg_analyze.main.analyze_text(text=mc_text, file_path="b.pg"),
		pg_analyze.main.analyze_text(text=multipart_text, file_path="c.pg"),
		pg_analyze.main.analyze_text(text=other_text, file_path="d.pg"),
		pg_analyze.main.analyze_text(text=unknown_pgml_blank_text, file_path="e.pg"),
	]

	for r in records:
		aggregator.add_record(r)

	reports = aggregator.render_reports()

	counts_all = _parse_counts_all_tsv(reports["counts_all.tsv"])
	assert counts_all[("type", "all", "numeric_entry")] == 2
	assert counts_all[("type", "all", "multiple_choice")] == 1
	assert counts_all[("type", "all", "multipart")] == 1
	assert counts_all[("type", "all", "other")] == 1
	assert counts_all[("type", "all", "unknown_pgml_blank")] == 1

	hists_all = _parse_histograms_all_tsv(reports["histograms_all.tsv"])
	assert hists_all[("confidence_bin", "0.5-0.6")] == 2
	assert hists_all[("confidence_bin", "0.7-0.8")] == 1

	assert counts_all[("macro_load", "all", "PGstandard.pl")] == 3
	assert counts_all[("macro_load", "all", "MathObjects.pl")] == 2
	assert counts_all[("macro_load", "all", "parserRadioButtons.pl")] == 1
	assert counts_all[("macro_load", "all", "AppletObjects.pl")] == 1

	assert counts_all[("widget_kind", "all", "blank")] == 3
	assert counts_all[("widget_kind", "all", "radio")] == 1

	assert counts_all[("evaluator_kind", "all", "cmp")] == 4

	assert hists_all[("input_count", "1")] == 3
	assert hists_all[("input_count", "2")] == 1
	assert hists_all[("input_count", "0")] == 1

	assert hists_all[("ans_count", "1")] == 2
	assert hists_all[("ans_count", "2")] == 1
	assert hists_all[("ans_count", "0")] == 2

	needs_review_lines = [l for l in reports["needs_review.tsv"].splitlines() if l.strip()]
	assert needs_review_lines[0].startswith("file\tconfidence\tbucket\t")
	assert len(needs_review_lines) == 4
	assert any(l.startswith("d.pg\t0.20\tcoverage_no_signals\t") for l in needs_review_lines[1:])
	assert any(l.startswith("e.pg\t0.25\twidget_no_evaluator\t") for l in needs_review_lines[1:])
	assert any(l.startswith("a.pg\t0.50\tlow_confidence_misc\t") for l in needs_review_lines[1:])

	needs_review_bucket_counts = _parse_simple_counts_tsv(reports["needs_review_bucket_counts.tsv"])
	assert needs_review_bucket_counts["coverage_no_signals"] == 1
	assert needs_review_bucket_counts["widget_no_evaluator"] == 1
	assert needs_review_bucket_counts["low_confidence_misc"] == 1

	needs_review_type_counts = _parse_simple_counts_tsv(reports["needs_review_type_counts.tsv"])
	assert needs_review_type_counts["numeric_entry"] == 1
	assert needs_review_type_counts["other"] == 1
	assert needs_review_type_counts["unknown_pgml_blank"] == 1

	needs_review_macro_counts = _parse_simple_counts_tsv(reports["needs_review_macro_counts.tsv"])
	assert needs_review_macro_counts["PGstandard.pl"] == 1
	assert needs_review_macro_counts["MathObjects.pl"] == 1
	assert needs_review_macro_counts["AppletObjects.pl"] == 1

	other_breakdown = _parse_simple_counts_tsv(reports["other_breakdown.tsv"])
	assert other_breakdown["other_applet_like"] == 1

	macro_counts_segmented = _parse_macro_counts_segmented_tsv(reports["macro_counts_segmented.tsv"])
	assert macro_counts_segmented[("other", "AppletObjects.pl")] == 1

	assert hists_all[("pgml_blank_marker_count", "0")] == 4
	assert hists_all[("pgml_blank_marker_count", "1")] == 1

	cross_tabs_all = _parse_cross_tabs_all_tsv(reports["cross_tabs_all.tsv"])
	assert cross_tabs_all[("type", "widget_kind", "other", "none")] == 1
	assert cross_tabs_all[("type", "evaluator_kind", "other", "none")] == 1
	assert cross_tabs_all[("widget_kind", "evaluator_kind", "radio", "cmp")] == 1

	coverage = _parse_simple_counts_tsv(reports["coverage.tsv"])
	assert coverage["widgets=some,eval=ans_only"] == 3
	assert coverage["widgets=some,eval=none"] == 1
	assert coverage["widgets=none,eval=none"] == 1
	assert coverage["widgets=none,eval=ans_only"] == 0
	assert coverage["widgets=none,eval=pgml_only"] == 0
	assert coverage["widgets=none,eval=both"] == 0
	assert coverage["widgets=some,eval=pgml_only"] == 0
	assert coverage["widgets=some,eval=both"] == 0

	# Duplicate helpers should be robust to missing hash fields.
	dup_top = reports["duplicate_clusters_top.tsv"].splitlines()
	assert dup_top[0] == "hash_type\tgroup_size\thash\trepresentative_file"
