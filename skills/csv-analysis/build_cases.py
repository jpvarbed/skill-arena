#!/usr/bin/env python3
import csv
import io
import json
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path


CORPUS_VERSION = "csv-analysis-v1"
SEED = 90210
CASE_COUNTS = {"easy": 20, "medium": 20, "hard": 20}
COLUMNS = ["region", "rep", "product", "date", "units", "revenue", "cost", "satisfaction"]
REGIONS = ["North", "South", "East", "West"]
REPS = ["Ari", "Blair", "Chen", "Devon", "Elliot", "Finley"]
PRODUCTS = ["Alpha", "Beta", "Gamma", "Delta"]


def number(value):
    return float(value) if "." in str(value) else int(value)


def rows_for(rng, n):
    start = date(2026, 1, 1)
    rows = []
    for i in range(n):
        units = rng.randint(2, 48)
        revenue = units * rng.randint(11, 37) + rng.randint(0, 9)
        cost = units * rng.randint(5, 19) + rng.randint(0, 7)
        rows.append({
            "region": REGIONS[(i + rng.randint(0, 3)) % len(REGIONS)],
            "rep": REPS[(i * 2 + rng.randint(0, 5)) % len(REPS)],
            "product": PRODUCTS[(i + rng.randint(0, 3)) % len(PRODUCTS)],
            "date": (start + timedelta(days=rng.randint(0, 89))).isoformat(),
            "units": str(units),
            "revenue": str(revenue),
            "cost": str(cost),
            "satisfaction": str(rng.randint(1, 100)),
        })
    return rows


def apply_filters(rows, filters):
    out = rows
    for item in filters or []:
        col, op, value = item["column"], item["op"], item["value"]
        if op == "eq":
            out = [row for row in out if row[col] == value]
        elif op == "gt":
            out = [row for row in out if number(row[col]) > number(value)]
        elif op == "gte":
            out = [row for row in out if number(row[col]) >= number(value)]
        elif op == "lt":
            out = [row for row in out if number(row[col]) < number(value)]
        elif op == "lte":
            out = [row for row in out if number(row[col]) <= number(value)]
        else:
            raise ValueError(f"unknown filter op: {op}")
    return out


def aggregate(values, agg):
    if agg == "sum":
        return sum(values)
    if agg == "mean":
        return sum(values) / len(values)
    if agg == "min":
        return min(values)
    if agg == "max":
        return max(values)
    if agg == "count":
        return len(values)
    raise ValueError(f"unknown aggregate: {agg}")


def format_value(value, query):
    if "round" in query:
        return f"{float(value):.{query['round']}f}"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def execute_query(rows, query):
    op = query["op"]
    filtered = apply_filters(rows, query.get("filters"))
    if op in {"aggregate", "filtered_aggregate", "multi_filter_aggregate"}:
        values = [number(row[query["column"]]) for row in filtered]
        return {"exact": format_value(aggregate(values, query["agg"]), query)}
    if op == "predicate_count":
        return {"exact": str(len(filtered))}
    if op == "groupby_argmax":
        totals = defaultdict(int)
        for row in filtered:
            totals[row[query["group_by"]]] += number(row[query["metric"]])
        return {"exact": max(totals, key=totals.get)}
    if op == "nth_largest":
        values = sorted((number(row[query["column"]]) for row in filtered), reverse=True)
        return {"exact": format_value(values[query["n"] - 1], query)}
    if op == "groupby_dict":
        totals = defaultdict(int)
        for row in filtered:
            totals[row[query["group_by"]]] += number(row[query["metric"]])
        return {"json": dict(sorted(totals.items()))}
    if op == "ratio_percent":
        numerator = aggregate([number(row[query["numerator"]]) for row in filtered], "sum")
        denominator = aggregate([number(row[query["denominator"]]) for row in filtered], "sum")
        return {"exact": format_value((numerator / denominator) * 100, query)}
    if op == "date_bucket_count":
        buckets = defaultdict(int)
        for row in filtered:
            buckets[row[query["date_column"]][:7]] += 1
        return {"json": dict(sorted(buckets.items()))}
    if op == "multi_step":
        grouped = defaultdict(list)
        for row in filtered:
            grouped[row[query["group_by"]]].append(number(row[query["metric"]]))
        means = {key: sum(values) / len(values) for key, values in grouped.items()}
        return {"exact": max(means, key=means.get)}
    raise ValueError(f"unknown query op: {op}")


def filter_phrase(item):
    names = {"eq": "equals", "gt": "is greater than", "gte": "is at least", "lt": "is less than", "lte": "is at most"}
    return f"{item['column']} {names[item['op']]} {item['value']}"


def where_phrase(query):
    filters = query.get("filters") or []
    return "" if not filters else " where " + " and ".join(filter_phrase(item) for item in filters)


def question_for(query):
    op = query["op"]
    if op in {"aggregate", "filtered_aggregate", "multi_filter_aggregate"}:
        question = f"What is the {query['agg']} of {query['column']}{where_phrase(query)}?"
    elif op == "predicate_count":
        question = f"How many rows have {filter_phrase(query['filters'][0])}?"
    elif op == "groupby_argmax":
        question = f"Which {query['group_by']} has the highest total {query['metric']}{where_phrase(query)}?"
    elif op == "nth_largest":
        question = f"What is the {query['n']}th largest {query['column']}{where_phrase(query)}?"
    elif op == "groupby_dict":
        question = f"Return a JSON object mapping each {query['group_by']} to total {query['metric']}{where_phrase(query)}."
    elif op == "ratio_percent":
        question = f"What is total {query['numerator']} as a percentage of total {query['denominator']}{where_phrase(query)}?"
    elif op == "date_bucket_count":
        question = f"Return a JSON object mapping each YYYY-MM month to row count{where_phrase(query)}."
    elif op == "multi_step":
        question = f"Among rows{where_phrase(query)}, which {query['group_by']} has the highest average {query['metric']}?"
    else:
        raise ValueError(f"unknown query op: {op}")
    if "round" in query:
        question += f" Round to exactly {query['round']} decimal places."
    return question


