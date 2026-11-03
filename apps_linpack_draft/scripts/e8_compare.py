#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e8_compare.py - E8: teammate's analytical model (ara2_model.py) vs RTL
measurements, side by side.

Inputs:
  --rtl-dir  <ara>/results/rtl   rtl_collect.sh output:
                rtl_all.csv (fmatmul rows) + <config>/res.csv (RES lines)
  --e7-dir   <ara>/results/e7    optional, e7_summarize.py's e7_summary.csv
  --model    path/to/ara2_model.py   teammate's model (ARA2_MODEL env also
                honored; searched, not required - without it you still get
                the measured-only tables)

Mapping measured rows -> model calls (all cycles/util are frequency-free,
both sides define util = fpcyc / (2*lanes)):
    v0_scalar   -> model_scalar_gemm(N,N,N)
    v2_autovec  -> model_autovec_gemm(N,N,N)
                   (E7 *novec* combos: the blocked kernel is scalar there,
                    mapped to model_scalar_gemm, flagged approx-blocked-scalar)
    rvv         -> model_rvv_dgemm(N,N,N, KernelParams(mr,lmul,kc,pipe))
                   k_unroll assumed 2 (model default; E7 dumps can refine)
    linpack     -> model_linpack(N, nb, KernelParams(...))

Outputs (in --out, default = --rtl-dir):
    e8_error.csv    per-row joined table
    e8_report.md    anchor table / per-variant error stats / auto findings
"""
import argparse
import csv
import importlib.util
import os
import sys

PAPER_ANCHORS = {32: 76.0, 64: 94.0}  # Ara2 paper, fmatmul FP64 @ 16 lanes

# ---------------------------------------------------------------- model load


def load_model(path):
    spec = importlib.util.spec_from_file_location("ara2_model", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # __main__ guard: self-check stays silent
    return mod


def find_model(explicit):
    cands = []
    if explicit:
        cands.append(explicit)
    if os.environ.get("ARA2_MODEL"):
        cands.append(os.environ["ARA2_MODEL"])
    cands += [
        os.path.join(os.environ.get("ARA_ROOT", os.getcwd()), "..",
                     "linpack-ara2", "sim", "ara2_model.py"),
        os.path.join(os.getcwd(), "sim", "ara2_model.py"),
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return os.path.normpath(c)
    return None


# ---------------------------------------------------------------- input read


def read_rtl_all(path):
    """fmatmul rows from rtl_collect.sh's merged csv."""
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("app") == "fmatmul":
                rows.append(r)
    return rows


def parse_kv_line(line):
    return dict(kv.split("=", 1) for kv in line.split(",") if "=" in kv)


