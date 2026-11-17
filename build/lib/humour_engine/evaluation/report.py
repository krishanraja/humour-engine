"""Readable report from a measured style experiment. Numbers come only from the run output."""

from __future__ import annotations

import json
from pathlib import Path


def write_style_report(report: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{report['run_id']}.json").write_text(json.dumps(report, indent=1, default=str))
    t = report["test"]
    d = report["data"]
    sel = report["dev_selection"]["selected"]
    lines = [
        f"# Style classifier experiment: {report['run_id']}",
        "",
        "Task: MaryKenneth five-class humour-style labels (self-enhancing, self-deprecating, affiliative, aggressive,",
        "neutral). Source-specific social-function prediction; not a measure of humour comprehension.",
        "",
        "## Data",
        f"- Records imported: {d['n_records']} across the five-class, four-class, binary and XAI views",
        f"- Distinct texts after canonical identity: {d['n_canonical_texts']} (label views collapse onto the same texts)",
        f"- Split groups (families): {d['n_groups']}; near-duplicate candidates co-located pending review: {len(d['near_duplicate_candidates_pending_review'])}",
        f"- Label conflicts across views: {len(d['label_conflicts'])}",
        "- Partition texts: " + ", ".join(f"{p} {v['texts']}" for p, v in report["partition_sizes"].items()),
        "- Split claim: joke-family disjoint. Not author- or source-disjoint (no such metadata exists).",
        "",
        "## Frozen configuration",
        f"- Config hash `{report['frozen_config_hash'][:16]}`, manifest seal `{report['frozen_config']['manifest_seal'][:16]}`",
    ]
    for v, s in sel.items():
        lines.append(f"- {v}: C={s['C']} chosen on dev (dev macro-F1 {s['dev_macro_f1']}), temperature {s['temperature']}")
    lines += [
        "",
        f"## Sealed test ({t['n_test_texts']} texts, evaluated once)",
        "",
        "| System | Macro-F1 | Accuracy | Brier (calibrated) | Brier (raw) | ECE |",
        "|---|---|---|---|---|---|",
        f"| Majority baseline | {t['majority_baseline']['macro_f1']} | {t['majority_baseline']['accuracy']} | {t['majority_baseline']['brier']} | | |",
    ]
    for v in ("single", "hierarchical"):
        r = t[v]
        lines.append(f"| {v} | {r['macro_f1']} | {r['accuracy']} | {r['brier']} | {r['brier_uncalibrated']} | {r['reliability']['ece']} |")
    h = t["hierarchical_minus_single"]
    s = t["single_minus_majority"]
    lines += [
        "",
        f"- Hierarchical minus single, macro-F1: {h['point']} (paired bootstrap 95% CI {h['ci95']}, {h['n_groups']} independent texts).",
        f"- Single minus majority baseline: {s['point']} (95% CI {s['ci95']}).",
        "",
        "### Per-class (single)",
        "| Class | P | R | F1 | Support |",
        "|---|---|---|---|---|",
    ]
    for c, m in t["single"]["per_class"].items():
        lines.append(f"| {c} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |")
    lines += ["", "### Per-class (hierarchical)", "| Class | P | R | F1 | Support |", "|---|---|---|---|---|"]
    for c, m in t["hierarchical"]["per_class"].items():
        lines.append(f"| {c} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |")
    lines += [
        "",
        f"Denominator: {t['denominator']}",
        "",
        "## Reading",
        "- Deployed variant (chosen on dev, not test): " + report.get("deployed_variant", "n/a"),
        "- The hierarchical routing is a hypothesis; this run does not establish an improvement unless its CI excludes zero.",
        "- Not a reproduction of the upstream papers: different features (TF-IDF, not GTE/DistilBERT), and an engine-assigned split.",
        "- Small test set; per-class supports are 35 to 50 texts, so per-class numbers are noisy.",
    ]
    path = out_dir / f"{report['run_id']}.md"
    path.write_text("\n".join(lines) + "\n")
    return path
