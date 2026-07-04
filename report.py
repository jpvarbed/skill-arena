#!/usr/bin/env python3
import argparse
import html
import json
import sys
from pathlib import Path


def print_comparison(results, stream=None):
    stream = stream or sys.stdout
    for skill_name, skill_result in results.get("skills", {}).items():
        cells = skill_result.get("cells", [])
        backends = sorted({cell["backend"] for cell in cells})
        variants = sorted({cell["prompt_variant"] for cell in cells})
        rows = []
        for variant in variants:
            row = [variant]
            for backend in backends:
                cell = next((c for c in cells if c["backend"] == backend and c["prompt_variant"] == variant), None)
                row.append(format_cell(cell) if cell else "-")
            rows.append(row)
        _print_table(skill_name, ["variant", *backends], rows, stream)


def write_leaderboard(results, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(results))
    return path


def format_cell(cell):
    if cell is None:
        return "-"
    if cell.get("errors"):
        return f"ERROR {cell['errors']}/{cell['n']}"
    if cell.get("pass_rate") is None:
        return "n/a"
    return f"{cell['passes']}/{cell['n']} ({cell['pass_rate']:.0%})"


def _print_table(title, headers, rows, stream):
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(str(value))) for width, value in zip(widths, row)]
    print(f"\n{title}", file=stream)
    print("  ".join(header.ljust(width) for header, width in zip(headers, widths)), file=stream)
    print("  ".join("-" * width for width in widths), file=stream)
    for row in rows:
        print("  ".join(str(value).ljust(width) for value, width in zip(row, widths)), file=stream)


def render_html(results):
    generated = html.escape(str(results.get("generated_at", "")))
    dry_run = "yes" if results.get("dry_run") else "no"
    sections = "\n".join(render_skill_section(name, result) for name, result in results.get("skills", {}).items())
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skill Arena Leaderboard</title>
<style>
:root {{
  color-scheme: light;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #f7f7f4;
  color: #1c1d1f;
}}
body {{ margin: 0; padding: 32px; }}
main {{ max-width: 1160px; margin: 0 auto; }}
h1 {{ font-size: 28px; margin: 0 0 6px; letter-spacing: 0; }}
h2 {{ font-size: 20px; margin: 30px 0 12px; letter-spacing: 0; }}
.meta {{ color: #5f6368; margin: 0 0 24px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d8d9d4; }}
th, td {{ border: 1px solid #d8d9d4; padding: 10px 12px; text-align: left; vertical-align: top; }}
th {{ background: #eceee8; font-size: 13px; text-transform: uppercase; color: #3b3d40; }}
.cell-pass {{ background: #e4f3e8; }}
.cell-warn {{ background: #fff2cf; }}
.cell-error {{ background: #f8dddd; }}
.rate {{ font-weight: 700; display: block; }}
.detail {{ color: #5f6368; font-size: 13px; }}
details {{ margin-top: 8px; }}
summary {{ cursor: pointer; color: #2b5f9e; }}
ul {{ margin: 8px 0 0 18px; padding: 0; }}
li {{ margin: 4px 0; }}
</style>
</head>
<body>
<main>
<h1>Skill Arena Leaderboard</h1>
<p class="meta">Generated {generated} · dry-run: {dry_run}</p>
{sections}
</main>
</body>
</html>
"""


def render_skill_section(skill_name, skill_result):
    cells = skill_result.get("cells", [])
    backends = sorted({cell["backend"] for cell in cells})
    variants = sorted({cell["prompt_variant"] for cell in cells})
    rows = []
    for variant in variants:
        tds = [f"<td>{html.escape(variant)}</td>"]
        for backend in backends:
            cell = next((c for c in cells if c["backend"] == backend and c["prompt_variant"] == variant), None)
            tds.append(render_cell(cell))
        rows.append("<tr>" + "".join(tds) + "</tr>")
    header = "".join(f"<th>{html.escape(value)}</th>" for value in ["variant", *backends])
    body = "\n".join(rows)
    return f"""<section>
<h2>{html.escape(skill_name)}</h2>
<table>
<thead><tr>{header}</tr></thead>
<tbody>
{body}
</tbody>
</table>
</section>"""


def render_cell(cell):
    if cell is None:
        return "<td>-</td>"
    css = "cell-pass"
    if cell.get("errors"):
        css = "cell-error"
    elif cell.get("pass_rate") is not None and cell["pass_rate"] < 1:
        css = "cell-warn"
    rate = html.escape(format_cell(cell))
    details = "\n".join(
        f"<li>{html.escape(str(case['id']))}: "
        f"{'PASS' if case['pass'] else 'FAIL'}"
        f"{' ERROR' if case.get('error') else ''} - {html.escape(str(case['detail']))}</li>"
        for case in cell.get("cases", [])
    )
    return (
        f'<td class="{css}"><span class="rate">{rate}</span>'
        f'<span class="detail">latency {cell.get("latency_s", 0):.3f}s · cost ${cell.get("cost_est", 0):.4f}</span>'
        f"<details><summary>cases</summary><ul>{details}</ul></details></td>"
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="out/results.json")
    parser.add_argument("--html", default="out/leaderboard.html")
    args = parser.parse_args(argv)

    results = json.loads(Path(args.results).read_text())
    print_comparison(results)
    write_leaderboard(results, args.html)
    print(f"\nwrote {args.html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
