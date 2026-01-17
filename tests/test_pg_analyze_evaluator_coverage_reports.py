# Local modules
import pg_analyze.aggregate


def test_evaluator_coverage_reports_and_restricted_macro_counts() -> None:
	agg = pg_analyze.aggregate.Aggregator(needs_review_limit=200)

	agg.add_record({
		"file": "a.pg",
		"types": ["unknown_pgml_blank"],
		"confidence": 0.25,
		"widget_kinds": ["pgml_blank"],
		"evaluator_kinds": [],
		"loadMacros": ["PGML.pl", "PGstandard.pl"],
		"pgml_blank_marker_count": 2,
		"ans_token_count": 0,
		"has_ans_token": 0,
		"has_cmp_token": 0,
		"has_answer_ctor": 0,
		"has_named_ans_rule_token": 0,
		"has_named_ans_token": 0,
		"has_ans_num_to_name": 0,
		"has_install_problem_grader": 0,
	})
	agg.add_record({
		"file": "b.pg",
		"types": ["numeric_entry"],
		"confidence": 0.50,
		"widget_kinds": ["blank"],
		"evaluator_kinds": [],
		"loadMacros": ["PGstandard.pl", "MathObjects.pl"],
		"pgml_blank_marker_count": 0,
		"ans_token_count": 0,
		"has_ans_token": 0,
		"has_cmp_token": 1,
		"has_answer_ctor": 1,
		"has_named_ans_rule_token": 0,
		"has_named_ans_token": 0,
		"has_ans_num_to_name": 0,
		"has_install_problem_grader": 0,
	})

	reports = agg.render_reports()

	eval_cov = reports["evaluator_coverage_reasons.tsv"]
	assert "none_pgml_blank_only\t1" in eval_cov
	assert "none_but_cmp_present\t1" in eval_cov

	m_unknown = reports["macro_counts_unknown_pgml_blank.tsv"]
	assert "PGML.pl\t1" in m_unknown

	m_num = reports["macro_counts_eval_none_numeric_entry.tsv"]
	assert "MathObjects.pl\t1" in m_num

	samples = reports["samples_unknown_pgml_blank.tsv"].splitlines()
	assert samples[0].startswith("file\tpgml_blank_markers\t")
	assert any(l.startswith("a.pg\t2\t0\t0\t") for l in samples[1:])
