# Local modules
import pg_analyze.aggregate


def test_duplicate_cluster_outputs_and_asset_signal_counts() -> None:
	agg = pg_analyze.aggregate.Aggregator(needs_review_limit=200)

	agg.add_record({
		"file": "a.pg",
		"file_rel": "OpenProblemLibrary/A/a.pg",
		"sha256": "h1",
		"sha256_ws": "hw1",
		"asset_signals": ["image_call", "javascript_token"],
	})
	agg.add_record({
		"file": "b.pg",
		"file_rel": "OpenProblemLibrary/A/b.pg",
		"sha256": "h1",
		"sha256_ws": "hw1",
		"asset_signals": ["image_call"],
	})
	agg.add_record({
		"file": "c.pg",
		"file_rel": "Contrib/C/c.pg",
		"sha256": "h2",
		"sha256_ws": "hw2",
		"asset_signals": [],
	})

	reports = agg.render_reports()

	hists = reports["histograms_all.tsv"]
	assert "sha256_dup_group_size\t2\t1" in hists
	assert "sha256_ws_dup_group_size\t2\t1" in hists

	dups = reports["duplicate_clusters_top.tsv"].splitlines()
	assert dups[0] == "hash_type\tgroup_size\thash\trepresentative_file"
	assert any(l.startswith("sha256\t2\th1\tOpenProblemLibrary/A/a.pg") for l in dups[1:])
	assert any(l.startswith("sha256_ws\t2\thw1\tOpenProblemLibrary/A/a.pg") for l in dups[1:])

	counts_all = reports["counts_all.tsv"]
	assert "asset_signal_file\tall\timage_call\t2" in counts_all
	assert "asset_signal_file\tall\tjavascript_token\t1" in counts_all