def read_res_dir(rtldir):
    """RES rows from <config>/res.csv (fall back to <config>/linpack.log)."""
    out = []
    if not os.path.isdir(rtldir):
        return out
    for cfg in sorted(os.listdir(rtldir)):
        base = os.path.join(rtldir, cfg)
        if not os.path.isdir(base):
            continue
        lanes = cfg.split("_")[0]
        src = None
        for name in ("res.csv", "linpack.log"):
            p = os.path.join(base, name)
            if os.path.isfile(p):
                src = p
                break
        if not src:
            continue
        with open(src, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("RES,"):
                    d = parse_kv_line(line[4:])
                    d["config"] = cfg
                    d["lanes"] = lanes
                    out.append(d)
    return out


def read_e7(e7dir):
    rows = []
    p = os.path.join(e7dir, "e7_summary.csv")
    if not os.path.isfile(p):
        return rows
    with open(p, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("cycles"):
                rows.append(r)
    return rows


def num(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- row -> model


def predict(mod, row, source):
    """Return (ModelResult|None, label, flag) for one measured row."""
    var = row.get("var")
    n = int(num(row.get("N"), 0) or 0)
    lanes = int(num(row.get("lanes"), 0) or 0)
    if not (var and n and lanes):
        return None, var, "unmapped"
    mc = mod.Ara2Config(lanes=lanes, freq_ghz=1.0)  # cycles/util are freq-free
    flag = ""
    if var == "v0_scalar":
        return mod.model_scalar_gemm(n, n, n, mc), "model_scalar_gemm", flag
    if var == "v2_autovec":
        if source == "e7" and "novec" in row.get("tag", ""):
            # control build: blocked kernel compiled scalar -> scalar model
            return (mod.model_scalar_gemm(n, n, n, mc),
                    "model_scalar_gemm(approx: blocked-scalar)", "approx")
        return mod.model_autovec_gemm(n, n, n, mc), "model_autovec_gemm", flag
    if var == "rvv":
        kp = mod.KernelParams(
            mr=int(num(row.get("mr"), 8) or 8),
            lmul=int(num(row.get("lmul"), 2) or 2),
            kc=int(num(row.get("kc"), 128) or 128),
            pipe=int(num(row.get("pipe"), 0) or 0),
            k_unroll=2)  # documented assumption; refine from E7 dumps
        return (mod.model_rvv_dgemm(n, n, n, kp, mc),
                f"model_rvv_dgemm(mr={kp.mr},lmul={kp.lmul},kc={kp.kc},p={kp.pipe})",
                flag)
    if var == "linpack":
        kp = mod.KernelParams(
            mr=int(num(row.get("mr"), 8) or 8),
            lmul=int(num(row.get("lmul"), 2) or 2),
            kc=int(num(row.get("kc"), 128) or 128),
            pipe=int(num(row.get("pipe"), 0) or 0))
        nb = int(num(row.get("nb"), 64) or 64)
        return (mod.model_linpack(n, nb, kp, mc),
                f"model_linpack(nb={nb})", flag)
    return None, var, "unmapped"


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtl-dir", required=True, help="rtl_collect.sh output dir")
    ap.add_argument("--e7-dir", default=None, help="e7 output dir (optional)")
    ap.add_argument("--model", default=None, help="path to ara2_model.py")
    ap.add_argument("--out", default=None, help="output dir (default: --rtl-dir)")
    args = ap.parse_args()

    model_path = find_model(args.model)
    mod = load_model(model_path) if model_path else None
    outdir = args.out or args.rtl_dir
    os.makedirs(outdir, exist_ok=True)

    fm_rows = read_rtl_all(os.path.join(args.rtl_dir, "rtl_all.csv"))
    res_rows = read_res_dir(args.rtl_dir)
    e7_rows = read_e7(args.e7_dir) if args.e7_dir else []

    joined = []   # per measured row
    for r in res_rows:
        r["_source"] = "rtl"
        joined.append(r)
    for r in e7_rows:
        r["_source"] = "e7"
        joined.append(r)

    # ------------------------------------------------------------- join
    table = []
    for r in joined:
        meas_cyc = num(r.get("cycles"))
        meas_util = num(r.get("util"))
        entry = {
            "source": r["_source"], "config": r.get("config", ""),
            "lanes": r.get("lanes", ""), "tag": r.get("tag", ""),
            "phase": r.get("phase", ""), "var": r.get("var", ""),
            "mr": r.get("mr", ""), "lmul": r.get("lmul", ""),
            "kc": r.get("kc", ""), "pipe": r.get("pipe", ""),
            "N": r.get("N", ""), "nb": r.get("nb", ""),
            "meas_cycles": int(meas_cyc) if meas_cyc is not None else "",
            "meas_fpcyc": r.get("fpcyc", ""),
            "meas_util_pct": meas_util if meas_util is not None else "",
            "model_cycles": "", "model_util_pct": "", "err_cycles_pct": "",
            "delta_util_pp": "", "model": "", "model_bound": "", "flag": "",
        }
        if meas_cyc is None:
            entry["flag"] = "no_meas_cycles"
            table.append(entry)
            continue
        if mod is None:
            entry["flag"] = "no_model"
            table.append(entry)
            continue
        res, label, flag = predict(mod, r, r["_source"])
        entry["model"] = label
        if res is None:
            entry["flag"] = flag or "unmapped"
            table.append(entry)
            continue
        m_cyc, m_util = res.cycles, res.utilization * 100.0
        err = (m_cyc - meas_cyc) / meas_cyc * 100.0  # + : model slower/overest.
        entry["model_cycles"] = f"{m_cyc:.0f}"
        entry["model_util_pct"] = f"{m_util:.2f}"
        entry["err_cycles_pct"] = f"{err:+.1f}"
        if meas_util is not None:
            entry["delta_util_pp"] = f"{m_util - meas_util:+.2f}"
        entry["model_bound"] = res.breakdown.get("bound", "")
        flags = [flag] if flag else []
        if m_util >= 95.0 and meas_util is not None and meas_util < 80.0:
            flags.append("model_ceiling")
        if abs(err) > 30.0:
            flags.append("big_err")
        entry["flag"] = ";".join(flags)
        table.append(entry)

    cols = ["source", "config", "lanes", "tag", "phase", "var", "mr", "lmul",
            "kc", "pipe", "N", "nb", "meas_cycles", "meas_fpcyc",
            "meas_util_pct", "model_cycles", "model_util_pct",
            "err_cycles_pct", "delta_util_pp", "model", "model_bound", "flag"]
    csv_path = os.path.join(outdir, "e8_error.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(table)

    # ------------------------------------------------------------- report
    rep = ["# E8 — 模型 vs RTL 实测 误差分析", ""]
    rep.append(f"- 模型: {model_path or '**未找到**(仅输出实测表;用 --model 指定 ara2_model.py)'}")
    rep.append(f"- 实测行数: RTL {len(res_rows)} + E7 {len(e7_rows)}"
               f",fmatmul 行 {len(fm_rows)}")
    rep.append("")

    # -- E0 anchor table
    rep += ["## E0 论文锚点(官方 fmatmul,16 lanes)", "",
            "| s | 实测 util% | 论文 util% | Δ(pp) | 实测 cycles | FLOP/cycle |",
            "|---|---|---|---|---|---|"]
    anchor_hits = 0
    for r in fm_rows:
        s = int(num(r.get("s"), 0) or 0)
        if r.get("lanes") == "16" and s in PAPER_ANCHORS:
            u = num(r.get("util"))
            paper = PAPER_ANCHORS[s]
            if u is not None:
                anchor_hits += 1
                rep.append(f"| {s} | {u:.2f} | {paper:.0f} | {u - paper:+.1f} "
                           f"| {num(r.get('cycles'), 0):.0f} "
                           f"| {num(r.get('fpcyc'), 0):.2f} |")
    if anchor_hits == 0:
        rep.append("| (无 16-lane fmatmul 数据 — RTLC_CONFIGS 加 16_lanes 重跑) | | | | | |")
    else:
        rep += ["", "模型自身的锚点输出(model_rvv_dgemm, mr=4/lmul=1/kc=s, L=16):",
                "| s | 模型 util% | 论文 util% |", "|---|---|---|"]
        if mod:
            for s, paper in PAPER_ANCHORS.items():
                res = mod.model_rvv_dgemm(s, s, s, mod.KernelParams(4, 1, s),
                                          mod.Ara2Config(lanes=16, freq_ghz=1.0))
                rep.append(f"| {s} | {res.utilization * 100:.1f} | {paper:.0f} |")

    # -- per-row table
    rep += ["", "## 逐行误差(全部来源)", "",
            "| 来源 | config | tag | 变体 | N | 实测cyc | 模型cyc | 周期误差% "
            "| 实测util% | 模型util% | Δutil pp | 模型瓶颈 | flag |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in table:
        rep.append(
            f"| {e['source']} | {e['config'] or '-'} | {e['tag'] or '-'} "
            f"| {e['var']}"
            + (f"[{e['mr']},{e['lmul']},{e['kc']},p{e['pipe']}]"
               if e['var'] == 'rvv' else "")
            + (f",nb={e['nb']}" if e['nb'] else "")
            + f" | {e['N']} | {e['meas_cycles']} | {e['model_cycles'] or '-'} "
            f"| {e['err_cycles_pct'] or '-'} | {e['meas_util_pct']} "
            f"| {e['model_util_pct'] or '-'} | {e['delta_util_pp'] or '-'} "
            f"| {e['model_bound'] or '-'} | {e['flag'] or ''} |")

    # -- aggregate
    rep += ["", "## 按变体汇总", "",
            "| 变体 | 行数 | 平均\\|周期误差\\|% | 最大\\|周期误差\\|% "
            "| 模型高估行数 | model_ceiling 行数 |", "|---|---|---|---|---|---|"]
    groups = {}
    for e in table:
        if e["err_cycles_pct"]:
            groups.setdefault(e["var"], []).append(e)
    for var, es in sorted(groups.items()):
        errs = [abs(float(e["err_cycles_pct"])) for e in es]
        over = sum(1 for e in es if float(e["err_cycles_pct"]) > 0)
        ceil_n = sum(1 for e in es if "model_ceiling" in e["flag"])
        rep.append(f"| {var} | {len(es)} | {sum(errs) / len(errs):.1f} "
                   f"| {max(errs):.1f} | {over}/{len(es)} | {ceil_n} |")

    # -- auto findings
    rep += ["", "## 自动发现(供报告引用)", ""]
    ceil_rows = [e for e in table if "model_ceiling" in e["flag"]]
    if ceil_rows:
        rep.append(f"- **模型天花板未被实测复现**:{len(ceil_rows)} 行模型 util≥95% "
                   "而实测 <80%(初稿报告里的『接近 100% 峰值』即此类模型产物):")
        for e in ceil_rows[:8]:
            rep.append(f"  - {e['source']}/{e['config']}/{e['tag']} {e['var']}"
                       f"[{e['mr']},{e['lmul']},{e['kc']},p{e['pipe']}] N={e['N']}: "
                       f"模型 {e['model_util_pct']}% vs 实测 {e['meas_util_pct']}%")
    big = sorted((e for e in table if e["err_cycles_pct"]),
                 key=lambda e: -abs(float(e["err_cycles_pct"])))
    if big:
        e = big[0]
        rep.append(f"- 最大周期误差: {e['var']} N={e['N']} "
                   f"({e['source']}/{e['config']}/{e['tag']}): "
                   f"{e['err_cycles_pct']}% (模型 {e['model_cycles']} vs 实测 "
                   f"{e['meas_cycles']} cycles)")
    by_var_msg = ", ".join(
        f"{v}: 平均|err|={sum(abs(float(e['err_cycles_pct'])) for e in es) / len(es):.0f}%"
        for v, es in sorted(groups.items()))
    if by_var_msg:
        rep.append(f"- 各变体平均误差 — {by_var_msg}")

    rep += ["", "## 口径说明", "",
            "- 周期对比与频率无关(双方都用 mcycle 实测周期/模型周期);"
            "util 两侧同为 fpcyc/(2×lanes),初稿 E4 换频率不改 cycles 的问题在此规避",
            "- rvv 行的模型调用假定 k_unroll=2(模型默认;可用 E7 dump 实测修正)",
            "- E7 novec 组的 v2 映射到标量模型(分块标量内核,近似),已打 approx 标",
            "- linpack 实测 ROI = blocked_lu+lu_solve(不含残差计算);模型 solve "
            "项含残差 flops,~2N² 量级,N≥512 时影响 <2%",
            "- err% 为正 = 模型高估周期(即低估性能)"]

    md_path = os.path.join(outdir, "e8_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    print(f"[e8] joined csv : {csv_path}")
    print(f"[e8] report     : {md_path}")
    if mod is None:
        print("[e8] WARNING: ara2_model.py not found - measured-only output")
        sys.exit(3)


if __name__ == "__main__":
    main()
