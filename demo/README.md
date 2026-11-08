# 方案 Demo 制作说明

## 当前最终版

- 文件：`demo/build/demo_final_v4.mp4`；交付目录另存为 `deliverables/光明未来-RVV-Linpack-演示视频.mp4`。
- 规格：1920×1080、30 fps、H.264/AAC，220.233秒、9,758,090字节（约9.76 MB），48 kHz双声道。
- 封面：国防科技大学、光明未来队；李丞阳、马卓然、段智中；指导教师雷国庆。
- 保留两段K230实机拍摄：板卡特写与官方HPL `PASSED` 画面，实拍run id为 `20261108_221043`。
- 配音为本机中文TTS（Microsoft Huihui），中文字幕已烧录进画面。
- 最终MP4是独立交付文件，不进入Git源码提交；分镜、配音稿和构建脚本进入源码包。

## 新图版本内容

1. 项目标题与三项核心结果；
2. 三个研究问题；
3. 同源代码、分层实测路线；
4. 第二轮列分块优化与真实RVV反汇编；
5. 从原始日志重新计算的现场校验；
6. 128阶和256阶双面板优化路径图；
7. 128阶各求解阶段前后对比箭图；
8. K230官方HPL点线图；
9. K230板卡和官方 `PASSED` 实拍；
10. 项目价值与交付入口。

采用的新图均来自 `report_archive/2026-11-08/figures/`：

- `fig_panel_v2_evidence.png`
- `fig_fullchain_n128_n256.png`
- `fig_n128_cycle_breakdown.png`
- `fig_hpl_openblas.png`

## 时间轴

| 时间 | 画面 | 核心内容 |
|---|---|---|
| 00:00–00:38 | 标题与研究问题 | 主题、队伍、3.75×/3.61×/PASSED |
| 00:38–01:00 | 技术路线 | QEMU/Spike、Ara2 RTL、K230与官方HPL |
| 01:00–01:26 | 核心优化 | 主元行驻留、整行交换、跨步列缩放 |
| 01:26–01:43 | 现场校验 | 原始日志、CSV和数值指纹自动核对 |
| 01:43–02:03 | RTL优化路径 | 128阶3.75×、256阶3.61× |
| 02:03–02:27 | 阶段收益 | 列分块、右上矩阵块和三角求解周期变化 |
| 02:27–02:47 | 官方HPL新图 | OpenBLAS RVV对比与大规模实测 |
| 02:47–03:06 | 实板视频 | K230板卡与官方HPL PASSED |
| 03:06–03:40 | 价值与交付 | 可复现、可校验、可迁移 |

## 数据口径

- RTL主结果使用4通道、NB=32、关闭分阶段计时的同配置对照。
- 阶段分解使用两次均开启分阶段计时的128阶对照，不与主结果混算周期。
- K230结果均为单Linux CPU、单MPI rank；官方HPL仅指Netlib HPL 2.3。
- 实拍单次运行是1.8871 GFLOPS；报告引用的N=8192/NB=256归档单次结果是1.8848 GFLOPS，两者不混为重复中位数。
- 4096阶/NB=256官方HPL三次中位数为1.7755 GFLOPS，均PASSED。

## 重新生成

在仓库根目录准备原始实拍文件：

```text
demo/build/k230_footage/board_clip.mp4
demo/build/k230_footage/passed_clip.mp4
```

生成配音：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File demo/scripts/generate_narration.ps1 `
  -Storyboard demo/storyboard.json `
  -OutputDirectory demo/build/narration
```

在带Pillow和中文字体的WSL环境生成图页：

```bash
python3 -I demo/scripts/render_slides.py
```

用同目录包含 `ffmpeg.exe` 与 `ffprobe.exe` 的Windows构建工具合成新文件；脚本拒绝覆盖已有输出：

```bash
python -I demo/scripts/build_preview.py /path/to/ffmpeg.exe demo/build/demo_final_v5.mp4
```

## 验收

```bash
/path/to/ffprobe.exe -v error -show_streams -show_format -of json demo/build/demo_final_v4.mp4
/path/to/ffmpeg.exe -v error -i demo/build/demo_final_v4.mp4 -f null -
```

检查时长小于10分钟、文件小于100MB、H.264/AAC、1920×1080和30 fps；逐段抽帧检查新图、字幕和实拍画面。最终文件的SHA-256记录在 `deliverables/SHA256SUMS.txt`。
