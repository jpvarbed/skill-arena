from pathlib import Path

from traj.scorers import score_transcript


FIXTURES = Path(__file__).parent / "fixtures"


def test_scores_full_path_transcript():
    assert score_transcript(FIXTURES / "full_path.jsonl") == {
        "ran_test_before_edit": True,
        "verified_after_last_edit": True,
        "files_edited": 1,
        "test_runs": 2,
        "flail_index": 3,
        "stated_hypothesis": True,
        "parse_errors": 0,
    }


def test_scores_malformed_lines_and_write_paths():
    assert score_transcript(FIXTURES / "malformed_and_write.jsonl") == {
        "ran_test_before_edit": False,
        "verified_after_last_edit": False,
        "files_edited": 1,
        "test_runs": 0,
        "flail_index": 1,
        "stated_hypothesis": True,
        "parse_errors": 1,
    }


def test_scores_transcript_with_no_edits():
    assert score_transcript(FIXTURES / "no_edits.jsonl") == {
        "ran_test_before_edit": False,
        "verified_after_last_edit": False,
        "files_edited": 0,
        "test_runs": 1,
        "flail_index": 1,
        "stated_hypothesis": False,
        "parse_errors": 0,
    }
