"""Interrupted checkpoints, stale outputs, empty outputs (class 17)."""

import pytest

from humour_engine.operations.runs import RunStore, StageFailed


def test_completed_stage_is_not_rerun(tmp_path):
    calls = []
    store = RunStore(tmp_path, "r", "seal")

    def fn():
        calls.append(1)
        return b"data"

    store.run_stage("s", "v1", store.path("s.out"), fn)
    RunStore(tmp_path, "r", "seal").run_stage("s", "v1", store.path("s.out"), fn)
    assert len(calls) == 1


def test_missing_output_reruns_instead_of_counting_as_success(tmp_path):
    calls = []
    store = RunStore(tmp_path, "r", "seal")
    out = store.path("s.out")
    store.run_stage("s", "v1", out, lambda: calls.append(1) or b"x")
    out.unlink()
    store.run_stage("s", "v1", out, lambda: calls.append(1) or b"x")
    assert len(calls) == 2 and out.read_bytes() == b"x"


def test_altered_output_is_stale(tmp_path):
    store = RunStore(tmp_path, "r", "seal")
    out = store.path("s.out")
    store.run_stage("s", "v1", out, lambda: b"x")
    out.write_bytes(b"tampered")
    assert not store.is_complete("s", "v1")


def test_empty_output_is_failure_not_success(tmp_path):
    store = RunStore(tmp_path, "r", "seal")
    with pytest.raises(StageFailed, match="empty"):
        store.run_stage("s", "v1", store.path("s.out"), lambda: b"", max_attempts=1)
    assert not store.path("s.out").exists()


def test_interrupted_write_leaves_no_partial_output(tmp_path):
    store = RunStore(tmp_path, "r", "seal")

    def boom():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        store.run_stage("s", "v1", store.path("s.out"), boom)
    assert not store.path("s.out").exists()
    assert not store.is_complete("s", "v1")
    # resume works after the interruption
    store.run_stage("s", "v1", store.path("s.out"), lambda: b"ok")
    assert store.is_complete("s", "v1")


def test_retry_attempts_survive_restart(tmp_path):
    def bad():
        raise RuntimeError("x")

    with pytest.raises(StageFailed):
        RunStore(tmp_path, "r", "seal").run_stage("s", "v1", tmp_path / "o", bad, max_attempts=2)
    with pytest.raises(StageFailed):
        RunStore(tmp_path, "r", "seal").run_stage("s", "v1", tmp_path / "o", bad, max_attempts=2)


def test_changed_input_seal_requires_new_run(tmp_path):
    RunStore(tmp_path, "r", "seal-a")
    with pytest.raises(StageFailed, match="seal"):
        RunStore(tmp_path, "r", "seal-b")
