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

for fair_name in ("k230_fair.csv", "k230_fair_packb.csv"):
    fair = read_csv(K230_DIR / fair_name)
    check(len(fair) == 248, f"{fair_name}: row count {len(fair)} != 248")
    check(all(float(r["max_diff"]) == 0.0 for r in fair),
          f"{fair_name}: DGEMM differs from scalar reference")
    for n, reps in ((160, 15), (256, 13), (512, 9), (1024, 5)):
        for variant in ("naive_scalar", "blocked_autovec", "rvv_mr2_m8_p1", "rvv_mr8_m2_p1"):
            selected = [r for r in fair if r["section"] == "raw" and
                        r["variant"] == variant and int(r["n"]) == n]
            check(len(selected) == reps,
                  f"{fair_name}: {variant} N={n} repeat count != {reps}")

packed = read_csv(K230_DIR / "k230_board_packb_fair.csv")
check(Counter(r["section"] for r in packed) == {"check": 28, "sweep": 52, "linpack": 12},
      "B-packed full K230 section counts are not 28/52/12")
check(all(r["ok"] == "1" for r in packed), "B-packed K230 contains a failed check")
for n in (128, 192, 256):
    rows = [r for r in packed if r["section"] == "linpack" and int(r["n"]) == n]
    check(len(rows) == 4, f"B-packed Linpack N={n}: expected four same-input variants")
    check(len({r["max_diff"] for r in rows}) == 1,
          f"B-packed Linpack N={n}: variants did not use the same matrix")

hpl_rows = read_csv(ROOT / "hpl/results/summary.csv")
check(len(hpl_rows) == 7, f"official HPL summary row count: {len(hpl_rows)} != 7")
for r in hpl_rows:
    label = f"HPL {r['platform']} np={r['ranks']} N={r['N']} NB={r['NB']}"
    check(r["result"] == "PASSED", f"{label}: summary result is not PASSED")
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

repeat_name = "k230_np1_openblas_n4096_nb256_r3"
repeat_log = (ROOT / f"hpl/results/{repeat_name}.log").read_text(encoding="utf-8")
repeat_rows = read_csv(ROOT / f"hpl/results/{repeat_name}.csv")
repeat_perf = re.findall(
    r"^WR\S+\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"
    r"([0-9.]+)\s+([0-9.eE+-]+)", repeat_log, re.MULTILINE)
repeat_resid = re.findall(r"\)=\s*([0-9.eE+-]+)\s*\.+\s*PASSED", repeat_log)
check(len(repeat_rows) == len(repeat_perf) == len(repeat_resid) == 3,
      "official HPL repeat series must contain three matching runs")
check(repeat_log.count("1 tests completed and passed residual checks") == 3 and
      repeat_log.count("0 tests completed and failed residual checks") == 3,
      "official HPL repeat series does not contain three independent PASSED summaries")
for i, (r, perf, residual) in enumerate(zip(repeat_rows, repeat_perf, repeat_resid), 1):
    check(int(r["repetition"]) == i, f"HPL repeat {i}: incorrect repetition index")
    check(r["result"] == "PASSED", f"HPL repeat {i}: result is not PASSED")
    for value, key in zip(perf[:4], ("N", "NB", "P", "Q")):
        check(int(value) == int(r[key]), f"HPL repeat {i}: {key} differs from raw log")
    close(float(r["time_s"]), float(perf[4]), 1e-12,
          f"HPL repeat {i}: time differs from raw log")
    close(float(r["gflops"]), float(perf[5]), 1e-12,
          f"HPL repeat {i}: GFLOPS differs from raw log")
    close(float(r["residual"]), float(residual), 1e-12,
          f"HPL repeat {i}: residual differs from raw log")

if failures:
    print(f"FAILED: {len(failures)} consistency error(s)")
    for failure in failures:
        print(f"- {failure}")
    sys.exit(1)
print("PASS: 93 cloud rows, 57 E8 comparisons, 89 historical K230 rows, "
      "496 fair DGEMM rows, 92 B-packed full rows, "
      f"{len(hpl_rows)} official HPL logs, and {len(repeat_rows)} "
      "official HPL repeat runs are consistent")
print(f"K230 best: {best['variant']} kc={best['kc']} = {best['gflops']} GFLOPS")
print(f"K230 Linpack gains N=128/192/256: {' / '.join(gains)}")
