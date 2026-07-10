#!/usr/bin/env python3
import argparse
import difflib
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


def write_forge_receipt(results, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_forge_receipt(results))
    return path


def render_forge_receipt(results):
    from forge import contestant_text, fixed_cases, format_pct, format_pp, original_text, summarize_results

    summary = results.get("summary") or summarize_results(results)
    winner = summary.get("winner")
    target = summary.get("target")
    target_row = next((row for row in summary.get("models", []) if row["backend"] == target), None)
    winner_text = contestant_text(results, winner) if winner else ""
    diff = render_skill_diff(original_text(results), winner_text, winner or "winner")
    fixed = fixed_cases(results, winner, target) if winner else []
    shown_fixed = fixed[:3] if len(fixed) > 3 else fixed
    narrative = forge_narrative(summary, target_row, len([c for c in results.get("contestants", []) if c.get("kind") == "variant"]))

    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(_pretty_model(row['backend']))}</td>"
        f"<td>{html.escape(format_pct(row['original_score']))}</td>"
        f"<td>{html.escape(row['best_variant'] or '-')} {html.escape(format_pct(row['best_variant_score']))}</td>"
        f"<td>{html.escape(format_pp(row['lift']))}</td>"
        f"<td>{html.escape(winner or '-')} {html.escape(format_pct(row['winner_score']))}</td>"
        "</tr>"
        for row in summary.get("models", [])
    )
    fixed_html = render_fixed_cases(shown_fixed, len(fixed))
    title = "Skill forge receipt" if summary.get("success") else "No improvement found"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --ink:#101114; --paper:#f7f3ea; --muted:#6d675e; --line:#d8d0c2; --good:#13795b; --bad:#9f2f2f; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:40px 20px 64px; }}
