# North Star

Status: draft, awaiting Krish. Not set.
Owner: Krish Raja

This repository has no North Star yet. Only Krish sets one (ai-harness `contract/north-star-metric.md`: "Krish sets the number and the ladder"), so nothing below is in force, and no session or reader should treat it as a number. The draft is in a plain `yaml` fence on purpose, not a `yaml north-star-metric` block, so no machine reads it as set. When Krish rules, the block below becomes `yaml north-star-metric`, this status line changes, and `NOW.md` gains its state line.

## Draft for Krish

Serves (draft): the purpose's "make it legible to people while it still counts", through the fleet's public copy: one definition of humour that the content and growth engines call before a funny line goes out, so a joke lands the way Krish means it.

Ambition (draft): when an engine asks this repository why a line is funny, a person agrees with the answer more often than with a plain prompt's.

```yaml
metric: "Human-judged mechanism accuracy on the sealed family-grouped set: the engine minus the plain-prompt baseline"
unit: "percentage points"
direction: up
target: 10            # draft; the paired 95% interval must also exclude zero
deadline: 2027-02-22  # draft, a Monday
ladder_shape: linear
source: "evals/: the human evaluation of the bounded live run, paired against the plain-prompt baseline"
status: draft
ladder: pending-baseline
```

What it needs first: the bounded live run (`evals/protocols/live_run_plan.json`, approved spend) and the human evaluation it feeds. Until both run, the number cannot be measured.

The question for Krish: set this North Star (human-judged mechanism accuracy, at least 10 points above the plain-prompt baseline by 22 February 2027), change it, or name another?
