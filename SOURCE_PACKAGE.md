# 源码与复现包说明

## 固定版本

- 远程仓库：https://github.com/shangjian2023/riscv-ara2-rvv-linpack
- 工作分支：`feat/cloud-priority`
- 源码ZIP由对应Git提交直接执行 `git archive` 生成；提交ID、包SHA-256和视频SHA-256记录在同目录的 `SHA256SUMS.txt` 与 `RELEASE_MANIFEST.json` 中。
- ZIP内不包含 `.git`、本地密钥、云端凭据、教师/队友原始报告、可重建目标文件或视频分段。

## 一键核验已归档结果

在源码包根目录运行：

```bash
python -I apps_linpack_draft/scripts/validate_results.py
python -I demo/scripts/show_evidence.py
python -I apps_linpack_draft/scripts/summarize_local_linpack.py \
  apps_linpack_draft/results/local_rtl /tmp/local_linpack_summary.csv
```

第一条命令从原始日志重新核对周期、FLOP/cycle、利用率、残差、校验和及官方HPL输出。第二条打印视频采用的关键结果。第三条重新生成18条本地RTL求解结果；可用 `diff` 与包内 `apps_linpack_draft/results/local_linpack_summary.csv` 对比。

## 主机冒烟测试

需要支持C99的GCC和数学库：

```bash
gcc -O2 -Wall -Wextra \
  -I apps_linpack_draft/test_host -I apps_linpack_draft/linpack/kernel \
  -DDGEMM_SWEEP_N=132 -DLINPACK_N=132 \
  -o /tmp/linpack_host \
  apps_linpack_draft/linpack/main.c \
  apps_linpack_draft/linpack/kernel/lp_data.c \
  apps_linpack_draft/linpack/kernel/dgemm_naive.c \
  apps_linpack_draft/linpack/kernel/linpack.c \
  apps_linpack_draft/test_host/stub_dgemm_rvv.c -lm
/tmp/linpack_host
```

成功标志为 `CHECK_PHASE,PASS,fails=0` 和 `DONE,fails=0`。主机测试使用计时桩，输出的周期不是RTL性能数据。

## Ara2 RTL复现

1. 准备Ara2/Verilator模型和RISC-V裸机工具链，按 `apps_linpack_draft/README.md` 将应用放入Ara工作区。
2. 通过 `ARA_ROOT`、`APP_DIR`、`MODEL_DIR`、`RTLC_GCC_PREFIX`、`RTLC_SHIM` 和 `OUT_ROOT` 指定本机路径；不要把云端路径写死到脚本。
3. 使用以下脚本分别运行基线、分阶段计时和优化版本：

```bash
bash apps_linpack_draft/scripts/rtl_linpack_chain.sh 128
bash apps_linpack_draft/scripts/rtl_linpack_profile.sh 128
bash apps_linpack_draft/scripts/rtl_linpack_opt.sh 128
```

`LP_OPT_SCALAR_PHASES=1` 开启第一轮行更新与三角求解优化，再加 `LP_OPT_PANEL_V2=1` 开启第二轮主元行复用。`LP_PROFILE=1` 只增加分阶段计时；带计时和不带计时的结果分开比较。原始配置、编译参数、仿真日志、反汇编和SHA-256保留在 `apps_linpack_draft/results/local_rtl/`；ELF和目标文件可按脚本重建，因此不进入源码包。

## K230与官方Netlib HPL 2.3

官方HPL来源、依赖版本、构建参数、输入文件、原始日志和串口复现命令见：

- `hpl/README.md`
- `hpl/PROVENANCE.md`
- `hpl/scripts/k230_serial.ps1`

K230结果均为CanMV-K230/C908上的单Linux CPU、单MPI rank结果。官方HPL只指未修改算法源码的Netlib HPL 2.3；`apps_linpack_draft/` 是自研Linpack求解程序，两者分别呈现。

## 报告图表与视频

- 最终报告：`report_archive/2026-11-08/参赛项目设计报告-融合队友版-修订稿-v5.docx`
- 绘图入口：`report_archive/2026-11-08/figures/make_figures.py`
- 图表数据与PNG/SVG/PDF均保留在同一目录。
- Demo分镜、配音稿和构建脚本位于 `demo/`。重新生成图页需要Pillow，视频合成需要FFmpeg/FFprobe；实板原始视频与可重建分段不进入源码ZIP，最终MP4作为独立交付文件提供。

在带中文字体的WSL环境中可重绘报告图：

```bash
python3 report_archive/2026-11-08/figures/make_figures.py
python3 -I demo/scripts/render_slides.py
```

## 校验文件

Windows PowerShell：

```powershell
Get-FileHash -Algorithm SHA256 .\riscv-ara2-rvv-linpack-src-<commit>.zip
Get-Content .\SHA256SUMS.txt
```

校验值必须与发布清单一致。若需核对文件清单，可在仓库中执行 `git ls-tree -r --name-only <commit>`，并与ZIP内的路径逐项对比。
