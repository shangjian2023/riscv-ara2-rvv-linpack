#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e7_summarize.py - aggregate E7 (compiler comparison) results.

Inputs  (produced by e7_run.sh):  <dir>/<tag>/{res.csv,linpack.dump,build.log,sim.log}
Outputs (in <dir>):               e7_summary.csv, e7_report.md

Per combo it joins
  * RTL cycles from the RES lines (v0 scalar / v2 auto-vectorized /
    hand-written rvv mr4m1 + mr8m2), and
  * static codegen evidence from the objdump:
      - dgemm_naive   : vector instruction count (must be 0, else the
                        "scalar forced" control leaked)
      - dgemm_blocked : vfmacc count -> did auto-vectorization fire?
      - dgemm_mr8_m2_p0: total instructions, vector instructions, and
                        sp-relative accesses (VRF-spill proxy) -> shows how
                        each compiler allocates the vector register file

Works with both GNU and LLVM objdump formats (mnemonic = first token after
the address and the hex byte pairs).
"""
import argparse
import csv
import os
import re

# Instruction lines: "<addr>:\t<bytes>\t<mnemonic> <operands>". GNU objdump
# prints bytes without internal spaces ("02b74503", "6b05"), LLVM prints
# space-separated pairs ("02 d7 65 57") - accept both. The byte group is
# greedy over [hex-pair + optional whitespace]; it stops at the first token
# that cannot be a hex pair, which is always the mnemonic (hex-looking
# mnemonics like "add" are saved by the mandatory whitespace separator).
INSN_RE = re.compile(
    r"^\s*[0-9a-f]+:\s+(?:[0-9a-f]{2}\s*)+([a-z][a-z0-9._]*)")
SYM_RE = re.compile(r"^[0-9a-f]*\s*<([^>]+)>:")
V_MNEMONIC = re.compile(
    r"^v(setvl|setivli|setvli|fmacc|fmadd|fmsac|fnmsac|macc|madd|nmsub|nmacc"
    r"|le\d+\.?[a-z]*|lse\d+|se\d+\.?[a-z]*|sse\d+|lux[a-z]*|sox[a-z]*"
    r"|mv[a-z0-9.]*|merge|slide[a-z]*|rgather[a-z]*|fadd|fsub|fmul|fdiv"
    r"|fsqrt|add|sub|mul|xor|and|or|red[a-z]*|first|msbf|mfgt|f[a-z]+)"
)

SYMBOLS = ("dgemm_naive", "dgemm_blocked", "dgemm_mr8_m2_p0", "dgemm_mr4_m1_p0")


def parse_dump(path):
    """Return {symbol: {insns, vec, vfmacc, sp}} for the symbols we care about."""
    stats = {}
    if not os.path.isfile(path):
        return stats
    cur = None
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = SYM_RE.match(line)
            if m:
                name = m.group(1)
                cur = name if name in SYMBOLS else None
                if cur and cur not in stats:
                    stats[cur] = {"insns": 0, "vec": 0, "vfmacc": 0, "sp": 0}
                continue
            if cur is None:
                continue
            mi = INSN_RE.match(line)
            if mi:
                mn = mi.group(1)
                stats[cur]["insns"] += 1
                if V_MNEMONIC.match(mn):
                    stats[cur]["vec"] += 1
                    if mn.startswith("vfmacc"):
                        stats[cur]["vfmacc"] += 1
            if "(sp)" in line:
                stats[cur]["sp"] += 1
    return stats


def parse_res(path):
    """Return (cfg, rows) where rows map (var,mr,lmul,kc,pipe) -> dict."""
    rows, cfg = {}, None
    if not os.path.isfile(path):
        return cfg, rows
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("CFG,"):
                cfg = dict(kv.split("=", 1) for kv in line[4:].split(",") if "=" in kv)
            elif line.startswith("RES,"):
                d = dict(kv.split("=", 1) for kv in line[4:].split(",") if "=" in kv)
                key = (d.get("var"), d.get("mr"), d.get("lmul"),
                       d.get("kc"), d.get("pipe"))
                rows[key] = d
    return cfg, rows


def num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="e7 output directory")
    args = ap.parse_args()

    combos = sorted(d for d in os.listdir(args.dir)
                    if os.path.isdir(os.path.join(args.dir, d)))

    summary = []   # flat rows
    per_combo = {}  # tag -> {cfg, rows, dump}
    for tag in combos:
        base = os.path.join(args.dir, tag)
        cfg, rows = parse_res(os.path.join(base, "res.csv"))
        dump = parse_dump(os.path.join(base, "linpack.dump"))
        per_combo[tag] = {"cfg": cfg, "rows": rows, "dump": dump}
        for key, r in rows.items():
            summary.append({
                "tag": tag,
                "lanes": (cfg or {}).get("lanes", ""),
                "phase": r.get("phase"), "var": r.get("var"),
                "mr": r.get("mr"), "lmul": r.get("lmul"),
                "kc": r.get("kc"), "pipe": r.get("pipe"),
                "N": r.get("N"), "cycles": r.get("cycles"),
                "fpcyc": r.get("fpcyc"), "util": r.get("util"),
                "chk": r.get("chk"),
            })

    with open(os.path.join(args.dir, "e7_summary.csv"), "w",
              newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=[
            "tag", "lanes", "phase", "var", "mr", "lmul", "kc", "pipe",
            "N", "cycles", "fpcyc", "util", "chk"])
        w.writeheader()
        w.writerows(summary)

    # ------------------------------------------------------------- report
    rep = ["# E7 编译器对比 — RTL 实测汇总", ""]

    # v2 auto-vectorization: the main event
    rep += ["## v2 自动向量化(核心对比)", "",
            "| 编译/flags | v2 fpcyc | v2 cycles@N | v2 向量化? (vfmacc) | v2 vs 本组 novec | v0 fpcyc | v2/v0 加速比 |",
            "|---|---|---|---|---|---|---|"]
    for tag in combos:
        pc = per_combo[tag]
        v2 = pc["rows"].get(("v2_autovec", "0", "0", "0", "0"))
        v0 = pc["rows"].get(("v0_scalar", "0", "0", "0", "0"))
        if not v2:
            rep.append(f"| {tag} | (build/run failed) | | | | | |")
            continue
        vfm = pc["dump"].get("dgemm_blocked", {}).get("vfmacc", 0)
        f2 = num(v2.get("fpcyc"))
        f0 = num(v0.get("fpcyc")) if v0 else 0.0
        # find the novec twin of the same compiler for the delta
        twin = tag.replace("fast-vec", "novec")
        twin_f = num(per_combo.get(twin, {}).get("rows", {})
                     .get(("v2_autovec", "0", "0", "0", "0"), {}).get("fpcyc"))
        delta = f"{f2 / twin_f:.2f}x" if twin_f > 0 and twin != tag else "-"
        speedup = f"{f2 / f0:.2f}x" if f0 > 0 else "-"
        rep.append(f"| {tag} | {f2:.2f} | {v2.get('cycles')}@N={v2.get('N')} "
                   f"| {'YES' if vfm > 0 else 'no'} ({vfm}) | {delta} "
                   f"| {f0:.2f} | {speedup} |")

    # hand-written kernel codegen across compilers
    rep += ["", "## 手写内核 codegen(mr8m2, 定时 mr8m2)", "",
            "| 编译/flags | mr8m2 fpcyc | util% | 总指令 | 向量指令 | sp 访问(溢出代理) |",
            "|---|---|---|---|---|---|"]
    for tag in combos:
        pc = per_combo[tag]
        r8 = pc["rows"].get(("rvv", "8", "2", "128", "0"))
        d = pc["dump"].get("dgemm_mr8_m2_p0", {})
        if not r8:
            rep.append(f"| {tag} | (missing) | | {d.get('insns', '-')} "
                       f"| {d.get('vec', '-')} | {d.get('sp', '-')} |")
            continue
        rep.append(f"| {tag} | {num(r8.get('fpcyc')):.2f} | {r8.get('util')} "
                   f"| {d.get('insns', '-')} | {d.get('vec', '-')} | {d.get('sp', '-')} |")

    # controls and invariants
    rep += ["", "## 控制项与不变量校验", ""]
    ok_all = True
    for tag in combos:
        pc = per_combo[tag]
        nv = pc["dump"].get("dgemm_naive", {}).get("vec", None)
        if nv is None:
            continue
        status = "OK" if nv == 0 else f"LEAK ({nv} vector insns!)"
        if nv != 0:
            ok_all = False
        rep.append(f"- v0 标量控制 @ {tag}: {status}")
    # bit-exactness of intrinsic kernels across compilers
    chks = {}
    for tag in combos:
        r8 = per_combo[tag]["rows"].get(("rvv", "8", "2", "128", "0"))
        if r8:
            chks.setdefault(r8.get("chk"), []).append(tag)
    if chks:
        rep.append(f"- mr8m2 结果指纹跨编译器: "
                   f"{'一致 ✓' if len(chks) == 1 else '不一致 ✗'} "
                   f"({len(chks)} 个不同值)")
    rep.append("- v2 指纹在 vec/novec 间允许不同(浮点重结合),跨编译器 novec 组应一致")

    # auto takeaways
    rep += ["", "## 自动结论(供报告引用)", ""]
    v2rank = []
    for tag in combos:
        r = per_combo[tag]["rows"].get(("v2_autovec", "0", "0", "0", "0"))
        if r:
            v2rank.append((num(r["fpcyc"]), tag))
    if v2rank:
        v2rank.sort(reverse=True)
        rep.append(f"- v2 自动向量化最优: **{v2rank[0][1]}** "
                   f"({v2rank[0][0]:.2f} FLOP/cycle),最差: {v2rank[-1][1]} "
                   f"({v2rank[-1][0]:.2f}),差距 {v2rank[0][0] / max(v2rank[-1][0], 1e-9):.2f}x")
    krank = []
    for tag in combos:
        r = per_combo[tag]["rows"].get(("rvv", "8", "2", "128", "0"))
        if r:
            krank.append((num(r["fpcyc"]), tag,
                          per_combo[tag]["dump"].get("dgemm_mr8_m2_p0", {}).get("sp", "-")))
    if krank:
        krank.sort(reverse=True)
        rep.append(f"- 手写内核最优: **{krank[0][1]}** ({krank[0][0]:.2f} FLOP/cycle);"
                   f"各编译器 sp 访问: " + ", ".join(f"{t}={s}" for _, t, s in krank))
        rep.append("- 若不同编译器 sp 访问数差异大,即为『编译器寄存器分配对 VRF 溢出的影响』"
                   "的直接证据(初稿只在一个编译器上看过这一点)")
    if not ok_all:
        rep.append("- ⚠ v0 出现向量指令:某组合的禁向量化控制失效,该组合数据需剔除")

    out_md = os.path.join(args.dir, "e7_report.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    print(f"[e7] summary csv : {os.path.join(args.dir, 'e7_summary.csv')}")
    print(f"[e7] report     : {out_md}")


if __name__ == "__main__":
    main()
