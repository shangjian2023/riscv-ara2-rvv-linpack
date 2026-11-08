#!/usr/bin/env python3
"""Print concise, computed demo evidence from archived CSV and official logs."""
import csv
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def selected_local():
    rows = read_csv(ROOT / "apps_linpack_draft/results/local_linpack_summary.csv")
    for n in (128, 256):
        selected = [r for r in rows if int(r["N"]) == n and int(r["mr"]) == 8
                    and int(r["lmul"]) == 2 and r["profiled"] == "0"]
        baseline = next(r for r in selected if r["variant"] == "baseline")
        print(f"N={n} baseline: cycles={int(baseline['cycles']):,}, "
              f"util={baseline['util']}%, residual={baseline['resid']}")
        for variant in ("rvv_phases", "panel_v2"):
            matches = [r for r in selected if r["variant"] == variant]
            if not matches:
                continue
            row = matches[0]
            assert row["checksum"] == baseline["checksum"]
            assert row["resid"] == baseline["resid"]
            speedup = int(baseline["cycles"]) / int(row["cycles"])
            print(f"N={n} {variant}: cycles={int(row['cycles']):,}, "
                  f"util={row['util']}%, speedup={speedup:.2f}x, fingerprint= MATCH")


def official_hpl():
    repeats = read_csv(ROOT / "hpl/results/k230_np1_openblas_n4096_nb256_r3.csv")
    assert len(repeats) == 3 and all(r["result"] == "PASSED" for r in repeats)
    assert len({r["residual"] for r in repeats}) == 1
    values = [float(r["gflops"]) for r in repeats]
    print(f"K230 official HPL N=4096 NB=256: 3-run median={median(values):.4f} GFLOPS, "
          f"range={min(values):.4f}..{max(values):.4f}, all PASSED")
    rows = read_csv(ROOT / "hpl/results/summary.csv")
    for n, nb in ((8192, 256), (8192, 512)):
        row = next(r for r in rows if r["platform"].startswith("k230")
                   and int(r["N"]) == n and int(r["NB"]) == nb
                   and "OpenBLAS" in r["blas"])
        log = (ROOT / "hpl/results" / row["log"]).read_text(encoding="utf-8")
        assert "PASSED" in log and row["result"] == "PASSED"
        print(f"K230 official HPL N={n} NB={nb}: {row['gflops']} GFLOPS, "
              f"residual={row['residual']}, {row['result']}, log={row['log']}")


def main():
    print("== Ara2 RTL full-chain evidence ==")
    selected_local()
    print("== K230 official Netlib HPL 2.3 evidence ==")
    official_hpl()
    print("Evidence source: archived CSV and raw logs; no simulation values are generated here.")


if __name__ == "__main__":
    main()
