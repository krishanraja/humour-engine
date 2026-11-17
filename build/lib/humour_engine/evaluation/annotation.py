"""Human annotation machinery: Label Studio adapter, blinded pairwise packets, agreement.

Independent annotations, adjudications and system outputs are kept in separate
files. Model output is never written into a gold field.
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict

from humour_engine.contracts.analysis import AnalysisResult
from humour_engine.taxonomy import load_taxonomy

READINGS = ["supported", "not_supported", "ambiguous", "insufficient_context"]


def label_studio_config() -> str:
    tax = load_taxonomy()

    def choices(name, axis, multi=True):
        opts = "".join(f'<Choice value="{v}"/>' for v in sorted(tax.values(axis)))
        return f'<Choices name="{name}" toName="text" choice="{"multiple" if multi else "single"}">{opts}</Choices>'

    readings = "".join(f'<Choice value="{r}"/>' for r in READINGS)
    return (
        "<View>\n"
        '  <Text name="text" value="$text"/>\n'
        '  <Header value="1. Is a humorous reading supported by this text and context?"/>\n'
        f'  <Choices name="comic_reading" toName="text" choice="single" required="true">{readings}</Choices>\n'
        '  <Header value="2. Which mechanisms apply?"/>\n'
        f"  {choices('mechanism', 'mechanism')}\n"
        '  <Header value="3. Which rhetorical modes apply?"/>\n'
        f"  {choices('rhetorical_mode', 'rhetorical_mode')}\n"
        '  <Header value="4. Highlight the text that supports the reading"/>\n'
        '  <Labels name="evidence" toName="text"><Label value="evidence"/></Labels>\n'
        '  <Header value="5. Essential elements an explanation must mention (one per line)"/>\n'
        '  <TextArea name="essential_elements" toName="text" rows="3"/>\n'
        '  <Header value="6. Enjoyable or appropriate for the stated audience? (separate from 1)"/>\n'
        '  <Choices name="audience" toName="text" choice="single"><Choice value="yes"/><Choice value="no"/>'
        '<Choice value="unsure"/><Choice value="no_audience_stated"/></Choices>\n'
        "</View>\n"
    )


def tasks_from_cases(cases: list[dict]) -> list[dict]:
    """Label Studio tasks. No expected labels or fixture answers are included."""
    out = []
    for c in cases:
        segs = c["request"]["segments"]
        text = "\n".join(f"[{s['segment_id']}|{s.get('speaker_id') or '?'}] {s['text']}" for s in segs)
        out.append({"data": {"text": text, "item_id": c["id"], "family": c.get("family")}})
    return out


def import_label_studio(export: list[dict]) -> list[dict]:
    """Flatten an LS JSON export into one row per (item, annotator). Raw, unadjudicated."""
    rows = []
    for task in export:
        item = task["data"].get("item_id")
        for ann in task.get("annotations", []):
            row = {"item_id": item, "annotator": str(ann.get("completed_by")), "comic_reading": None,
                   "mechanism": [], "rhetorical_mode": [], "evidence": [], "essential_elements": [], "audience": None}
            for r in ann.get("result", []):
                name, val = r.get("from_name"), r.get("value", {})
                if name in ("comic_reading", "audience"):
                    row[name] = (val.get("choices") or [None])[0]
                elif name in ("mechanism", "rhetorical_mode"):
                    row[name] = val.get("choices", [])
                elif name == "evidence":
                    row["evidence"].append({"start": val.get("start"), "end": val.get("end"), "text": val.get("text")})
                elif name == "essential_elements":
                    row["essential_elements"] += [t for t in val.get("text", []) if t.strip()]
            rows.append(row)
    return rows


def fleiss_kappa(rows: list[dict], field: str = "comic_reading", categories: list[str] = READINGS) -> dict:
    by_item = defaultdict(list)
    for r in rows:
        if r.get(field) is not None:
            by_item[r["item_id"]].append(r[field])
    items = [v for v in by_item.values() if len(v) >= 2]
    if not items:
        return {"kappa": None, "n_items": 0}
    n = min(len(v) for v in items)
    items = [v[:n] for v in items]
    N, k = len(items), len(categories)
    mat = [[Counter(v)[c] for c in categories] for v in items]
    p_j = [sum(row[j] for row in mat) / (N * n) for j in range(k)]
    P_i = [(sum(x * x for x in row) - n) / (n * (n - 1)) for row in mat]
    P_bar, P_e = sum(P_i) / N, sum(p * p for p in p_j)
    kappa = (P_bar - P_e) / (1 - P_e) if P_e < 1 else None
    disagree = sum(1 for v in items if len(set(v)) > 1)
    return {"kappa": None if kappa is None else round(kappa, 4), "n_items": N, "raters_per_item": n,
            "items_needing_adjudication": disagree}


def pairwise_packet(pairs: list[tuple[str, AnalysisResult, AnalysisResult]], seed: int, max_chars: int = 1200):
    """Blind A/B packet. Returns (packet for judges, key kept by the coordinator)."""
    from humour_engine.analysis.render import render_markdown

    rng = random.Random(seed)
    packet, key = [], []
    for item_id, sys1, sys2 in pairs:
        outs = [("system_1", sys1), ("system_2", sys2)]
        rng.shuffle(outs)

        def blind(res: AnalysisResult) -> str:
            md = render_markdown(res)
            for s in (res.versions.provider or "", res.versions.model or "", res.analysis_id):
                if s:
                    md = md.replace(s, "[hidden]")
            return md[:max_chars]

        packet.append({"item_id": item_id, "A": blind(outs[0][1]), "B": blind(outs[1][1]),
                       "question": "Which explanation better identifies the supported reading and its mechanism, "
                                   "grounded in the text, without unsupported claims? A / B / tie"})
        key.append({"item_id": item_id, "A": outs[0][0], "B": outs[1][0], "seed": seed})
    return packet, key


def score_pairwise(judgements: list[dict], key: list[dict], expected_items: list[str]) -> dict:
    """Win/tie/loss for system_2 vs system_1 with the full denominator, including missing judgements."""
    k = {x["item_id"]: x for x in key}
    win = tie = loss = 0
    judged = set()
    for j in judgements:
        kk = k[j["item_id"]]
        judged.add(j["item_id"])
        if j["choice"] == "tie":
            tie += 1
        else:
            chosen = kk[j["choice"]]
            win += chosen == "system_2"
            loss += chosen == "system_1"
    missing = [i for i in expected_items if i not in judged]
    non_tied = win + loss
    return {"system_2_wins": win, "ties": tie, "system_2_losses": loss, "missing": len(missing),
            "denominator": len(expected_items),
            "win_rate_non_tied": round(win / non_tied, 4) if non_tied else None}


def write_jsonl(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
