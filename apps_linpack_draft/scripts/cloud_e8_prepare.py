#!/usr/bin/env python3
"""Convert cloud_all.csv into e8_compare.py's rtl_collect directory layout."""
import csv
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: cloud_e8_prepare.py CLOUD_CSV OUT_RTL_DIR")
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*_lanes/res.csv"):
        old.unlink()
    fmatmul = []
    res_count = 0
    with src.open(newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        lanes = row["config"].split("_")[0]
        if row["phase"] == "e0":
            # The 64³ job already includes the 4/8/16/32³ prefix runs.
            if not row["job"].endswith("_64"):
                continue
            n = int(row["N"])
            cycles = int(row["cycles"])
            fpcyc = 2.0 * n**3 / cycles
            util = 100.0 * fpcyc / (2.0 * int(lanes))
            fmatmul.append({
                "config": row["config"], "lanes": lanes, "app": "fmatmul",
                "s": n, "N": n, "cycles": cycles,
                "fpcyc": f"{fpcyc:.6f}", "util": f"{util:.2f}",
                "verified": "cloud",
            })
            continue
        cfg_dir = out / row["config"]
        cfg_dir.mkdir(exist_ok=True)
        with (cfg_dir / "res.csv").open("a", newline="") as f:
            fields = [f"phase={row['phase']}", f"var={row['var']}"]
            if row["job"].startswith("e7_"):
                fields.append(f"tag={row['job']}")
            if row["var"] in ("rvv", "linpack"):
                fields += [f"mr={row['mr']}", f"lmul={row['lmul']}",
                           f"kc={row['kc']}", f"pipe={row['pipe']}"]
            fields += [f"N={row['N']}", f"cycles={row['cycles']}",
                       f"fpcyc={row['fpcyc']}", f"util={row['util']}",
                       f"chk={row['chk']}"]
            f.write("RES," + ",".join(fields) + "\n")
            res_count += 1
    with (out / "rtl_all.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fmatmul[0]))
        writer.writeheader()
        writer.writerows(fmatmul)
    print(f"prepared {len(fmatmul)} fmatmul rows and {res_count} RES rows -> {out}")


if __name__ == "__main__":
    main()
