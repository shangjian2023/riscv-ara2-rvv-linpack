#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_e8_fixture.py - synthetic E8 test fixture (host-only, not for WSL).

Generates a fake rtl_collect.sh / e7_summarize.py output tree where every
"measured" number is derived from the REAL teammate model with a known
perturbation factor f:  meas_cycles = model_cycles * (1 + f).
e8_compare.py must then report err_cycles_pct = -f/(1+f)*100 exactly, which
makes the join math self-checking.

Usage:  python make_e8_fixture.py <path-to-ara2_model.py> <out-dir>
"""
import importlib.util
import math
import os
import sys

MODEL, OUT = sys.argv[1], os.path.join(sys.argv[2], "e8_test")

spec = importlib.util.spec_from_file_location("ara2_model", MODEL)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(lanes, var, n, mr=0, lmul=0, kc=0, pipe=0, nb=None, f=0.0,
        as_model=None):
    """Return (model_result, RES-line dict) for one synthetic measurement.

    as_model: force the generating model ("scalar" for E7 novec v2 rows,
    which e8_compare maps to the scalar model by design).
    """
    mc = mod.Ara2Config(lanes=lanes, freq_ghz=1.0)
    if as_model == "scalar" or var == "v0_scalar":
        res = mod.model_scalar_gemm(n, n, n, mc)
    elif var == "v2_autovec":
        res = mod.model_autovec_gemm(n, n, n, mc)
    elif var == "rvv":
        res = mod.model_rvv_dgemm(n, n, n, mod.KernelParams(mr, lmul, kc, pipe), mc)
    else:  # linpack
        res = mod.model_linpack(n, nb, mod.KernelParams(mr, lmul, kc, pipe), mc)
    cyc = res.cycles * (1 + f)
    flops = res.flops
    fpcyc = flops / cyc
    util = 100.0 * fpcyc / (2.0 * lanes)
    d = {"var": var, "mr": mr, "lmul": lmul, "kc": kc, "pipe": pipe, "N": n,
         "cycles": round(cyc), "fpcyc": round(fpcyc, 3), "util": round(util, 2),
         "_f": f, "_model_cycles": res.cycles, "_model_util": res.utilization * 100}
    if nb is not None:
        d["nb"] = nb
    return d


def res_line(d, phase):
    parts = [f"phase={phase}", f"var={d['var']}",
             f"mr={d['mr']}", f"lmul={d['lmul']}", f"kc={d['kc']}",
             f"pipe={d['pipe']}", f"N={d['N']}"]
    if "nb" in d:
        parts.append(f"nb={d['nb']}")
    parts += [f"cycles={d['cycles']}", f"fpcyc={d['fpcyc']:.3f}",
              f"util={d['util']:.2f}", "chk=0123456789abcdef"]
    return "RES," + ",".join(parts)


# ---- 4_lanes: one of each variant, assorted perturbations ---------------
rows4 = [
    row(4, "v0_scalar", 128, f=0.08),                    # err -7.407%
    row(4, "v2_autovec", 256, f=0.20),                   # err -16.667%
    row(4, "rvv", 256, mr=8, lmul=2, kc=128, pipe=0, f=-0.35),   # err +53.8%, big_err
    row(4, "linpack", 512, mr=8, lmul=2, kc=128, pipe=0, nb=64, f=0.15),
    row(4, "linpack", 512, mr=4, lmul=1, kc=64, pipe=0, nb=32, f=0.25),
]
# ---- 16_lanes: the model's "exactly peak" calibration point ------------
rows16 = [
    row(16, "v2_autovec", 256, f=0.10),
    # model says util=100%; measured 30% slower -> util 76.9% < 80:
    # this is exactly the "model ceiling" case the report must flag
    row(16, "rvv", 256, mr=8, lmul=2, kc=128, pipe=0, f=+0.30),
]

rtl = os.path.join(OUT, "rtl")
os.makedirs(os.path.join(rtl, "4_lanes"), exist_ok=True)
os.makedirs(os.path.join(rtl, "16_lanes"), exist_ok=True)
with open(os.path.join(rtl, "4_lanes", "res.csv"), "w") as fh:
    fh.write("CFG,lanes=4,vlen=4096,sweepN=256,linpackN=512,nbMax=64,reps=1\n")
    for d in rows4:
        fh.write(res_line(d, "lp" if d["var"] == "linpack" else "swp") + "\n")
with open(os.path.join(rtl, "16_lanes", "res.csv"), "w") as fh:
    fh.write("CFG,lanes=16,vlen=16384,sweepN=256,linpackN=512,nbMax=64,reps=1\n")
    for d in rows16:
        fh.write(res_line(d, "swp") + "\n")

# ---- fmatmul merged csv: anchors at 16 lanes + decoys --------------------
with open(os.path.join(rtl, "rtl_all.csv"), "w") as fh:
    fh.write("config,lanes,app,s,N,cycles,fpcyc,util,verified\n")
    for s, u in [(4, 3.1), (8, 6.2), (16, 12.5), (32, 70.1), (64, 88.3)]:
        cyc = round(2 * s ** 3 / (u / 100.0 * 32.0))
        fh.write(f"16_lanes,16,fmatmul,{s},{s},{cyc},"
                 f"{u / 100 * 32:.2f},{u},yes\n")
    for s, u in [(32, 22.0), (64, 30.5)]:  # wrong-lane decoys
        cyc = round(2 * s ** 3 / (u / 100.0 * 8.0))
        fh.write(f"4_lanes,4,fmatmul,{s},{s},{cyc},{u / 100 * 8:.2f},{u},yes\n")

# ---- e7 summary csv ------------------------------------------------------
e7rows = [
    row(4, "v2_autovec", 256, f=0.18),
    # novec twin: e8 maps it to the SCALAR model, so generate from there too
    row(4, "v2_autovec", 256, f=-0.05, as_model="scalar"),
    row(4, "rvv", 256, mr=8, lmul=2, kc=128, pipe=0, f=-0.10),
]
e7 = os.path.join(OUT, "e7")
os.makedirs(e7, exist_ok=True)
tags = ["clang-O3-fast-vec", "clang-O3-novec", "gcc-O3-fast-vec"]
with open(os.path.join(e7, "e7_summary.csv"), "w", newline="") as fh:
    fh.write("tag,lanes,phase,var,mr,lmul,kc,pipe,N,cycles,fpcyc,util,chk\n")
    for tag, d in zip(tags, e7rows):
        fh.write(f"{tag},{4},swp,{d['var']},{d['mr']},{d['lmul']},{d['kc']},"
                 f"{d['pipe']},{d['N']},{d['cycles']},{d['fpcyc']:.3f},"
                 f"{d['util']:.2f},deadbeef\n")

# ---- expected errors for the checker -------------------------------------
with open(os.path.join(OUT, "expected.csv"), "w") as fh:
    fh.write("source,var,lanes,N,nb,tag,f,expected_err_pct,model_util\n")
    src = ["rtl"] * 5 + ["rtl"] * 2 + ["e7"] * 3
    tags = [""] * 7 + tags
    for s, d, t in zip(src, rows4 + rows16 + e7rows, tags):
        lanes = 16 if d in rows16 else 4
        fh.write(f"{s},{d['var']},{lanes},{d['N']},{d.get('nb', '')},{t},"
                 f"{d['_f']},{-d['_f'] / (1 + d['_f']) * 100:.3f},"
                 f"{d['_model_util']:.2f}\n")

print(f"fixture written to {OUT}")
print("check with: python scripts/e8_compare.py --rtl-dir <rtl> --e7-dir <e7> "
      "--model <model> --out <out>  (then compare err_cycles_pct vs expected.csv)")
