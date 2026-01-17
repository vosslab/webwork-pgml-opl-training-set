# Standard Library
# Local modules
import pg_analyze.aggregate
import pg_analyze.main


def _parse_counts_tsv(tsv_text: str) -> dict[str, int]:
	lines = [l for l in tsv_text.splitlines() if l.strip()]
	assert lines
	assert "\t" in lines[0]
	out: dict[str, int] = {}
	for line in lines[1:]:
		key, count_text = line.split("\t", 1)
		out[key] = int(count_text)
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

	type_counts = _parse_counts_tsv(reports["counts_by_type.tsv"])
	assert type_counts["numeric_entry"] == 2
	assert type_counts["multiple_choice"] == 1
	assert type_counts["multipart"] == 1
	assert type_counts["other"] == 1
	assert type_counts["unknown_pgml_blank"] == 1

	conf_bins = _parse_counts_tsv(reports["confidence_bins.tsv"])
	assert conf_bins["0.5-0.6"] == 2
	assert conf_bins["0.7-0.8"] == 1

	macro_counts = _parse_counts_tsv(reports["macro_counts.tsv"])
	assert macro_counts["PGstandard.pl"] == 3
	assert macro_counts["MathObjects.pl"] == 2
	assert macro_counts["parserRadioButtons.pl"] == 1
	assert macro_counts["AppletObjects.pl"] == 1

	widget_counts = _parse_counts_tsv(reports["widget_counts.tsv"])
	assert widget_counts["blank"] == 3
	assert widget_counts["radio"] == 1

	eval_counts = _parse_counts_tsv(reports["evaluator_counts.tsv"])
	assert eval_counts["cmp"] == 4

	input_hist = _parse_counts_tsv(reports["input_count_hist.tsv"])
	assert input_hist["1"] == 3
	assert input_hist["2"] == 1
	assert input_hist["0"] == 1

	ans_hist = _parse_counts_tsv(reports["ans_count_hist.tsv"])
	assert ans_hist["1"] == 2
	assert ans_hist["2"] == 1
	assert ans_hist["0"] == 2

	needs_review_lines = [l for l in reports["needs_review.tsv"].splitlines() if l.strip()]
	assert needs_review_lines[0] == "file\tconfidence\ttypes\treasons"
	assert len(needs_review_lines) == 4
	assert any(l.startswith("d.pg\t0.20\t") for l in needs_review_lines[1:])
	assert any(l.startswith("e.pg\t0.25\t") for l in needs_review_lines[1:])
	assert any(l.startswith("a.pg\t0.50\t") for l in needs_review_lines[1:])

	other_breakdown = _parse_counts_tsv(reports["other_breakdown.tsv"])
	assert other_breakdown["other_applet_like"] == 1

	macro_counts_other = _parse_counts_tsv(reports["macro_counts_other.tsv"])
	assert macro_counts_other["AppletObjects.pl"] == 1

	pgml_blank_hist = _parse_counts_tsv(reports["pgml_blank_marker_hist.tsv"])
	assert pgml_blank_hist["0"] == 4
	assert pgml_blank_hist["1"] == 1

	type_by_widget_lines = [l for l in reports["type_by_widget.tsv"].splitlines() if l.strip()]
	assert type_by_widget_lines[0] == "type\twidget_kind\tcount"
	assert any(l.startswith("other\tnone\t1") for l in type_by_widget_lines[1:])

	coverage = _parse_counts_tsv(reports["coverage.tsv"])
	assert coverage["widgets=some,evaluators=some"] == 3
	assert coverage["widgets=none,evaluators=none"] == 2
