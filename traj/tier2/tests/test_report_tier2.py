from traj.tier2 import report_tier2


def test_report_conclusion_manifest_and_metrics_definitions():
    manifest = {
        "instances": [
            {"instance_id": "repo__case-1", "repo": "repo/name", "base_commit": "a" * 40, "image_digest": "sha256:one"}
        ],
        "skipped": [],
    }
    rows = [
        {
            "instance_id": "repo__case-1",
            "arm": "baseline",
            "trial": 1,
            "resolved": True,
            "fail_to_pass_passed": 2,
            "pass_to_pass_regressions": 0,
            "timeout": False,
            "duration_s": 10.0,
            "metrics": {"test_runs": 1, "files_edited": 2, "flail_index": 3, "stated_hypothesis": True},
            "trace_path": "trace.jsonl",
            "box_name": "t2-case",
        }
    ]

    receipt = report_tier2.render_receipt(rows, manifest)

    assert receipt.startswith("# Tier 2 Trajectory Benchmark Receipt\n\n## Conclusion")
    assert "| baseline | 1/1 | 100.0% | 0 |" in receipt
    assert "outside the target difficulty band" in receipt
    assert "## Metrics Definitions" in receipt
    assert "repo__case-1" in receipt
