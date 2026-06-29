"""Theoretical entry/exit schematic diagrams for the SPX SMA-band variant suite.
Hand-crafted illustrative price paths (NOT backtest output) showing exactly what
each rule captures. Saves PNGs for embedding into the Excel workbook.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUT.mkdir(parents=True, exist_ok=True)

C_SMA = "#888888"; C_UP = "#2e7d32"; C_LO = "#c62828"; C_PX = "#1f4e79"
C_ENT = "#0a7d2e"; C_EXIT = "#b00020"; C_FILL_IN = "#e8f5e9"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "axes.titlesize": 12, "axes.titleweight": "bold"})


def _bands(ax, x, sma, up=0.03, lo=0.03):
    ax.plot(x, sma, color=C_SMA, lw=1.4, ls="--", label="SMA", zorder=2)
    ax.plot(x, sma * (1 + up), color=C_UP, lw=1.1, label=f"+{up*100:.0f}% band", zorder=2)
    ax.plot(x, sma * (1 - lo), color=C_LO, lw=1.1, label=f"-{lo*100:.0f}% band", zorder=2)


def _marker(ax, x, y, kind, txt, dy=8):
    if kind == "entry":
        ax.scatter([x], [y], marker="^", s=140, color=C_ENT, zorder=6, edgecolor="white", lw=1.2)
    else:
        ax.scatter([x], [y], marker="v", s=140, color=C_EXIT, zorder=6, edgecolor="white", lw=1.2)
    ax.annotate(txt, (x, y), textcoords="offset points", xytext=(0, dy if dy > 0 else dy),
                ha="center", fontsize=8.5, fontweight="bold",
                color=C_ENT if kind == "entry" else C_EXIT)


def _shade_in(ax, x, mask, ymin, ymax):
    ax.fill_between(x, ymin, ymax, where=mask, color=C_FILL_IN, alpha=0.55, zorder=0)


def fig_bands():
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    x = np.arange(120)
    sma = np.full(120, 100.0)
    # a hump that starts BELOW -3% and ends BELOW -3% so both rules trigger cleanly
    px = 94.0 + 16.0 * np.sin(np.pi * x / 119.0)
    for ax, mode in zip(axes, ["conv", "early"]):
        _bands(ax, x, sma)
        ax.plot(x, px, color=C_PX, lw=2.0, label="Price", zorder=3)
        ub, lb = sma * 1.03, sma * 0.97
        inmask = np.zeros(120, bool); cur = False
        ent = exi = None
        for i in range(1, 120):
            if mode == "conv":
                if px[i] > ub[i]: cur = True
                elif px[i] < lb[i]: cur = False
            else:
                if not cur and px[i-1] <= lb[i-1] and px[i] > lb[i]: cur = True
                elif cur and ((px[i-1] >= ub[i-1] and px[i] < ub[i]) or px[i] < lb[i]): cur = False
            inmask[i] = cur
            if cur and ent is None: ent = i
            if (not cur) and ent is not None and exi is None: exi = i
        _shade_in(ax, x, inmask, 88, 112)
        if ent: _marker(ax, ent, px[ent], "entry", "ENTRY", 12 if mode=="conv" else -16)
        if exi: _marker(ax, exi, px[exi], "exit", "EXIT", -16 if mode=="conv" else 12)
        ttl = ("Conventional band (incumbent)\nenter ABOVE +3%  •  exit BELOW -3%" if mode == "conv"
               else "Early-in / early-out (your rule)\nenter rising thru -3%  •  exit falling thru +3%")
        ax.set_title(ttl)
        ax.set_ylim(88, 112); ax.set_xticks([]); ax.set_yticks([])
        ax.legend(loc="lower right", fontsize=7.5, framealpha=0.9)
    fig.suptitle("Band mechanics — what 'enter' and 'exit' mean (green = invested)", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(OUT / "diag_bands.png", dpi=130); plt.close(fig)


def fig_stops():
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    x = np.arange(120); sma = np.full(120, 100.0)
    # price enters then fails (for stop) / runs then pulls back (for trailing)
    px_fail = np.concatenate([np.linspace(96, 104, 25), np.linspace(104, 92, 30), np.linspace(92, 99, 65)])
    px_run = np.concatenate([np.linspace(96, 104, 20), np.linspace(104, 118, 45), np.linspace(118, 108, 55)])
    for ax, (px, mode) in zip(axes, [(px_fail, "fixed"), (px_run, "trail")]):
        _bands(ax, x, sma)
        ax.plot(x, px, color=C_PX, lw=2.0, label="Price", zorder=3)
        if mode == "fixed":
            ent = np.argmax(px > 103)            # conv-style entry for illustration
            entry_px = px[ent]; stop_lvl = entry_px * (1 - 0.05)
            ax.axhline(stop_lvl, color=C_EXIT, ls=":", lw=1.3)
            ax.annotate("fixed stop = entry × (1-5%)", (4, stop_lvl), fontsize=8, color=C_EXIT, va="bottom")
            sx = ent + np.argmax(px[ent:] <= stop_lvl)
            _marker(ax, ent, px[ent], "entry", "ENTRY", 12)
            _marker(ax, sx, px[sx], "exit", "STOP HIT", -18)
            ax.set_title("Fixed stop-loss (Variant A)\ncut the trade at a fixed % below entry")
        else:
            ent = np.argmax(px > 103); entry_px = px[ent]
            peak = np.maximum.accumulate(np.where(np.arange(120) >= ent, px, -1e9))
            trail = peak * (1 - 0.08)
            ax.plot(x[ent:], trail[ent:], color=C_EXIT, ls=":", lw=1.3, label="trailing stop (-8% from peak)")
            sx = ent + np.argmax(px[ent:] <= trail[ent:])
            _marker(ax, ent, px[ent], "entry", "ENTRY", 12)
            pk = ent + np.argmax(px[ent:]); _marker(ax, pk, px[pk], "exit", "peak", 12)
            ax.scatter([pk], [px[pk]], marker="o", s=60, color="#f9a825", zorder=6, edgecolor="white")
            _marker(ax, sx, px[sx], "exit", "TRAIL HIT", -18)
            ax.set_title("Trailing stop (Variant A')\nlock in gains: exit on -8% from the running peak")
        ax.set_xticks([]); ax.set_yticks([]); ax.legend(loc="lower left", fontsize=7.5, framealpha=0.9)
    fig.suptitle("Stop overlays — 'don't hang around once it turns'", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(OUT / "diag_stops.png", dpi=130); plt.close(fig)


def fig_variantB():
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    x = np.arange(120); sma = np.full(120, 100.0)
    for ax, mode in zip(axes, ["decay", "accel"]):
        for m in (1.01, 1.02, 1.03):
            ax.plot(x, sma * m, color=C_UP, lw=0.8, alpha=0.45 + (m-1)*8)
            ax.annotate(f"+{(m-1)*100:.0f}%", (118, sma[0]*m), fontsize=7, color=C_UP, va="center")
        ax.plot(x, sma, color=C_SMA, lw=1.2, ls="--")
        if mode == "decay":
            px = np.concatenate([np.linspace(98.5, 103.6, 22), np.linspace(103.6, 103.3, 8),
                                 np.linspace(103.3, 100.4, 20), np.linspace(100.4, 97, 70)])
            ax.plot(x, px, color=C_PX, lw=2.0, zorder=3)
            ent = np.argmax(px > 100.97)
            sx = ent + np.argmax(px[ent:] < 101.0)   # premium decayed back through the 1% rung
            _marker(ax, ent, px[ent], "entry", "ENTRY", 12)
            _marker(ax, sx, px[sx], "exit", "EXIT: steam gone\n(3%→2%→1%)", -24)
            ax.set_title("Variant B — momentum DECAY exit\ncushion ratchets DOWN thru bands within N days → out")
        else:
            px = np.concatenate([np.linspace(98.5, 103.2, 18), np.full(30, 103.0) + np.linspace(0, 0.25, 30),
                                 np.linspace(103.25, 97.5, 72)])
            ax.plot(x, px, color=C_PX, lw=2.0, zorder=3)
            ent = np.argmax(px > 100.97)
            sx = ent + 30   # N-day window with no new band high
            ax.axvspan(ent, sx, color="#fff3e0", alpha=0.7, zorder=0)
            ax.annotate("N-day window:\nno NEW higher band", ((ent+sx)/2, 106.0), ha="center", fontsize=8, color="#e65100")
            _marker(ax, ent, px[ent], "entry", "ENTRY", 12)
            _marker(ax, sx, px[sx], "exit", "EXIT: failed to\naccelerate", -24)
            ax.set_title("Variant B — must-ACCELERATE exit\nno higher band within N days of entry → out")
        ax.plot(x, sma, color=C_SMA, lw=1.2, ls="--", zorder=1)
        ax.set_ylim(96, 108); ax.set_xlim(0, 122); ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Variant B — two readings of 'keep jumping bands or leave'", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(OUT / "diag_variantB.png", dpi=130); plt.close(fig)


def fig_variantC():
    fig, axes = plt.subplots(2, 1, figsize=(13, 5.4), gridspec_kw={"height_ratios": [2, 1]})
    x = np.arange(120); sma = np.full(120, 100.0)
    ax, axr = axes
    _bands(ax, x, sma)
    px = np.concatenate([np.linspace(99, 95, 18), np.linspace(95, 108, 40), np.linspace(108, 101, 62)])
    ax.plot(x, px, color=C_PX, lw=2.0, label="Price", zorder=3)
    # synthetic RSI: low at the dip, rising through entry
    rsi = 50 + 26 * np.sin((x - 30) / 22.0)
    ent = np.argmax((np.arange(120) > 18) & (rsi > 50))
    sx = ent + np.argmax((px[ent:-1] >= sma[ent:-1]*1.03) & (px[ent+1:] < sma[ent+1:]*1.03))
    inmask = np.zeros(120, bool); inmask[ent:sx] = True
    _shade_in(ax, x, inmask, 92, 112)
    _marker(ax, ent, px[ent], "entry", "ENTRY: RSI/MACD\nmomentum turns up", 12)
    _marker(ax, sx, px[sx], "exit", "EXIT: close falls\nthru +3% band", -20)
    ax.set_title("Variant C — momentum (RSI / MACD) ENTRY, band EXIT", loc="left")
    ax.set_ylim(92, 112); ax.set_xticks([]); ax.set_yticks([]); ax.legend(loc="lower right", fontsize=7.5)
    axr.plot(x, rsi, color="#6a1b9a", lw=1.6)
    axr.axhline(50, color="#999", ls=":", lw=1); axr.axhline(30, color=C_LO, ls=":", lw=1); axr.axhline(70, color=C_UP, ls=":", lw=1)
    axr.scatter([ent], [rsi[ent]], marker="^", s=120, color=C_ENT, zorder=6, edgecolor="white")
    axr.annotate("RSI crosses up\nthru threshold", (ent, rsi[ent]), textcoords="offset points",
                 xytext=(8, -2), fontsize=8, color=C_ENT)
    axr.set_ylim(20, 80); axr.set_xticks([]); axr.set_yticks([30, 50, 70]); axr.set_ylabel("RSI(14)", fontsize=8)
    fig.suptitle("Variant C — enter on momentum, leave on the band", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(OUT / "diag_variantC.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    fig_bands(); fig_stops(); fig_variantB(); fig_variantC()
    print("Wrote diagrams to", OUT)
