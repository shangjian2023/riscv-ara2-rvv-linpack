import re, sys
log, cfg, lanes, allcsv = sys.argv[1:5]
rows = []
s = None
for line in open(log, encoding="utf-8", errors="ignore"):
    m = re.search(r"Calculating a \((\d+) x (\d+)\) x \((\d+) x (\d+)\)", line)
    if m:
        s = int(m.group(1))
        continue
    m = re.search(r"execution took (\d+) cycles", line)
    if m and s is not None:
        rows.append([s, m.group(1), None, None]); continue
    m = re.search(r"performance is ([\d.]+) FLOP/cycle \(([\d.]+)%", line)
    if m and rows and rows[-1][2] is None:
        rows[-1][2], rows[-1][3] = m.group(1), m.group(2)
    if "Passed." in line and rows:
        rows[-1].append("yes")
with open(allcsv, "a", encoding="utf-8") as f:
    for r in rows:
        if len(r) >= 4:
            f.write(f"{cfg},{lanes},fmatmul,{r[0]},{r[0]},{r[1]},{r[2]},{r[3]},"
                    f"{r[4] if len(r) > 4 else '?'}\n")
print(f"  fmatmul: {len(rows)} sizes parsed")
