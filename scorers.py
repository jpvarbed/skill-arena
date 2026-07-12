import json
import re

from backends import is_error_sentinel


def parse_array(text):
    # find the last bracketed array that parses as a list of strings
    for m in reversed(re.findall(r"\[[^\[\]]*\]", text, re.S)):
        try:
            v = json.loads(m)
            if isinstance(v, list):
                return {str(x).strip().lower() for x in v}
        except Exception:
            pass
    return None  # could not parse -> treat as error


def score_case(case, model_output, scorer_config=None, judge_call=None):
    scorer_config = scorer_config or {}
    scorer_type = scorer_config.get("type") or case.get("scorer") or "deterministic"
    if isinstance(scorer_type, dict):
        scorer_config = {**scorer_type, **scorer_config}
        scorer_type = scorer_config.get("type")
    if scorer_type == "expect_set":
        return score_expect_set(case, model_output)
    if scorer_type == "deterministic":
        return score_deterministic(case, model_output)
    if scorer_type == "compression_fidelity":
        return score_compression_fidelity(case, model_output, scorer_config)
    if scorer_type == "brief_lint":
        return score_brief_lint(case, model_output)
    if scorer_type == "llm_judge":
        return score_llm_judge(case, model_output, scorer_config, judge_call=judge_call)
    if scorer_type == "arize":
        return score_arize(case, model_output)
    raise ValueError(f"unknown scorer type: {scorer_type}")


def score_expect_set(case, model_output):
    if is_error_sentinel(model_output):
        return {"pass": False, "detail": f"backend error: {model_output}"}
    got = parse_array(model_output)
    if got is None:
        return {"pass": False, "detail": "could not parse JSON array", "error": True}
    if case["kind"] == "dirty":
        exp = set(case["expect"]) if isinstance(case["expect"], list) else {case["expect"]}
        ok = bool(exp & got)  # any acceptable tell counts
        detail = f"expected={sorted(exp)} got={sorted(got)}"
    else:
        ok = len(got) == 0
        detail = "clean" if ok else f"false-positive got={sorted(got)}"
    return {"pass": ok, "detail": detail}


def score_deterministic(case, model_output):
    if is_error_sentinel(model_output):
        return {"pass": False, "detail": f"backend error: {model_output}"}
    rules = case.get("expect")
    if not isinstance(rules, dict):
        ok = str(model_output).strip() == str(rules).strip()
        return {"pass": ok, "detail": "exact match" if ok else f"expected exact {rules!r}"}

    checks = []
    if "json" in rules:
        actual = parse_json_value(model_output)
        expected = rules["json"]
        ok = actual == expected
        checks.append((ok, "JSON matched" if ok else f"expected JSON {expected!r} got {actual!r}"))
    if "exact" in rules:
        expected = str(rules["exact"]).strip()
        actual = str(model_output).strip()
        ok = actual == expected
        checks.append((ok, "exact matched" if ok else f"expected exact {expected!r} got {actual!r}"))
    if "regex" in rules:
        ok = re.search(str(rules["regex"]), str(model_output), re.S) is not None
        checks.append((ok, "regex matched" if ok else f"regex did not match {rules['regex']!r}"))
    if "keyword" in rules:
        expected = str(rules["keyword"])
        ok = expected in str(model_output)
        checks.append((ok, "keyword matched" if ok else f"missing keyword {expected!r}"))
    if "keywords" in rules:
        missing = [word for word in rules["keywords"] if str(word) not in str(model_output)]
        ok = not missing
        checks.append((ok, "keywords matched" if ok else f"missing keywords {missing!r}"))
    if not checks:
        return {"pass": False, "detail": "no deterministic rules declared"}
    ok = all(passed for passed, _ in checks)
    return {"pass": ok, "detail": "; ".join(detail for _, detail in checks)}


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", re.UNICODE)


def deterministic_tokens(text):
    """Split into word-like runs plus punctuation tokens; stable across platforms."""
    return TOKEN_RE.findall(str(text))


def score_compression_fidelity(case, model_output, scorer_config=None):
    if is_error_sentinel(model_output):
        return {"pass": False, "detail": f"backend error: {model_output}"}
    scorer_config = scorer_config or {}
    threshold = float(scorer_config.get("fidelity_threshold", 0.8))
    source = str(case.get("input") or case.get("draft") or "")
    source_tokens = deterministic_tokens(source)
    output_tokens = deterministic_tokens(model_output)
    if not source_tokens:
        return {"pass": False, "detail": "empty source text", "score": 0.0}

    probes = case.get("probes")
    if probes is None and isinstance(case.get("expect"), dict):
        probes = case["expect"].get("probes")
    if not probes:
        return {"pass": False, "detail": "compression_fidelity requires probes", "score": 0.0}

    matched = []
    missing = []
    for probe in probes:
        pattern = probe.get("answer_pattern")
        if pattern and re.search(pattern, str(model_output), re.I | re.S):
            matched.append(probe.get("question", pattern))
        else:
            missing.append(probe.get("question", pattern))
    fidelity = len(matched) / len(probes)
    compression = max(0.0, 1.0 - (len(output_tokens) / len(source_tokens)))
    ok = fidelity >= threshold
    return {
        "pass": ok,
        "detail": (
            f"compression={compression:.1%}; fidelity={len(matched)}/{len(probes)}"
            + ("" if ok else f"; missing={missing!r}")
        ),
        "score": compression if ok else 0.0,
        "compression": compression,
        "fidelity": fidelity,
    }


