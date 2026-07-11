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

    if "checks" in rules:
        if set(rules) != {"checks"}:
            raise ValueError("cannot mix expect.checks with legacy deterministic rules")
        checks = [score_deterministic_check(check, model_output) for check in rules["checks"]]
        failures = [check["id"] for check in checks if not check["pass"]]
        return {
            "pass": bool(checks) and not failures,
            "detail": "all checks passed" if checks and not failures else f"failed checks: {', '.join(failures) or 'none declared'}",
            "checks": checks,
        }

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


def score_deterministic_check(check, model_output):
    check_id = check.get("id") or check.get("type") or "check"
    check_type = check.get("type")
    text = str(model_output)
    ignore_case = check.get("ignore_case", True)
    compared = text.lower() if ignore_case else text
    if check_type in {"contains", "not_contains"}:
        needle = str(check["text"])
        needle = needle.lower() if ignore_case else needle
        matched = needle in compared
        passed = matched if check_type == "contains" else not matched
    elif check_type in {"regex", "not_regex"}:
        flags = re.I if ignore_case else 0
        matched = re.search(check["pattern"], text, flags | re.S) is not None
        passed = matched if check_type == "regex" else not matched
    elif check_type == "max_chars":
        passed = len(text) <= int(check["value"])
    elif check_type == "json_fields":
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = None
        passed = isinstance(value, dict) and all(field in value for field in check["fields"])
    else:
        raise ValueError(f"unknown deterministic check type: {check_type!r}")
    return {"id": check_id, "type": check_type, "pass": passed}


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
