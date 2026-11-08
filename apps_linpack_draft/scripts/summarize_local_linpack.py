#!/usr/bin/env python3
"""Build a checked summary from completed local Ara2 Linpack-only RTL runs."""
import argparse
import csv
import math
from pathlib import Path
import re

FIELDS = [
    "variant", "profiled", "lanes", "vlen", "N", "NB", "mr", "lmul", "kc",
    "pipe", "cycles", "fpcyc", "util", "resid", "checksum", "panel_cycles",
    "u12_cycles", "dgemm_cycles", "solve_cycles", "source_log",
]


def run_variant(run):
    config = (run / "config.txt").read_text(encoding="utf-8")
    if "LP_OPT_PANEL_V2=1" in config:
        variant = "panel_v2"
    elif "LP_OPT_SCALAR_PHASES=1" in config:
        variant = "rvv_phases"
    else:
        variant = "baseline"
    return variant, int("LP_PROFILE=1" in config)


def parse_run(run):
    log = run / "sim.log"
    text = log.read_text(encoding="utf-8")
    if "DONE,fails=0" not in text or "mode=lp_only" not in text:
        raise ValueError(f"{log}: not a successful Linpack-only run")
    cfg_match = re.search(
        r"^CFG,lanes=(\d+),vlen=(\d+),sweepN=\d+,linpackN=(\d+),nbMax=(\d+),"
        r"reps=\d+,mode=lp_only$", text, re.MULTILINE
    )
    if not cfg_match:
        raise ValueError(f"{log}: missing or invalid CFG row")
    lanes, vlen, n, nb_max = map(int, cfg_match.groups())
    variant, profiled = run_variant(run)
    profiles = {}
    for line in text.splitlines():
        if not line.startswith("PROF,"):
            continue
        values = dict(item.split("=", 1) for item in line.split(",")[1:])
        key = (int(values["mr"]), int(values["lmul"]))
        phases = tuple(int(values[name]) for name in ("panel", "u12", "dgemm", "solve"))
        if any(value < 0 for value in phases):
            raise ValueError(f"{log}: negative profile counter")
        profiles[key] = phases
    if bool(profiles) != bool(profiled):
        raise ValueError(f"{log}: config/profile-row mismatch")

    rows = []
    for line in text.splitlines():
        if not line.startswith("RES,phase=lp,"):
            continue
        values = dict(item.split("=", 1) for item in line.split(",")[1:])
        row_n, nb = int(values["N"]), int(values["nb"])
        mr, lmul = int(values["mr"]), int(values["lmul"])
        cycles = int(values["cycles"])
        residual = float(values["resid"])
        fpcyc = float(values["fpcyc"])
        util = float(values["util"])
        expected = (2.0 / 3.0 * row_n**3 + 2.0 * row_n**2) / cycles
        if row_n != n or nb > nb_max or cycles <= 0:
            raise ValueError(f"{log}: inconsistent size or cycle count")
        if not math.isfinite(residual) or not 0.0 <= residual < 16.0:
            raise ValueError(f"{log}: invalid residual {residual}")
        if not math.isclose(fpcyc, expected, rel_tol=0.0, abs_tol=0.00051):
            raise ValueError(f"{log}: FLOP/cycle mismatch")
        if not math.isclose(util, 100.0 * expected / (2 * lanes), rel_tol=0.0, abs_tol=0.011):
            raise ValueError(f"{log}: utilization mismatch")
        phases = profiles.get((mr, lmul), ("", "", "", ""))
        if profiled and sum(phases) > cycles:
            raise ValueError(f"{log}: profile counters exceed total ROI")
        rows.append({
            "variant": variant,
            "profiled": profiled,
            "lanes": lanes,
            "vlen": vlen,
            "N": row_n,
            "NB": nb,
            "mr": mr,
            "lmul": lmul,
            "kc": int(values["kc"]),
            "pipe": int(values["pipe"]),
            "cycles": cycles,
            "fpcyc": values["fpcyc"],
            "util": values["util"],
            "resid": values["resid"],
            "checksum": values["chk"],
            "panel_cycles": phases[0],
            "u12_cycles": phases[1],
            "dgemm_cycles": phases[2],
            "solve_cycles": phases[3],
            "source_log": str(log),
        })
    if [(r["mr"], r["lmul"]) for r in rows] != [(8, 2), (4, 1)]:
        raise ValueError(f"{log}: expected tuned mr8/m2 then baseline mr4/m1")
    if len({(r["N"], r["NB"], r["resid"], r["checksum"]) for r in rows}) != 1:
        raise ValueError(f"{log}: tuned and baseline numerical results differ")
    return rows


def result_key(row):
    return tuple(row[name] for name in
                 ("variant", "profiled", "lanes", "N", "NB", "mr", "lmul"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    logs = sorted(args.root.glob("*_lanes/n*_nb*/sim.log"))
    if not logs:
        raise ValueError(f"no local Linpack RTL logs below {args.root}")
    rows = []
    for log in logs:
        run_rows = parse_run(log.parent)
        relative_log = log.relative_to(args.root).as_posix()
        for row in run_rows:
            row["source_log"] = relative_log
        rows.extend(run_rows)
    keys = [result_key(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate local RTL result keys")
    rows.sort(key=result_key)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"VALIDATED {len(rows)} local full-chain Linpack RTL rows -> {args.output}")
    groups = sorted({result_key(row)[:5] for row in rows})
    for variant, profiled, lanes, n, nb in groups:
        selected = [r for r in rows if result_key(r)[:5] == (variant, profiled, lanes, n, nb)]
        tuned = next(r for r in selected if (r["mr"], r["lmul"]) == (8, 2))
        base = next(r for r in selected if (r["mr"], r["lmul"]) == (4, 1))
        print(
            f"  {variant} profiled={profiled} L={lanes} N={n} NB={nb}: "
            f"tuned={tuned['fpcyc']} FLOP/cycle, baseline={base['fpcyc']}, "
            f"speedup={base['cycles']/tuned['cycles']:.3f}x, residual={tuned['resid']}"
        )


if __name__ == "__main__":
    main()
