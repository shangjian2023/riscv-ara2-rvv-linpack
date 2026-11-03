#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_instr.py - 模型预测的动态指令计数 vs 插桩实测（-DINSTR_COUNT 构建）。
内核循环全部确定性 -> 计数可解析精确预测；两者应逐项一致（误差 0）。"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ara2_model import Ara2Config, KernelParams, _ceil_div

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")


def predict(n, m, k, mr, lmul, kc, pipe, vlen):
    """语义级动态计数（与 src/dgemm_rvv.c 插桩点一一对应）。
    vlmax_e64m1 = vlen/64；LMUL 组向量长 vlmax = vlen/64*lmul 元素。"""
    vlmax_grp = vlen // 64 * lmul
    j_blocks = _ceil_div(m, vlmax_grp)
    i_blocks = n // mr
    i_tail = n % mr
    k_blocks = _ceil_div(k, kc)
    fma = load = store = move = scalar = 0
    for kb in range(k_blocks):
        kcq = min(kc, k - kb * kc)
        # full MR blocks
        fma += j_blocks * i_blocks * kcq * mr
        load += j_blocks * i_blocks * (kcq + mr)        # B per k + C per kernel
        store += j_blocks * i_blocks * mr
        if pipe:
            move += j_blocks * i_blocks * (kcq - 1 if kcq > 0 else 0)
        scalar += j_blocks * i_blocks * kcq * mr        # A-panel packing loads
        # i-tail rows (MR=1)
        fma += j_blocks * i_tail * kcq
        load += j_blocks * i_tail * (kcq + 1)
        store += j_blocks * i_tail
        scalar += j_blocks * i_tail * kcq
    return dict(vec_fma=fma, vec_load=load, vec_store=store, vec_move=move,
                scalar_load=scalar)


def main():
    cases = []
    for vlen in (256, 512):
        path = os.path.join(RES, f"instr_vlen{vlen}.csv")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for row in csv.DictReader(f):
                cases.append((vlen, row))
    rows = []
    all_ok = True
    for vlen, row in cases:
        mr, lmul = int(row["config"].split("_")[0][2:]), int(row["config"].split("_")[1][1:])
        kc, pipe = int(row["config"].split("_")[2][2:]), int(row["config"].split("_")[3][1:])
        n, m, k = 96, 80, 64
        p = predict(n, m, k, mr, lmul, kc, pipe, vlen)
        line = [f"{row['config']}@VLEN{vlen}"]
        ok = True
        for key in ("vec_fma", "vec_load", "vec_store", "vec_move", "scalar_load"):
            got, exp = int(row[key]), p[key]
            match = got == exp
            ok &= match
            line.append(f"{key}:测{got}/模{exp}{'✓' if match else '✗'}")
        all_ok &= ok
        rows.append([row["config"], vlen,
                     int(row["vec_fma"]), p["vec_fma"],
                     int(row["vec_load"]), p["vec_load"],
                     int(row["vec_store"]), p["vec_store"],
                     int(row["vec_move"]), p["vec_move"],
                     int(row["scalar_load"]), p["scalar_load"],
                     "一致" if ok else "不一致"])
        print(" ".join(line))
    with open(os.path.join(RES, "e7_instr_validation.csv"), "w",
              newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["config", "VLEN", "fma实测", "fma模型", "load实测", "load模型",
                    "store实测", "store模型", "move实测", "move模型",
                    "scalar实测", "scalar模型", "结论"])
        w.writerows(rows)
    print("ALL MATCH" if all_ok else "MISMATCH FOUND")


if __name__ == "__main__":
    main()
