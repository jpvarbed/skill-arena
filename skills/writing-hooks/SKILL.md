---
name: writing-hooks
description: 'Personal compilation of hook and social-post writing gotchas (X/LinkedIn) in Jason''s voice. Trigger on "write me a hook", "clean up this tweet", "draft a thread", "does this sound like me", or any time a tweet/thread/hook is being written or edited. Use alongside avoid-ai-writing and the motion hook skills (hook-writing, hook-tactics, hook-voice-patterns) — this catches the tells those miss and enforces a plain, finding-first voice. NOT for long-form articles (use edit-article / writing-shape) or de-AI-ing general prose (avoid-ai-writing alone covers that).'
---

# writing-hooks — gotchas for hooks, in my voice

A companion to two other skills, not a replacement. Run it last.

- **avoid-ai-writing** — general AI-isms (em dashes, vocab tiers, filler, structure).
- **motion hook skills** (hook-writing, hook-tactics, hook-voice-patterns) — hook angle and triggers.

This file is the third pass: the specific tells those two miss, plus how my hooks should sound.

## The principle

The hook is the most surprising true thing you already wrote, moved to the front and
tightened. Don't manufacture it. If you have to invent drama, you buried the real finding.

Read-aloud test: would I say this sentence to another engineer? If it sounds like ad copy, cut it.

Assume the reader is intelligent and patient. Avoid trying to sound insightful. Avoid
concluding sentences that feel quotable. Every major claim should emerge from reasoning
rather than assertion.

## Voice

- Terse, technical, first person. State the finding flat.
- No clickbait personas, no manufactured stakes.
- Plain words over business-speak.
- One concrete claim per line. Cite the specific thing.

## Gotchas (kill these in hooks)

Each one is a tell we actually hit, with the fix.

**Throat-clear before the point** — soft setups that delay the point to fake anticipation:
"One thing that reliably helps:", "The thing that…", "Here's what works:", "What I found is:".
Cut the setup, lead with the point.
- Before: "One thing that reliably helps: specifying an output format."
- After: "Specifying an output format helps."

**Business-speak** — lever, move the needle, unlock, supercharge, leverage. Use the plain verb.
- "One lever that works" → "Specifying an output format helps."

**Claimed emotion** — "what surprised me", "better than I expected", "I was fascinated to find".
If it's surprising, the fact carries it. Cut the claim.

**Manufactured drama** — "a skill that refuses to", "the fix for lazy agents was an HTML
report", a tease dressed as a hook. Lead with the actual finding instead.

**Markdown in tweets** — `*italics*` and `**bold**` render as literal asterisks on X, and `#`
makes a hashtag, not a header. Never use markdown emphasis in a post.

**Em dashes in posts** — use a period or colon. avoid-ai-writing flags these too; for posts
it's a hard rule.

**real / actual as an intensifier** — "the real bottleneck", "actual tests run". Name what
makes it so, or drop the word.

**Manufactured quotability** — a clever closer built to sound deep, asserting a vibe instead
of earning it. Tell: it would fit on a poster but doesn't follow from anything you argued.
Cut it, or replace it with the reasoning that should have led there.
- Bad: "The fat was always the point. The salad was just keeping it company."

**Parataxis** — short clauses stacked with no conjunction, so the juxtaposition implies a
connection you never made. The rhythm fakes weight (and it's what powers most quotable
closers). Fix: state the actual relationship between the ideas (because / so / but), or merge
them into one sentence that earns the point. https://en.wikipedia.org/wiki/Parataxis
- Bad: "The fat was always the point. The salad was just keeping it company."
- Better: "The salad was there to make the fat feel acceptable."

**"It's not just X, it's Y"** — fake elevation: demote the literal thing to crown a grander
one, manufacturing depth. Just say what it is. (avoid-ai-writing flags the dash form,
"It's not X, it's Y", too.)
- Bad: "It's not just a planner, it's a way to never miss a talk."
- Fix: "A planner that resolves the time conflicts for you."

**Filler / dead weight** — a sentence that carries no information. Tell: delete it and nothing
is lost. Cut it, and vary sentence length so the rhythm isn't a flat row of equal lines.
- Bad: "AI Engineer World's Fair has 300 talks. You can't see them all."
- Fix: "551 talks at AI Engineer World's Fair. A few I'm not missing:"

**Abstract framing over a concrete number** — leading with a vague observation when a specific
figure hits harder. Lead with the number or the fact, not the commentary about it.
- Bad: "30 parallel tracks, and the talk you want is always up against another talk you want."
- Fix: "551 talks at AI Engineer World's Fair."

## Process

1. Draft in my own words.
2. hook-writing / hook-tactics: pick the angle, lead with the most surprising true line.
3. This file: kill the gotchas above, then run the exit checks — all must pass:
   - [ ] first line is the concrete finding or number, not setup
   - [ ] zero markdown emphasis (`*`/`**`/`#`) and zero em dashes in the post text
   - [ ] read aloud: nothing you wouldn't say to another engineer
   - [ ] no closer that sounds quotable but doesn't follow from the argument
4. avoid-ai-writing (linkedin profile): final pass for general isms and length.

## Output

Return the paste-ready post text (plain text, no markdown), followed by a one-line list of
which gotchas were hit and fixed — so the running list below keeps earning its keep.
This skill edits post text only; it never posts anywhere itself.

---

Keep appending gotchas here as we hit them — this is a running list, not a finished one.

## Errors

| Issue | Fix |
|---|---|
| a gotcha conflicts with avoid-ai-writing guidance | this skill wins for voice; avoid-ai-writing wins for AI-tell removal |
| hook still reads like ad copy after a pass | lead with the concrete finding/number and delete the first sentence |
| no clear finding to lead with | ask for the one number/result the post exists to share |
