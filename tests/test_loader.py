from arena import load_cases, load_skill


def test_highsignal_skill_loads_existing_cases_unmodified():
    skill = load_skill("highsignal")
    cases = load_cases(skill)

    assert skill.config["cases_path"] == "~/dev/highsignal/tests/cases.jsonl"
    assert len(cases) >= 16
    assert cases[0] == {
        "id": "1",
        "kind": "dirty",
        "context": "social",
        "expect": "throat-clear",
        "draft": "One thing that really helps with agent reliability: you specify an output format.",
    }
    assert cases[11]["id"] == "C1"
    assert cases[11]["kind"] == "clean"
