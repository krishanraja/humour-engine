# 2026-11-17 humour engine vertical slice

Status: Local engine built on `claude/hopeful-cannon-cvibw1`. It includes contracts, ontology, pattern cards, the
registry, analysis core, compare, CLI/HTTP/MCP, the style classifier (measured), attribution, profiles,
annotation tooling and 101 passing tests. Real inference has not run (no API key), so comprehension
performance is unverified. Human evaluation is pending.

Next: Approve the bounded live run in `evals/protocols/live_run_plan.json` (330 calls max at 1,500 output tokens
each), with `ANTHROPIC_API_KEY` set outside the repo. Then run the plain/ontology/engine comparison and
start the 120-family annotation pilot.

North Star check (2026-11-17): this repository has no North Star yet. One is proposed for Krish to set, e.g.
"human-judged comprehension of the mechanism beats the plain-prompt baseline with a paired CI excluding zero."