SECTION_RE = re.compile(r"^(GOAL|CONTEXT|EFFORT|VERIFY|RESOLVED(?: \(do not reopen\))?|RUBRIC(?: \(binary\))?):", re.M)


def lint_goal_brief(text):
    text = str(text).replace("\r\n", "\n")
    lines = text.splitlines()
    sections = _brief_sections(lines)
    checks = {
        "goal_single_line": _has_single_line_goal(sections),
        "context_access_list": _has_context_access_list(sections),
        "effort_line": _has_effort_line(sections),
        "verify_number_to_beat": _has_verify_number_to_beat(sections),
        "rubric_binary_checkboxes": _has_binary_rubric(sections),
        "resolved_present": any(key.startswith("RESOLVED") for key in sections),
    }
    violations = [name for name, passed in checks.items() if not passed]
    return {"pass": not violations, "checks": checks, "violations": violations}


def score_brief_lint(case, model_output):
    if is_error_sentinel(model_output):
        return {"pass": False, "detail": f"backend error: {model_output}"}
    result = lint_goal_brief(model_output)
    expected = case.get("expect")
    if isinstance(expected, dict) and "passes_lint" in expected:
        ok = result["pass"] is bool(expected["passes_lint"])
        return {
            "pass": ok,
            "detail": "matched hand label" if ok else f"expected passes_lint={expected['passes_lint']} got {result['pass']}",
        }
    return {
        "pass": result["pass"],
        "detail": "brief lint passed" if result["pass"] else f"brief lint failed: {result['violations']}",
        "score": 1.0 if result["pass"] else 0.0,
    }


def _brief_sections(lines):
    sections = {}
    current = None
    for line in lines:
        match = SECTION_RE.match(line)
        if match:
            current = match.group(1)
            sections.setdefault(current, []).append(line)
        elif current:
            sections[current].append(line)
    return sections


def _section_text(sections, prefix):
    for key, value in sections.items():
        if key.startswith(prefix):
            return "\n".join(value)
    return ""


def _has_single_line_goal(sections):
    goal = sections.get("GOAL")
    if not goal or len([line for line in goal if line.strip()]) != 1:
        return False
    return bool(re.match(r"^GOAL:\s+\S", goal[0]))


def _has_context_access_list(sections):
    text = _section_text(sections, "CONTEXT")
    if not text:
        return False
    has_list_shape = any(marker in text for marker in ("tools:", "refs:", "output:", "fixtures:", ";", "\n- "))
    access_terms = sum(1 for term in ("tool", "cli", "repo", "path", "fixture", "ref", "auth", "output") if re.search(term, text, re.I))
    return has_list_shape and access_terms >= 2


def _has_effort_line(sections):
    effort = sections.get("EFFORT")
    return bool(effort and len([line for line in effort if line.strip()]) == 1 and re.match(r"^EFFORT:\s+(high|medium|low)\b", effort[0], re.I))


def _has_verify_number_to_beat(sections):
    text = _section_text(sections, "VERIFY")
    if not text:
        return False
    return bool(re.search(r"(beat|baseline|target|break|>=|at least|under|below)[^.\n]*\d", text, re.I))


def _has_binary_rubric(sections):
    text = _section_text(sections, "RUBRIC")
    if not text:
        return False
    items = [line.strip() for line in text.splitlines() if line.strip().startswith("-")]
    if not items:
        return False
    return all(re.match(r"^-\s+\[\s\]\s+\S", item) for item in items)


def score_llm_judge(case, model_output, scorer_config, judge_call=None):
    if is_error_sentinel(model_output):
        return {"pass": False, "detail": f"backend error: {model_output}"}
    rubric = case.get("expect", {}).get("rubric") if isinstance(case.get("expect"), dict) else case.get("rubric")
    if not rubric:
        return {"pass": False, "detail": "llm_judge requires an expect.rubric or rubric field"}

    prompt = (
        "Judge whether MODEL_OUTPUT satisfies the RUBRIC.\n"
        "Return ONLY JSON like {\"pass\": true, \"detail\": \"short reason\"}.\n\n"
        f"RUBRIC:\n{rubric}\n\n"
        f"CASE INPUT:\n{case.get('input') or case.get('draft') or ''}\n\n"
        f"MODEL_OUTPUT:\n{model_output}\n"
    )
    model = scorer_config.get("model")
    if judge_call is None:
        from backends import call_backend

        backend = scorer_config.get("backend", "openai")
        raw = call_backend(backend, prompt, model)
    else:
        raw = judge_call(prompt, model)
    if is_error_sentinel(raw):
        return {"pass": False, "detail": f"judge backend error: {raw}"}
    verdict = parse_json_value(raw)
    if not isinstance(verdict, dict) or "pass" not in verdict:
        return {"pass": False, "detail": "judge did not return a JSON verdict"}
    return {"pass": bool(verdict["pass"]), "detail": str(verdict.get("detail", ""))}


def score_arize(case, model_output):
    raise NotImplementedError(
        "Arize scorer is not wired in this local arena yet; add the Arize evaluator adapter before using scorer type 'arize'."
    )


def parse_json_value(text):
    text = str(text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[idx:])
            return value
        except Exception:
            continue
    return None
