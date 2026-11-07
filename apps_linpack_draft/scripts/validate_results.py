#!/usr/bin/env python3
"""Validate the frozen cloud RTL, E8, and K230 result tables."""
from collections import Counter
import csv
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
CLOUD = ROOT / "apps_linpack_draft/results/cloud_all.csv"
E8 = ROOT / "apps_linpack_draft/results/e8_cloud/e8_error.csv"
K230_DIR = ROOT / "teammate_draft/riscv/linpack-ara2/results"
failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def close(actual, expected, tolerance, message):
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        failures.append(f"{message}: got {actual}, expected {expected}")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


cloud = read_csv(CLOUD)
check(len(cloud) == 93, f"cloud_all row count: {len(cloud)} != 93")
check(sum(r["job"].startswith("e0_") for r in cloud) == 36, "E0 row count != 36")
check(sum(r["job"].startswith("e3_") for r in cloud) == 41, "E3 row count != 41")
check(sum(r["job"].startswith("e7_") for r in cloud) == 16, "E7 row count != 16")
keys = [(r["job"], r["phase"], r["var"], r["N"], r["mr"], r["lmul"],
         r["kc"], r["pipe"]) for r in cloud]
check(len(set(keys)) == len(keys), "duplicate cloud result keys")
for r in cloud:
    lanes = int(r["config"].split("_")[0])
    n = int(r["N"])
    cycles = int(r["cycles"])
    check(cycles > 0, f"non-positive cycles in {r['job']}")
    if r["phase"] == "e0":
        check(not r["fpcyc"] and not r["util"], f"unexpected E0 derived fields: {r['job']}")
        continue
    expected_fpcyc = 2.0 * n**3 / cycles
    close(float(r["fpcyc"]), expected_fpcyc, 0.00051, f"fpcyc mismatch: {r['job']}/{r['var']}")
    close(float(r["util"]), 100.0 * expected_fpcyc / (2 * lanes), 0.011,
          f"util mismatch: {r['job']}/{r['var']}")

e8 = read_csv(E8)
check(len(e8) == 57, f"E8 row count: {len(e8)} != 57")
check(Counter(r["var"] for r in e8) == {"rvv": 49, "v0_scalar": 4, "v2_autovec": 4},
      "E8 variant counts differ from 49 RVV + 4 scalar + 4 autovec")
for i, r in enumerate(e8, 2):
    measured = float(r["meas_cycles"])
    modeled = float(r["model_cycles"])
    close(float(r["err_cycles_pct"]), 100.0 * (modeled - measured) / measured,
          0.051, f"E8 cycle error mismatch on CSV line {i}")

raw = read_csv(K230_DIR / "k230_board_vlen2.csv")
sections = Counter(r["section"] for r in raw)
check(sections == {"check": 28, "sweep": 52, "linpack": 9},
      f"K230 section counts are {dict(sections)}")
checks = [r for r in raw if r["section"] == "check"]
sweeps = [r for r in raw if r["section"] == "sweep"]
linpack = [r for r in raw if r["section"] == "linpack"]
check(all(r["ok"] == "1" for r in raw), "K230 contains a failed check")
check(all(float(r["max_diff"]) == 0.0 for r in checks + sweeps),
      "K230 DGEMM contains a nonzero residual")
check(all(float(r["max_diff"]) < 0.01 for r in linpack),
      "K230 Linpack residual exceeds 0.01")
for r in checks + sweeps:
    if float(r["ms"]) == 0.0:
        check(float(r["gflops"]) == 0.0, f"zero-time K230 check has nonzero GFLOPS: {r['variant']}")
        continue
    n, m, k = (int(r[x]) for x in ("n", "m", "k"))
    expected = 2.0 * n * m * k / (float(r["ms"]) * 1e6)
    close(float(r["gflops"]), expected, max(0.000051, expected * 0.0002),
          f"K230 DGEMM GFLOPS mismatch: {r['variant']} {n}x{m}x{k}")
for r in linpack:
    n = int(r["n"])
    expected = (2.0 * n**3 / 3.0 + 2.0 * n**2) / (float(r["ms"]) * 1e6)
    close(float(r["gflops"]), expected, max(0.000051, expected * 0.0002),
          f"K230 Linpack GFLOPS mismatch: {r['variant']} N={n}")

