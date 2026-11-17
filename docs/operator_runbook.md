# Operator runbook

## Install and check

```bash
pip install -e '.[dev]'
```

```bash
humour doctor
```

```bash
python3 -m pytest -q
```

## Fetch the pinned sources (needed for corpus work only)

```bash
mkdir -p ../humour-sources && cd ../humour-sources
git clone https://github.com/MaryKenneth/XAI_humour_styles && git -C XAI_humour_styles checkout 0eaaef08be347a4fbdadc0f1fbcad8eee4e516a5
git clone https://github.com/MaryKenneth/Two_Model_Humour_Style && git -C Two_Model_Humour_Style checkout 23a0409728f1cc1616a4336306ed67275917ea3c
git clone https://github.com/iabufarha/iSarcasmEval && git -C iSarcasmEval checkout dfc708b53bde1bb571abfb5692f63231c2232195
```

Verify the hashes:

```bash
humour sources audit --root S02=../humour-sources/Two_Model_Humour_Style --root S06=../humour-sources/iSarcasmEval
```

## Rebuild the style model and report

```bash
humour evaluate style --s01 ../humour-sources/XAI_humour_styles --s02 ../humour-sources/Two_Model_Humour_Style
```

The run resumes from verified checkpoints under `artifacts/runs/<run_id>/`. Its test partition can be used
once per frozen configuration (`artifacts/test_ledger.json`). To change the configuration, retire the test
and create a new independent one before making another confirmatory claim.

## Enable live inference

1. Put `ANTHROPIC_API_KEY` in the environment, outside the repo. Never paste it in chat or commit it.
2. Review `evals/protocols/live_run_plan.json` (`humour evaluate plan-live`) for maximum calls and tokens,
   and multiply by the current provider price.
3. Approve the spend, then run requests with `--live` or set `allowed_provider_ids: ["anthropic"]` and
   `allow_external_inference: true`.

## Serve

`humour serve` binds to 127.0.0.1 and refuses public addresses because it has no authentication.
`humour mcp` speaks MCP over stdio. Raw inputs are not logged, and uvicorn access logs are off.

## Removals

Add `{source_id, row_ref, reason, date}` to `excluded_records` in `sources/registry.yaml`, then rebuild.
Every importer filters these records. Deleting existing artifacts is a separate action that needs explicit approval.