h1 {{ margin:0 0 12px; font-size:42px; line-height:1.05; }}
h2 {{ margin:34px 0 12px; font-size:22px; }}
p {{ font-size:17px; line-height:1.55; max-width:72ch; }}
table {{ width:100%; border-collapse:collapse; background:#fffaf0; border:1px solid var(--line); }}
th, td {{ text-align:left; padding:11px 12px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
pre {{ overflow:auto; background:#181a1f; color:#f4efe4; padding:16px; border-radius:8px; line-height:1.45; }}
.meta {{ color:var(--muted); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px; }}
.ok {{ color:var(--good); }}
.bad {{ color:var(--bad); }}
.case {{ background:#fffaf0; border:1px solid var(--line); padding:14px; margin:10px 0; border-radius:8px; }}
</style>
</head>
<body>
<main>
<p class="meta">skill-arena forge | target {html.escape(_pretty_model(target or ''))} | winner {html.escape(winner or 'none')}</p>
<h1>{html.escape(title)}</h1>
<p>{html.escape(narrative)}</p>
<h2>Before / after</h2>
<table>
<thead><tr><th>Model</th><th>Original</th><th>Best variant</th><th>Lift</th><th>Winner</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<h2>Winning SKILL.md diff</h2>
<pre>{html.escape(diff)}</pre>
<h2>Cases the winner fixed</h2>
{fixed_html}
</main>
</body>
</html>
"""


def forge_narrative(summary, target_row, variant_count):
    if summary.get("success") and target_row:
        before = target_row["original_score"]
        after = target_row["best_variant_score"]
        lift = target_row["lift"] or 0
        return (
            "A generated variant beat the original on the target model. "
            f"{_pretty_model(summary['target'])} moved from {before * 100:.1f}% to {after * 100:.1f}%, "
            f"a {abs(lift) * 100:.1f} point lift."
        )
    return (
        "No improvement found. "
        f"This run tested {variant_count} generated variants against the same cases, "
        "and none beat the original on the target model. The table and diff make the failed run auditable."
    )


def render_skill_diff(before, after, winner):
    lines = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile="original/SKILL.md",
        tofile=f"{winner}/SKILL.md",
        lineterm="",
    )
    diff = "\n".join(lines)
    return diff or "No textual diff."


def render_fixed_cases(cases, total):
    if not cases:
        return "<p>No target-model fixes for the selected winner.</p>"
    items = []
    for case in cases:
        items.append(
            '<div class="case">'
            f'<p class="meta">{html.escape(str(case.get("id", "")))}</p>'
            f'<p>{html.escape(case.get("input", ""))}</p>'
            "</div>"
        )
    note = "" if total <= len(cases) else f"<p class=\"meta\">Showing {len(cases)} of {total} fixed cases.</p>"
    return note + "\n".join(items)


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


REPO_URL = "https://github.com/jpvarbed/skill-arena"


def _skill_cells_by_model(skill_result):
    """One representative cell per model (best variant), keyed by backend name."""
    best = {}
    for cell in skill_result.get("cells", []):
        b = cell["backend"]
        rate = None if cell.get("errors") else cell.get("pass_rate")
        prev = best.get(b)
        if prev is None or (rate is not None and (prev.get("_rate") is None or rate > prev["_rate"])):
            cell = dict(cell)
            cell["_rate"] = rate
            best[b] = cell
    return best


def render_html(results):
    skills = results.get("skills", {})
    # models = union of all backends, ordered by overall average (best first)
    models = []
    for r in skills.values():
        for c in r.get("cells", []):
            if c["backend"] not in models:
                models.append(c["backend"])
    per_skill = {name: _skill_cells_by_model(r) for name, r in skills.items()}

    def model_avg(m):
        rates = [per_skill[s][m]["_rate"] for s in skills if m in per_skill[s] and per_skill[s][m]["_rate"] is not None]
        return sum(rates) / len(rates) if rates else None

    models_ranked = sorted(models, key=lambda m: (model_avg(m) is not None, model_avg(m) or -1), reverse=True)
    champ = models_ranked[0] if models_ranked and model_avg(models_ranked[0]) is not None else None
    n_cases = sum(r.get("cells", [{}])[0].get("n", 0) for r in skills.values() if r.get("cells"))

    rows = "\n".join(render_skill_row(name, per_skill[name], models_ranked) for name in skills)
    foot = "".join(
        f'<td class="mcol"><span class="avg">{_pct(model_avg(m))}</span></td>' for m in models_ranked
    )
    head = "".join(
        f'<th class="mcol">{_crown(m, champ)}{html.escape(_pretty_model(m))}</th>' for m in models_ranked
    )
    champ_line = (
        f'<span class="champ">{html.escape(_pretty_model(champ))}</span> leads across {len(skills)} skills'
        if champ else "no scored results yet"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skill Arena — which model runs your skill best?</title>
<style>
:root {{
  --ink:#0d0f16; --panel:#141824; --line:#242a3a; --line2:#2f3648;
  --fg:#e9e7df; --dim:#8b93a7; --amber:#ffb020; --amber-dim:#5a4213;
  --teal:#5ad1b4; --red:#ff6b6b;
  color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
body {{
  margin:0; background:var(--ink); color:var(--fg);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing:antialiased;
}}
.mono {{ font-family: ui-monospace, "SF Mono", "SFMono-Regular", Menlo, monospace; font-variant-numeric: tabular-nums; }}
main {{ max-width: 1080px; margin: 0 auto; padding: 40px 22px 72px; }}
.eyebrow {{ font-family: ui-monospace, Menlo, monospace; font-size:12px; letter-spacing:.28em; text-transform:uppercase; color:var(--amber); margin:0 0 18px; }}
h1 {{ font-size: clamp(34px, 6vw, 60px); line-height:1.02; letter-spacing:-.02em; font-weight:800; margin:0 0 18px; max-width:14ch; }}
.sub {{ font-size:17px; line-height:1.55; color:var(--dim); max-width:60ch; margin:0 0 26px; }}
.sub b {{ color:var(--fg); font-weight:600; }}
.bar {{ display:flex; flex-wrap:wrap; gap:10px 26px; align-items:baseline; margin:0 0 40px; padding:16px 20px; background:var(--panel); border:1px solid var(--line); border-radius:14px; }}
.bar .k {{ font-family:ui-monospace,Menlo,monospace; font-size:12px; letter-spacing:.12em; text-transform:uppercase; color:var(--dim); }}
.bar .v {{ font-family:ui-monospace,Menlo,monospace; font-size:15px; color:var(--fg); margin-left:8px; }}
.champ {{ color:var(--amber); font-weight:700; }}
.tablewrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:14px; background:var(--panel); }}
table {{ width:100%; border-collapse:collapse; min-width:640px; }}
th, td {{ padding:0; text-align:left; }}
thead th {{ position:sticky; top:0; background:var(--panel); border-bottom:1px solid var(--line2); padding:14px 14px; font-size:12px; font-weight:600; letter-spacing:.02em; color:var(--dim); white-space:nowrap; vertical-align:bottom; }}
th.skillcol {{ min-width:170px; }}
th.mcol, td.mcol {{ text-align:right; }}
.crown {{ color:var(--amber); margin-right:6px; }}
tbody td {{ border-bottom:1px solid var(--line); padding:16px 14px; vertical-align:middle; }}
tbody tr:last-child td {{ border-bottom:none; }}
.skcell {{ display:flex; flex-direction:column; gap:3px; }}
.skname {{ font-weight:700; font-size:16px; }}
.skmeta {{ font-family:ui-monospace,Menlo,monospace; font-size:12px; color:var(--dim); }}
.cell {{ position:relative; text-align:right; }}
.cell .score {{ font-family:ui-monospace,Menlo,monospace; font-size:18px; font-weight:600; }}
.cell .frac {{ font-family:ui-monospace,Menlo,monospace; font-size:12px; color:var(--dim); display:block; margin-top:1px; }}
.track {{ height:5px; border-radius:3px; background:var(--line2); margin-top:8px; overflow:hidden; }}
.fill {{ height:100%; background:var(--teal); border-radius:3px; }}
.lead .score {{ color:var(--amber); }}
.lead .fill {{ background:var(--amber); }}
.lead {{ background:linear-gradient(0deg,var(--amber-dim),transparent); }}
.err .score {{ color:var(--red); font-size:13px; }}
.err .fill {{ background:var(--red); }}
tfoot td {{ border-top:1px solid var(--line2); padding:14px; }}
tfoot .lbl {{ font-family:ui-monospace,Menlo,monospace; font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--dim); }}
tfoot .avg {{ font-family:ui-monospace,Menlo,monospace; font-size:15px; font-weight:600; color:var(--fg); }}
.foot {{ margin-top:34px; display:flex; flex-wrap:wrap; gap:14px 28px; align-items:center; justify-content:space-between; }}
.method {{ color:var(--dim); font-size:14px; line-height:1.5; max-width:56ch; }}
.cta {{ display:inline-flex; align-items:center; gap:8px; background:var(--amber); color:#1a1205; text-decoration:none; font-weight:700; padding:12px 18px; border-radius:10px; font-size:15px; }}
.cta:focus-visible, a:focus-visible {{ outline:2px solid var(--amber); outline-offset:2px; }}
a {{ color:var(--teal); }}
@media (max-width:560px) {{ main {{ padding:28px 16px 56px; }} .foot {{ flex-direction:column; align-items:flex-start; }} }}
</style>
</head>
<body>
<main>
<p class="eyebrow">Open skill benchmark</p>
<h1>Which model runs your skill best?</h1>
<p class="sub">Every skill is a set of graded cases. Every model runs them cold. <b>One honest number per cell</b> — a failed call scores as an error, never a fake pass. Point it at your own skill repo and get the same table.</p>
<div class="bar">
  <div><span class="k">Leader</span><span class="v">{champ_line}</span></div>
  <div><span class="k">Skills</span><span class="v mono">{len(skills)}</span></div>
  <div><span class="k">Models</span><span class="v mono">{len(models_ranked)}</span></div>
  <div><span class="k">Graded cases</span><span class="v mono">{n_cases}</span></div>
</div>
<div class="tablewrap">
<table>
<thead><tr><th class="skillcol">Skill</th>{head}</tr></thead>
<tbody>
{rows}
</tbody>
<tfoot><tr><td class="lbl">Avg across skills</td>{foot}</tr></tfoot>
</table>
</div>
<div class="foot">
  <p class="method">Scored deterministically or by an independent judge, whichever the skill declares. Model judges vary run to run; a differing count is variance, not a bug. Cases live in git — the number is reproducible.</p>
  <a class="cta" href="{REPO_URL}">Run it on your skills →</a>
</div>
</main>
</body>
</html>
"""


def render_skill_row(skill_name, cells_by_model, models_ranked):
    present = [cells_by_model[m]["_rate"] for m in models_ranked if m in cells_by_model and cells_by_model[m]["_rate"] is not None]
    lead_rate = max(present) if present else None
    n = next((cells_by_model[m].get("n", 0) for m in models_ranked if m in cells_by_model), 0)
    tds = [
        f'<td class="skillcol"><div class="skcell"><span class="skname">{html.escape(skill_name)}</span>'
        f'<span class="skmeta">{n} cases</span></div></td>'
    ]
    for m in models_ranked:
        cell = cells_by_model.get(m)
        tds.append(render_matrix_cell(cell, lead_rate))
    return "<tr>" + "".join(tds) + "</tr>"


def render_matrix_cell(cell, lead_rate):
    if cell is None:
        return '<td class="mcol cell"><span class="score" style="color:var(--dim)">—</span></td>'
    if cell.get("errors") or cell.get("_rate") is None:
        return (
            '<td class="mcol cell err"><span class="score">ERR</span>'
            f'<span class="frac">{cell.get("errors", cell.get("n", 0))}/{cell.get("n", 0)}</span>'
            '<div class="track"><div class="fill" style="width:100%"></div></div></td>'
        )
    rate = cell["_rate"]
    is_lead = lead_rate is not None and rate >= lead_rate and rate > 0
    cls = "mcol cell lead" if is_lead else "mcol cell"
    pct = f"{rate*100:.0f}%"
    return (
        f'<td class="{cls}"><span class="score">{pct}</span>'
        f'<span class="frac">{cell.get("passes", 0)}/{cell.get("n", 0)}</span>'
        f'<div class="track"><div class="fill" style="width:{rate*100:.0f}%"></div></div></td>'
    )


def _pct(x):
    return f"{x*100:.0f}%" if x is not None else "—"


def _crown(m, champ):
    return '<span class="crown">♦</span>' if m == champ else ""


_MODEL_LABELS = {
    "opus": "Opus 4.8", "sonnet": "Sonnet 5", "haiku": "Haiku 4.5",
    "openai": "GPT-5.5", "gemini-pro": "Gemini 2.5 Pro", "gemini-flash": "Gemini 2.5 Flash",
    "anthropic": "Claude", "google": "Gemini", "codex": "GPT-5.5 (codex)",
}


def _pretty_model(m):
    return _MODEL_LABELS.get(m, m)


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
