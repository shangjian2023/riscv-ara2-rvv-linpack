#!/usr/bin/env python3
"""Derive the fair B-packed K230 summary without changing historical CSVs."""
import csv
from collections import Counter
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "results"


def read(name):
    with (RES / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def medians(name):
    rows = read(name)
    assert len(rows) == 248, (name, len(rows))
    assert max(float(r["max_diff"]) for r in rows) == 0.0
    return {(r["variant"], int(r["n"])): float(r["gflops"])
            for r in rows if r["section"] == "summary" and r["stat_or_rep"] == "median"}


before = medians("k230_fair.csv")
after = medians("k230_fair_packb.csv")
full = read("k230_board_packb_fair.csv")
assert Counter(r["section"] for r in full) == {"check": 28, "sweep": 52, "linpack": 12}
assert all(r["ok"] == "1" for r in full)
assert all(float(r["max_diff"]) == 0.0 for r in full if r["section"] != "linpack")
linpack = [r for r in full if r["section"] == "linpack"]

lines = [
    "# K230 B-packed fair benchmark summary",
    "",
    "DGEMM values are medians over 15/13/9/5 runs for N=160/256/512/1024.",
    "All DGEMM outputs match the scalar reference exactly (max_diff=0).",
    "The unpacked and packed runs are separate binaries; historical CSVs are unchanged.",
    "",
    "| N | Scalar | GCC blocked | RVV unpacked | RVV B-packed | Packed/scalar | Packing gain |",
    "|---:|---:|---:|---:|---:|---:|---:|",
]
for n in (160, 256, 512, 1024):
    scalar = before[("naive_scalar", n)]
    blocked = before[("blocked_autovec", n)]
    unpacked = before[("rvv_mr2_m8_p1", n)]
    packed = after[("rvv_mr2_m8_p1", n)]
    lines.append(f"| {n} | {scalar:.4f} | {blocked:.4f} | {unpacked:.4f} | "
                 f"**{packed:.4f}** | {packed/scalar:.2f}× | {packed/unpacked:.2f}× |")

lines += [
    "",
    "Linpack rows use the same matrix for every variant at a given N; residuals therefore",
    "match within each row set. These are single-run small-N custom Linpack-style results,",
    "not official HPL scores. Official HPL 2.3 results are under `hpl/results/`.",
    "",
    "| N | Baseline GFLOPS | mr2×m8/kc128 GFLOPS | Speedup | Shared residual |",
    "|---:|---:|---:|---:|---:|",
]
for n in (128, 192, 256):
    rows = [r for r in linpack if int(r["n"]) == n]
    assert len(rows) == 4
    assert len({r["max_diff"] for r in rows}) == 1
    base = next(r for r in rows if r["variant"] == "baseline")
    best = next(r for r in rows if r["variant"] == "mr2m8kc128")
    gain = float(best["gflops"]) / float(base["gflops"])
    lines.append(f"| {n} | {float(base['gflops']):.4f} | **{float(best['gflops']):.4f}** | "
                 f"{gain:.2f}× | {base['max_diff']} |")

out = RES / "k230_packb_summary.md"
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"saved {out}")
