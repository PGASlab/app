"""Figures for the README and the article (PNG).

    python -m pgas.plot                     # data/raw -> docs/figures/

* spoilage_<label>.png  - one per continuous capture: hours on x, each MQ
  sensor's rise above the fresh baseline (volts, 15-min rolling median) on y.
* hood_fresh_vs_spoiled.png - hood captures overlaid, one panel per sensor:
  seconds since the hood went over the food on x, rise above that capture's
  own 30 s ambient baseline on y; fresh vs spoiled/swill in two colours.

Captures marked "synthetic" in their JSON sidecar are refused when the output
folder is inside the repository.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from . import config, labeling
from .dataio import Capture, list_captures, load_capture

# Categorical slots 1-3 of the validated reference palette (light mode).
SERIES = {"mq135": "#2a78d6", "mq3": "#eb6834", "mq2": "#1baf7a"}
GRADE_COLORS = {"FRESH": "#2a78d6", "SPOILING": "#eda100", "DO-NOT-SELL": "#eb6834"}
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def _style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _rolling_median(v: np.ndarray, n: int) -> np.ndarray:
    if n <= 1 or v.size < n:
        return v
    pad = n // 2
    p = np.pad(v, pad, mode="edge")
    return np.array([np.nanmedian(p[i:i + n]) for i in range(v.size)])


def _check(caps: list[Capture], out_dir: Path) -> None:
    try:
        out_dir.resolve().relative_to(config.REPO_ROOT.resolve())
        inside = True
    except ValueError:
        inside = False
    if inside and any(c.meta.get("synthetic") for c in caps):
        raise SystemExit("refusing to write figures from synthetic data inside the repo")


def plot_spoilage(cap: Capture, out_dir: Path, smooth_rows: int = 15) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    hours = cap.t_s / 3600
    nb = config.CONTINUOUS_BASELINE_ROWS
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=150)
    _style(ax)
    for s in config.SENSORS:
        v = cap.volts(s)
        d = _rolling_median(v - np.nanmedian(v[:nb]), smooth_rows)
        ax.plot(hours, d, color=SERIES[s], linewidth=2, label=f"{s.upper()} ({config.SENSOR_GASES[s]})")
        ax.annotate(s.upper(), (hours[-1], d[-1]), xytext=(4, 0), textcoords="offset points",
                    fontsize=8, color=TEXT, va="center")
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xlabel("Hours since start", color=TEXT, fontsize=9)
    ax.set_ylabel("Rise above fresh baseline (V)", color=TEXT, fontsize=9)
    start = cap.meta.get("started", cap.started.isoformat())
    ax.set_title(f"{cap.label.replace('_', ' ')} - started {start}", fontsize=10, color=TEXT, loc="left")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    out = out_dir / f"spoilage_{cap.label}.png"
    fig.savefig(out)
    plt.close(fig)
    return out


def plot_hood(caps: list[Capture], out_dir: Path) -> Path | None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    graded = [(c, labeling.label_hood(c.label)) for c in caps]
    graded = [(c, g) for c, g in graded if g is not None and c.mask("expose").any() and c.mask("baseline").any()]
    if not graded:
        return None
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), dpi=150, sharey=True)
    seen = set()
    for ax, s in zip(axes, config.SENSORS):
        _style(ax)
        for c, g in graded:
            v = c.volts(s)
            base = np.nanmedian(v[c.mask("baseline")])
            t0 = c.t_s[c.mask("expose")][0]
            keep = c.mask("expose") | c.mask("recover")
            lbl = g if g not in seen else None
            seen.add(g)
            ax.plot(c.t_s[keep] - t0, v[keep] - base, color=GRADE_COLORS[g], linewidth=1.5, alpha=0.85, label=lbl)
        ax.axvline(config.HOOD_EXPOSE_S, color=MUTED, linewidth=0.8, linestyle="--")
        ax.axhline(0, color=MUTED, linewidth=0.8)
        ax.set_title(f"{s.upper()} - {config.SENSOR_GASES[s]}", fontsize=9, color=TEXT, loc="left")
        ax.set_xlabel("Seconds since hood placed", color=TEXT, fontsize=8)
    axes[0].set_ylabel("Rise above ambient (V)", color=TEXT, fontsize=9)
    axes[0].legend(frameon=False, fontsize=8)
    n = {g: sum(1 for _, gg in graded if gg == g) for g in config.GRADES}
    fig.suptitle("Hood mode: " + ", ".join(f"{g} n={k}" for g, k in n.items() if k)
                 + "  (dashed line = hood lifted)", fontsize=9, color=MUTED, x=0.01, ha="left")
    fig.tight_layout()
    out = out_dir / "hood_fresh_vs_spoiled.png"
    fig.savefig(out)
    plt.close(fig)
    return out


def run(data_dir: Path, out_dir: Path) -> list[Path]:
    caps = [load_capture(p) for p in list_captures(data_dir)]
    _check(caps, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = [plot_spoilage(c, out_dir) for c in caps
            if c.mode == "continuous" and len(c) > config.CONTINUOUS_BASELINE_ROWS]
    h = plot_hood([c for c in caps if c.mode == "hood"], out_dir)
    if h:
        outs.append(h)
    return outs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=config.DATA_RAW)
    ap.add_argument("--out-dir", type=Path, default=config.FIGURES_DIR)
    a = ap.parse_args(argv)
    for p in run(a.data_dir, a.out_dir):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