best = max(sweeps, key=lambda r: float(r["gflops"]))
worst = min(sweeps, key=lambda r: float(r["gflops"]))
naive = next(r for r in checks if r["variant"] == "naive_scalar")
autovec = next(r for r in checks if r["variant"] == "blocked_autovec")
summary = {r["指标"]: r["数值"] for r in read_csv(K230_DIR / "e12_k230_board.csv")}
check(next(v for k, v in summary.items() if k.startswith("功能校验")).startswith("28/28"),
      "K230 summary does not report 28/28 checks")
check(summary["最优 DGEMM 配置"].startswith(f"{best['variant']} kc={best['kc']}"),
      "K230 summary best configuration does not match raw data")
check(summary["最优 DGEMM 吞吐"].startswith(f"{float(best['gflops']):.3f} GFLOPS"),
      "K230 summary best throughput does not match raw data")
ratio_label = next(k for k in summary if k.startswith("较标量基线"))
ratio_text = summary[ratio_label]
expected_ratios = (f"{float(best['gflops'])/float(naive['gflops']):.2f}× / "
                   f"{float(best['gflops'])/float(autovec['gflops']):.2f}×")
check(ratio_text.startswith(expected_ratios), "K230 summary DGEMM ratios do not match raw data")
check("跨用例" in ratio_label + ratio_text and
      "160×160×160" in ratio_text and "131×126×117" in ratio_text,
      "K230 summary does not disclose the different DGEMM matrix shapes")
gains = []
for n in (128, 192, 256):
    base = next(r for r in linpack if r["variant"] == "baseline" and int(r["n"]) == n)
    tuned = next(r for r in linpack if r["variant"] == "tuned+pipe" and int(r["n"]) == n)
    gains.append(f"{float(tuned['gflops'])/float(base['gflops']):.2f}×")
linpack_text = next(v for k, v in summary.items() if k.startswith("Linpack 调优收益"))
check(linpack_text == " / ".join(gains), "K230 summary Linpack gains do not match raw data")
check(summary["配置空间最优/最差差距"] ==
      f"{float(best['gflops'])/float(worst['gflops']):.1f}×",
      "K230 summary configuration span does not match raw data")

hpl_rows = read_csv(ROOT / "hpl/results/summary.csv")
check(len(hpl_rows) == 2, f"official HPL summary row count: {len(hpl_rows)} != 2")
for r in hpl_rows:
    label = f"HPL {r['platform']} np={r['ranks']}"
    log = (ROOT / "hpl/results" / r["log"]).read_text(encoding="utf-8")
    check("HPLinpack 2.3" in log, f"{label}: missing official HPL 2.3 banner")
    check("1 tests completed and passed residual checks" in log,
          f"{label}: missing official passed-test count")
    check("0 tests completed and failed residual checks" in log,
          f"{label}: missing official zero-failure count")
    perf = re.search(r"^WR\S+\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"
                     r"([0-9.]+)\s+([0-9.eE+-]+)", log, re.MULTILINE)
    check(perf is not None, f"{label}: missing official performance row")
    if perf:
        for value, key in zip(perf.groups()[:4], ("N", "NB", "P", "Q")):
            check(int(value) == int(r[key]), f"{label}: {key} differs from official log")
        close(float(r["time_s"]), float(perf.group(5)), 1e-12,
              f"{label}: time differs from official log")
        close(float(r["gflops"]), float(perf.group(6)), 1e-12,
              f"{label}: GFLOPS differs from official log")
    residual = re.search(r"\)=\s*([0-9.eE+-]+)\s*\.+\s*PASSED", log)
    check(residual is not None, f"{label}: missing official PASSED residual")
    if residual:
        close(float(r["residual"]), float(residual.group(1)), 1e-12,
              f"{label}: residual differs from official log")

if failures:
    print(f"FAILED: {len(failures)} consistency error(s)")
    for failure in failures:
        print(f"- {failure}")
    sys.exit(1)
print("PASS: 93 cloud rows, 57 E8 comparisons, 89 K230 raw rows, and "
      f"{len(hpl_rows)} official HPL logs are consistent")
print(f"K230 best: {best['variant']} kc={best['kc']} = {best['gflops']} GFLOPS")
print(f"K230 Linpack gains N=128/192/256: {' / '.join(gains)}")
