#!/usr/bin/env python3
"""Extract and validate repeated official HPL 2.3 runs from one raw log."""
import argparse
import csv
import math
from pathlib import Path
import re
import statistics

PERF = re.compile(
    r"^WR\S+\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"
    r"([0-9.]+)\s+([0-9.eE+-]+)", re.MULTILINE
)
RESIDUAL = re.compile(r"\)=\s*([0-9.eE+-]+)\s*\.+\s*PASSED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    text = args.log.read_text(encoding="utf-8")
    if "HPLinpack 2.3" not in text:
        raise ValueError("missing official HPL 2.3 banner")
    performances = PERF.findall(text)
    residuals = RESIDUAL.findall(text)
    if not performances or len(performances) != len(residuals):
        raise ValueError(
            f"performance/residual count mismatch: {len(performances)}/{len(residuals)}"
        )
    passed = text.count("1 tests completed and passed residual checks")
    failed = text.count("0 tests completed and failed residual checks")
    if passed != len(performances) or failed != len(performances):
        raise ValueError("official per-run PASSED summary count mismatch")

    rows = []
    for repetition, (performance, residual) in enumerate(
        zip(performances, residuals), 1
    ):
        n, nb, p, q, time_s, gflops = performance
        expected_gflops = (2.0 / 3.0 * int(n) ** 3 + 2.0 * int(n) ** 2) / (
            float(time_s) * 1e9
        )
        # HPL prints time to 0.01 s but computes GFLOPS from its unrounded
        # timer; allow 0.1% for the independent rounded-time recomputation.
        if not math.isclose(float(gflops), expected_gflops, rel_tol=1e-3):
            raise ValueError(f"run {repetition}: GFLOPS does not match N and time")
        if not 0.0 <= float(residual) < 16.0:
            raise ValueError(f"run {repetition}: residual outside official threshold")
        rows.append(
            {
                "repetition": repetition,
                "N": int(n),
                "NB": int(nb),
                "P": int(p),
                "Q": int(q),
                "time_s": time_s,
                "gflops": gflops,
                "residual": residual,
                "result": "PASSED",
            }
        )
    if len({(r["N"], r["NB"], r["P"], r["Q"]) for r in rows}) != 1:
        raise ValueError("a repeat series must use one fixed HPL configuration")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    times = [float(r["time_s"]) for r in rows]
    rates = [float(r["gflops"]) for r in rows]
    print(
        f"VALIDATED {len(rows)} official HPL runs: N={rows[0]['N']} NB={rows[0]['NB']}"
    )
    print(
        "time_s min/median/max = "
        f"{min(times):.2f}/{statistics.median(times):.2f}/{max(times):.2f}"
    )
    print(
        "GFLOPS min/median/max = "
        f"{min(rates):.4f}/{statistics.median(rates):.4f}/{max(rates):.4f}"
    )


if __name__ == "__main__":
    main()
