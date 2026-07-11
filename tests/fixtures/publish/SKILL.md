---
name: highsignal
description: Detect and remove AI-writing tells from prose.
license: MIT
compatibility: Any agent that reads a SKILL.md. No external tools required.
metadata:
  author: Jason Varbedian
---

# highsignal: detect AI-writing tells

Goal: high signal, no filler. Find the tells that make writing sound generated,
then either flag them or rewrite the text in a plain human voice.

## Modes

- **detect:** Quote the offending text and name the tell.
- **rewrite:** Return the clean version, then briefly list what changed.

## AI-writing tells

**Throat-clear**
A soft setup that delays the point.

**Claimed emotion**
"What surprised me," "I was fascinated to find." The fact should carry the interest.
