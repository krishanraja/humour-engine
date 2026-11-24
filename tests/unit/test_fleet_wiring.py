"""The fleet wiring: auto-merge picks only our own ready pull request, and the closeout fold runs the harness hook."""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
PICK = ROOT / ".github" / "scripts" / "auto-merge-pick.jq"


def test_workflows_parse_and_auto_merge_follows_ci():
    names = {}
    for path in WORKFLOWS.glob("*.yml"):
        names[path.name] = yaml.safe_load(path.read_text())["name"]
    assert names["ci.yml"] == "CI"
    auto = yaml.safe_load((WORKFLOWS / "auto-merge.yml").read_text())
    assert auto[True]["workflow_run"]["workflows"] == ["CI"]  # yaml reads `on` as True


def _pick(prs, sha="abc", owner="krishanraja"):
    out = subprocess.run(
        ["jq", "-r", "--arg", "sha", sha, "--arg", "owner", owner, "-f", str(PICK)],
        input=json.dumps(prs), capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _pr(**over):
    pr = {"number": 7, "headRefOid": "abc", "isDraft": False, "isCrossRepository": False,
          "author": {"login": "krishanraja"}, "headRepositoryOwner": {"login": "krishanraja"}}
    pr.update(over)
    return pr


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")
def test_auto_merge_picks_only_our_ready_pull_request_at_the_green_sha():
    assert _pick([_pr()]) == "7"
    assert _pick([_pr(author={"login": "github-actions[bot]"})]) == "7"
    assert _pick([_pr(isDraft=True)]) == ""
    assert _pick([_pr(headRefOid="other")]) == ""
    assert _pick([_pr(isCrossRepository=True)]) == ""
    assert _pick([_pr(author={"login": "someone-else"})]) == ""
    assert _pick([_pr(headRepositoryOwner={"login": "someone-else"})]) == ""


def test_closeout_fold_pins_the_harness_hook():
    pinned = re.search(r'echo "([0-9a-f]{64})  \.claude/hooks/harness-closeout\.mjs"',
                       (WORKFLOWS / "now-cap.yml").read_text()).group(1)
    actual = hashlib.sha256((ROOT / ".claude" / "hooks" / "harness-closeout.mjs").read_bytes()).hexdigest()
    assert pinned == actual
