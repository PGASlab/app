"""Turn a grade into one concrete sentence of advice for a street-food vendor.

The classifier decides the grade. The LLM (a small open Gemma model run by
llama.cpp on the board) only phrases the advice, and is given the action and
the deadline that the rules below already computed. Its output is checked;
if the LLM is missing, fails, takes longer than LLM_TIMEOUT_S, or says
something that does not match the grade, the rule-based sentence is used.

Configuration (environment variables, all optional):

    PGAS_LLAMA_BIN    llama.cpp CLI binary   (default: llama-completion on PATH)
    PGAS_LLM_MODEL    path to the GGUF model (default: models/llm/*.gguf)
    PGAS_LLAMA_URL    base URL of a running llama-server, e.g. http://127.0.0.1:8080
                      (if set, used instead of spawning the CLI)
    PGAS_LLM_THREADS  CPU threads for llama.cpp (default 4)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import config

GRADE_PREFIXES = ("fresh", "spoiling", "spoiled", "swill")


@dataclass
class Advice:
    text: str
    source: str            # "llm" or "rules"
    grade: str
    food: str
    deadline: str | None   # HH:MM, when the rules set one
    latency_s: float
    fallback_reason: str | None = None


def food_name(label: str) -> str:
    parts = label.split("_")
    if parts and parts[0] in GRADE_PREFIXES and len(parts) > 1:
        parts = parts[1:]
    for tail in (("room", "temp"), ("fridge",)):
        if tuple(parts[-len(tail):]) == tail and len(parts) > len(tail):
            parts = parts[: -len(tail)]
    return " ".join(parts) or "food"


def _round_up_quarter(t: datetime) -> datetime:
    t = t.replace(second=0, microsecond=0)
    add = (-t.minute) % 15
    return t + timedelta(minutes=add)


def plan(grade: str, features: dict[str, float], now: datetime) -> tuple[str, str | None]:
    """Return (action keyword, deadline HH:MM or None) from deterministic rules."""
    temp = features.get("temp_c")
    hot = temp is not None and temp == temp and temp >= 30  # NaN-safe
    if grade == "FRESH":
        return "sell", _round_up_quarter(now + timedelta(hours=2 if hot else 4)).strftime("%H:%M")
    if grade == "SPOILING":
        return "discount", _round_up_quarter(now + timedelta(hours=1 if hot else 2)).strftime("%H:%M")
    if grade == "DO-NOT-SELL":
        return "discard", None
    raise ValueError(f"unknown grade {grade}")


def rule_advice(grade: str, food: str, deadline: str | None) -> str:
    if grade == "FRESH":
        return f"The {food} smells fresh: sell as normal, keep it cold and check it again before {deadline}."
    if grade == "SPOILING":
        return f"The {food} is starting to turn: sell it at a discount before {deadline}, cooked through, or take it off the menu."
    return f"Do not sell this {food}: throw it away now and wash the container before reusing it."


def build_prompt(grade: str, food: str, deadline: str | None, features: dict[str, float]) -> str:
    action = {
        "FRESH": f"It is fine to sell. Tell them to keep it cold and re-check before {deadline}.",
        "SPOILING": f"Tell them to sell it at a discount before {deadline}, cooked through, or remove it.",
        "DO-NOT-SELL": "Tell them not to sell it and to throw it away now.",
    }[grade]
    temp = features.get("temp_c")
    env = f" The stall temperature is {temp:.0f} C." if temp is not None and temp == temp else ""
    user = (
        "You advise a night-market food vendor. An electronic nose checked their "
        f"{food} and graded it {grade}.{env} {action} "
        "Reply with exactly one short, friendly sentence in English, at most 25 words, no lists, no emojis."
    )
    # Gemma chat template.
    return f"<start_of_turn>user\n{user}<end_of_turn>\n<start_of_turn>model\n"


_FIRST_SENTENCE = re.compile(r"^(.+?[.!])(\s|$)", re.S)


def clean_llm_text(text: str) -> str:
    text = text.replace("<end_of_turn>", "").replace("<eos>", "").strip().strip('"').strip()
    text = re.sub(r"\s+", " ", text)
    m = _FIRST_SENTENCE.match(text)
    return (m.group(1) if m else text).strip()


def validate(text: str, grade: str, deadline: str | None) -> str | None:
    """Return None if acceptable, else the reason it was rejected."""
    if not text:
        return "empty output"
    if len(text) > 220:
        return "too long"
    low = text.lower()
    if grade == "DO-NOT-SELL":
        if not any(k in low for k in ("discard", "throw", "bin", "dispose", "not sell", "don't sell", "do not sell")):
            return "does not tell the vendor to stop selling"
    else:
        if any(k in low for k in ("throw it away", "discard", "do not sell", "don't sell")):
            return "contradicts the grade"
        if deadline and deadline not in text:
            return f"deadline {deadline} missing"
    return None


def default_model_path() -> Path | None:
    env = os.environ.get("PGAS_LLM_MODEL")
    if env:
        return Path(env)
    found = sorted((config.MODELS_DIR / "llm").glob("*.gguf"))
    return found[0] if found else None


def run_llm(prompt: str, timeout_s: float) -> str:
    """Run llama.cpp; raises on any failure (caller falls back)."""
    url = os.environ.get("PGAS_LLAMA_URL")
    threads = os.environ.get("PGAS_LLM_THREADS", "4")
    if url:
        body = json.dumps({"prompt": prompt, "n_predict": 60, "temperature": 0.3,
                           "stop": ["<end_of_turn>", "\n"]}).encode()
        req = urllib.request.Request(url.rstrip("/") + "/completion", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return json.loads(r.read())["content"]

    binary = os.environ.get("PGAS_LLAMA_BIN") or shutil.which("llama-completion") or shutil.which("llama-cli")
    model = default_model_path()
    if not binary:
        raise FileNotFoundError("llama.cpp binary not found")
    if model is None or not model.exists():
        raise FileNotFoundError("GGUF model not found")
    cmd = [binary, "-m", str(model), "-p", prompt, "-n", "60", "--temp", "0.3",
           "-t", threads, "-no-cnv", "--no-display-prompt", "-r", "<end_of_turn>"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if out.returncode != 0:
        raise RuntimeError(f"llama.cpp exited {out.returncode}: {out.stderr[-300:]}")
    return out.stdout


def advise(
    grade: str,
    features: dict[str, float],
    label: str,
    now: datetime | None = None,
    use_llm: bool = True,
    timeout_s: float = config.LLM_TIMEOUT_S,
    llm=run_llm,
) -> Advice:
    now = now or datetime.now()
    food = food_name(label)
    _, deadline = plan(grade, features, now)
    t0 = time.perf_counter()
    reason = "LLM disabled"
    if use_llm:
        try:
            text = clean_llm_text(llm(build_prompt(grade, food, deadline, features), timeout_s))
            elapsed = time.perf_counter() - t0
            if elapsed > timeout_s:
                reason = f"LLM took {elapsed:.1f} s (> {timeout_s:.0f} s)"
            else:
                reason = validate(text, grade, deadline)
                if reason is None:
                    return Advice(text, "llm", grade, food, deadline, elapsed)
                reason = f"LLM output rejected: {reason}"
        except subprocess.TimeoutExpired:
            reason = f"LLM timed out after {timeout_s:.0f} s"
        except Exception as e:  # noqa: BLE001 - any LLM failure means fallback
            reason = f"LLM unavailable: {type(e).__name__}: {e}"
    return Advice(rule_advice(grade, food, deadline), "rules", grade, food, deadline,
                  time.perf_counter() - t0, reason)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Print vendor advice for a grade.")
    ap.add_argument("--grade", required=True, choices=config.GRADES)
    ap.add_argument("--label", required=True, help="food label, e.g. fresh_chicken")
    ap.add_argument("--features", type=Path, help="JSON file with features (optional)")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args(argv)
    feats = json.loads(a.features.read_text()) if a.features else {}
    adv = advise(a.grade, feats, a.label, use_llm=not a.no_llm)
    print(json.dumps(asdict(adv), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
