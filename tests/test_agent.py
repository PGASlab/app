import subprocess
from datetime import datetime

import pytest

from pgas import agent

NOW = datetime(2026, 10, 14, 11, 50)
FEATS = {"temp_c": 26.0}


def test_food_name():
    assert agent.food_name("fresh_chicken") == "chicken"
    assert agent.food_name("chicken_room_temp") == "chicken"
    assert agent.food_name("swill_mixed") == "mixed"
    assert agent.food_name("tofu") == "tofu"


def test_plan_deadlines():
    assert agent.plan("SPOILING", FEATS, NOW) == ("discount", "14:00")
    assert agent.plan("SPOILING", {"temp_c": 32.0}, NOW) == ("discount", "13:00")
    assert agent.plan("FRESH", FEATS, NOW) == ("sell", "16:00")
    assert agent.plan("DO-NOT-SELL", FEATS, NOW) == ("discard", None)
    assert agent.plan("SPOILING", {"temp_c": float("nan")}, NOW)[1] == "14:00"


def test_no_llm_uses_rules():
    a = agent.advise("SPOILING", FEATS, "chicken_room_temp", now=NOW, use_llm=False)
    assert a.source == "rules" and "14:00" in a.text and "chicken" in a.text


def test_llm_success():
    fake = lambda prompt, timeout: "Sell the chicken at a discount before 14:00 today. Extra text."
    a = agent.advise("SPOILING", FEATS, "fresh_chicken", now=NOW, llm=fake)
    assert a.source == "llm"
    assert a.text == "Sell the chicken at a discount before 14:00 today."


def test_prompt_contains_grade_and_deadline():
    seen = {}
    def fake(prompt, timeout):
        seen["p"] = prompt
        return "Sell it at a discount before 14:00."
    agent.advise("SPOILING", FEATS, "fresh_chicken", now=NOW, llm=fake)
    assert "SPOILING" in seen["p"] and "14:00" in seen["p"] and "chicken" in seen["p"]


@pytest.mark.parametrize("exc", [FileNotFoundError("no model"), RuntimeError("boom"),
                                 subprocess.TimeoutExpired("llama", 20)])
def test_llm_failure_falls_back(exc):
    def fake(prompt, timeout):
        raise exc
    a = agent.advise("DO-NOT-SELL", FEATS, "swill_mixed", now=NOW, llm=fake)
    assert a.source == "rules" and a.fallback_reason
    assert "Do not sell" in a.text


def test_slow_llm_falls_back(monkeypatch):
    clock = iter([0.0, 25.0, 25.0])
    monkeypatch.setattr(agent.time, "perf_counter", lambda: next(clock))
    a = agent.advise("FRESH", FEATS, "fresh_chicken", now=NOW, llm=lambda p, t: "Sell it before 16:00.")
    assert a.source == "rules" and "took" in a.fallback_reason


@pytest.mark.parametrize("grade,text", [
    ("DO-NOT-SELL", "Looks great, sell it all today!"),       # unsafe
    ("FRESH", "Throw it away now."),                          # contradicts
    ("SPOILING", "Sell it at a discount soon."),              # missing deadline
    ("FRESH", ""),                                            # empty
])
def test_bad_llm_output_rejected(grade, text):
    a = agent.advise(grade, FEATS, "fresh_chicken", now=NOW, llm=lambda p, t: text)
    assert a.source == "rules" and "rejected" in a.fallback_reason


def test_missing_binary_falls_back(monkeypatch):
    monkeypatch.delenv("PGAS_LLAMA_URL", raising=False)
    monkeypatch.setenv("PGAS_LLAMA_BIN", "")
    monkeypatch.setattr(agent.shutil, "which", lambda name: None)
    a = agent.advise("FRESH", FEATS, "fresh_chicken", now=NOW)
    assert a.source == "rules" and "not found" in a.fallback_reason


def test_notify_stub(tmp_path, monkeypatch):
    from pgas import notify
    monkeypatch.delenv("PGAS_TELEGRAM_TOKEN", raising=False)
    rec = notify.send("hello", outbox=tmp_path / "o.jsonl")
    assert rec["sent"] is False and "stub" in rec["reason"]
    assert "hello" in (tmp_path / "o.jsonl").read_text()