def render_csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().strip()


def render_input(rows, question, expect):
    output = "Output ONLY the JSON object." if "json" in expect else "Output ONLY the answer."
    return f"CSV:\n{render_csv(rows)}\n\nQuestion: {question}\n\n{output}"


def has_unique_answer(rows, query):
    op = query["op"]
    filtered = apply_filters(rows, query.get("filters"))
    if not filtered:
        return False
    if op == "groupby_argmax":
        totals = defaultdict(int)
        for row in filtered:
            totals[row[query["group_by"]]] += number(row[query["metric"]])
        vals = list(totals.values())
        return len(vals) == len(set(vals))
    if op == "nth_largest":
        vals = [number(row[query["column"]]) for row in filtered]
        return len(vals) >= query["n"] and len(vals) == len(set(vals))
    if op == "multi_step":
        grouped = defaultdict(list)
        for row in filtered:
            grouped[row[query["group_by"]]].append(number(row[query["metric"]]))
        vals = [sum(items) / len(items) for items in grouped.values()]
        return len(vals) == len(set(vals))
    if op == "ratio_percent":
        return sum(number(row[query["denominator"]]) for row in filtered) != 0
    return True


def query_for(tier, task_type, rng):
    region = rng.choice(REGIONS)
    product = rng.choice(PRODUCTS)
    numeric = rng.choice(["units", "revenue", "cost", "satisfaction"])
    if task_type == "aggregate":
        return {"op": "aggregate", "agg": rng.choice(["sum", "mean", "min", "max"]), "column": numeric, "round": 2}
    if task_type == "predicate_count":
        column = rng.choice(["region", "product"])
        return {"op": "predicate_count", "filters": [{"column": column, "op": "eq", "value": region if column == "region" else product}]}
    if task_type == "filtered_aggregate":
        return {"op": "filtered_aggregate", "agg": rng.choice(["sum", "mean"]), "column": numeric, "filters": [{"column": "region", "op": "eq", "value": region}], "round": 2}
    if task_type == "groupby_argmax":
        return {"op": "groupby_argmax", "group_by": rng.choice(["region", "product", "rep"]), "metric": rng.choice(["units", "revenue"])}
    if task_type == "nth_largest":
        return {"op": "nth_largest", "column": numeric, "n": rng.choice([2, 3, 4])}
    if task_type == "groupby_dict":
        return {"op": "groupby_dict", "group_by": rng.choice(["region", "product"]), "metric": rng.choice(["units", "revenue", "cost"])}
    if task_type == "multi_filter_aggregate":
        return {"op": "multi_filter_aggregate", "agg": rng.choice(["sum", "mean"]), "column": numeric, "filters": [{"column": "region", "op": "eq", "value": region}, {"column": "units", "op": "gte", "value": "10"}], "round": 2}
    if task_type == "ratio_percent":
        return {"op": "ratio_percent", "numerator": "cost", "denominator": "revenue", "filters": [{"column": "product", "op": "eq", "value": product}], "round": 2}
    if task_type == "date_bucket_count":
        return {"op": "date_bucket_count", "date_column": "date", "filters": [{"column": "region", "op": "eq", "value": region}]}
    if task_type == "multi_step":
        return {"op": "multi_step", "group_by": "rep", "metric": rng.choice(["revenue", "satisfaction"]), "filters": [{"column": "product", "op": "eq", "value": product}]}
    raise ValueError(task_type)


def make_case(case_id, tier, task_type, rng):
    for _ in range(200):
        rows = rows_for(rng, rng.randint(10, 30))
        query = query_for(tier, task_type, rng)
        if not has_unique_answer(rows, query):
            continue
        expect = execute_query(rows, query)
        question = question_for(query)
        return {
            "id": case_id,
            "input": render_input(rows, question, expect),
            "expect": expect,
            "meta": {
                "corpus_version": CORPUS_VERSION,
                "tier": tier,
                "task_type": task_type,
                "columns": COLUMNS,
                "rows": rows,
                "query": query,
            },
        }
    raise RuntimeError(f"could not make unique case: {case_id}")


def build_cases():
    rng = random.Random(SEED)
    tasks = {
        "easy": ["aggregate", "predicate_count"],
        "medium": ["filtered_aggregate", "groupby_argmax", "nth_largest", "groupby_dict"],
        "hard": ["multi_filter_aggregate", "ratio_percent", "date_bucket_count", "multi_step"],
    }
    cases = []
    for tier, count in CASE_COUNTS.items():
        for idx in range(count):
            task_type = tasks[tier][idx % len(tasks[tier])]
            cases.append(make_case(f"csv-{tier}-{idx + 1:02d}", tier, task_type, rng))
    return cases


def write_cases(path):
    path = Path(path)
    cases = build_cases()
    with path.open("w") as f:
        for case in cases:
            f.write(json.dumps(case, sort_keys=True, separators=(",", ":")) + "\n")


def main():
    write_cases(Path(__file__).with_name("cases.jsonl"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
