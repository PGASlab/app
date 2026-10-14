"""Compile and profile the PGAS ONNX classifier on Qualcomm AI Hub (run on the Mac).

    qai-hub configure --api_token <TOKEN>     # once; token from aihub.qualcomm.com
    python -m pgas.aihub                       # picks the closest device
    python -m pgas.aihub --list                # show candidate devices
    python -m pgas.aihub --device "QCS6490 (Proxy)"

Writes models/aihub_result.json. Every number in docs/ai-hub.md must come
from that file (cloud profile) or from the board log (on-board baseline).

Device choice: the UNO Q's QRB2210 is preferred if AI Hub lists it; otherwise
the first device whose name or attributes match the preferences below, and the
choice is recorded.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from . import config

PREFERENCES = ("uno q", "qrb2210", "qcm2290", "qcs2290", "qcs6490", "qcs8275")


def _matches(dev, key: str) -> bool:
    text = " ".join([dev.name, *getattr(dev, "attributes", [])]).lower()
    return key in text


def pick_device(devices: list) -> tuple[object | None, str]:
    for key in PREFERENCES:
        for d in devices:
            if _matches(d, key):
                return d, key
    return None, ""


def run(model: Path, device_name: str | None, out: Path) -> dict:
    import qai_hub as hub

    devices = hub.get_devices()
    if device_name:
        dev = hub.Device(device_name)
        why = "requested"
    else:
        dev, why = pick_device(devices)
        if dev is None:
            raise SystemExit("no matching device; run with --list and pass --device")
    card = json.loads((model.parent / "model_card.json").read_text())
    n = len(card["features"])
    result: dict = {"created": datetime.now().isoformat(timespec="seconds"), "device": dev.name,
                    "matched_on": why, "model": card["model"], "n_features": n, "attempts": []}
    for runtime in ("onnx", "tflite"):
        att: dict = {"target_runtime": runtime}
        try:
            cj = hub.submit_compile_job(model=str(model), device=dev,
                                        input_specs={"features": ((1, n), "float32")},
                                        options=f"--target_runtime {runtime}")
            att["compile_job"] = cj.job_id
            target = cj.get_target_model()
            if target is None:
                att["error"] = f"compile failed: {cj.get_status().message}"
                result["attempts"].append(att)
                continue
            pj = hub.submit_profile_job(model=target, device=dev)
            att["profile_job"] = pj.job_id
            prof = pj.download_profile()
            summ = prof.get("execution_summary", {})
            att["estimated_inference_time_us"] = summ.get("estimated_inference_time")
            att["peak_memory_bytes"] = summ.get("estimated_inference_peak_memory")
            att["compute_units"] = sorted({l.get("compute_unit") for l in prof.get("execution_detail", [])})
        except Exception as e:  # noqa: BLE001 - record and try the next runtime
            att["error"] = f"{type(e).__name__}: {e}"
        result["attempts"].append(att)
    out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", type=Path, default=config.MODELS_DIR / "pgas_classifier.onnx")
    ap.add_argument("--device")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", type=Path, default=config.MODELS_DIR / "aihub_result.json")
    a = ap.parse_args(argv)
    if a.list:
        import qai_hub as hub

        for d in hub.get_devices():
            print(f"{d.name:45s} {d.os:10s} {', '.join(d.attributes)}")
        return 0
    print(json.dumps(run(a.model, a.device, a.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
