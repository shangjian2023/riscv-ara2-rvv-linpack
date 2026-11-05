#!/usr/bin/env python3
"""Collect RES and fmatmul rows from recovered cloud sim.log directories."""
import csv
import re
import sys
from pathlib import Path

HEADER = ["job", "config", "phase", "var", "mr", "lmul", "kc", "pipe",
          "N", "cycles", "fpcyc", "util", "chk"]
RES_RE = re.compile(
    r"^RES,phase=(\w+),var=([\w.]+)"
    r"(?:,mr=(\d+),lmul=(\d+),kc=(\d+),pipe=(\d+))?"
    r",N=(\d+)(?:,nb=(\d+))?,cycles=(\d+),fpcyc=([\d.]+),util=([\d.]+)",
    re.M,
)


def collect(out: Path):
    rows = []
    for wd in sorted(p for p in out.iterdir() if p.is_dir()):
        log = wd / "sim.log"
        if not log.is_file():
            continue
        name = wd.name
        parts = name.split("_")
        cfg = f"{parts[1]}_lanes" if len(parts) > 2 else "?"
        txt = log.read_text(errors="ignore")
        for m in RES_RE.finditer(txt):
            p, var, mr, lm, kc, pi, n, _nb, cyc, fp, ut = m.groups()
            rows.append([name, cfg, p, var, mr or 0, lm or 0, kc or 0,
                         pi or 0, n, cyc, fp, ut, ""])
        size = None
        for line in txt.splitlines():
            m = re.search(r"Calculating a \((\d+) x ", line)
            if m:
                size = m.group(1)
                continue
            m = re.search(r"execution took (\d+) cycles", line)
            if m and size:
                rows.append([name, cfg, "e0", "fmatmul", 0, 0, 0, 0,
                             size, m.group(1), "", "", ""])
    return rows


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: cloud_collect.py OUT_A OUT_16 CSV")
    rows = collect(Path(sys.argv[1])) + collect(Path(sys.argv[2]))
    rows.sort(key=lambda r: (r[0], r[2], r[3], int(r[4]), int(r[5]), int(r[8])))
    csv_path = Path(sys.argv[3])
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(rows)
    print(f"collected {len(rows)} rows -> {csv_path}")


if __name__ == "__main__":
    main()
