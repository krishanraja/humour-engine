# North Star

Status: set by Krish, 2026-11-24.
Owner: Krish Raja

Serves: the purpose's "make it legible to people while it still counts", through the fleet's public copy: one definition of humour that the content and growth engines call before a funny line goes out, so a joke lands the way Krish means it.

Ambition: when an engine asks this repository why a line is funny, a person agrees with the answer more often than with a plain prompt's.

## The number

```yaml north-star-metric
metric: "Human-judged mechanism accuracy on the sealed family-grouped set: the engine minus the plain-prompt baseline"
unit: "percentage points"
direction: up
target: 10            # and the paired 95% interval excludes zero
deadline: 2027-02-22
ladder_shape: linear
source: "evals/: the human evaluation of the bounded live run, paired against the plain-prompt baseline"
status: active
ladder: pending-baseline
```

What it needs first: the bounded live run (`evals/protocols/live_run_plan.json`, approved spend) and the human evaluation it feeds. Until both run, the number cannot be measured, and the ladder waits on that baseline.

Only Krish changes this file.
