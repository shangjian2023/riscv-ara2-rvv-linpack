#!/usr/bin/env python3
"""Render 1080p demo slides from the storyboard and verified project evidence."""
import csv
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo"
OUT = DEMO / "build/slides"
W, H = 1920, 1080
FONT = ("C:/Windows/Fonts/msyh.ttc" if Path("C:/Windows/Fonts/msyh.ttc").exists()
        else "/mnt/c/Windows/Fonts/msyh.ttc")
MONO = ("C:/Windows/Fonts/consola.ttf" if Path("C:/Windows/Fonts/consola.ttf").exists()
        else "/mnt/c/Windows/Fonts/consola.ttf")
INK = "#17212B"
MUTED = "#52606D"
BLUE = "#2A78D6"
ORANGE = "#EB6834"
GREEN = "#1BAF7A"
YELLOW = "#EDA100"
SURFACE = "#F5F7FA"
WHITE = "#FFFFFF"
BORDER = "#D9E1E8"


def font(size, mono=False):
    return ImageFont.truetype(MONO if mono else FONT, size)


def base(title, index):
    image = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, W, 18), fill=BLUE)
    draw.text((90, 60), title, font=font(56), fill=INK)
    draw.line((90, 155, 1830, 155), fill=BORDER, width=2)
    draw.text((90, 1015), "光明未来  |  RVV 1.0 Linpack", font=font(24), fill=MUTED)
    draw.text((1740, 1015), f"{index:02d} / 12", font=font(24), fill=MUTED)
    return image, draw


def wrapped(draw, text, box_width, text_font):
    lines = []
    for source_line in text.splitlines():
        current = ""
        for char in source_line:
            candidate = current + char
            if current and draw.textlength(candidate, font=text_font) > box_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)
    return lines


def paragraph(draw, text, xy, width, size=34, fill=INK, spacing=16, mono=False):
    text_font = font(size, mono)
    x, y = xy
    for line in wrapped(draw, text, width, text_font):
        draw.text((x, y), line, font=text_font, fill=fill)
        y += size + spacing
    return y


def card(draw, box, title, body="", accent=BLUE, number=None):
    draw.rounded_rectangle(box, radius=24, fill=SURFACE, outline=BORDER, width=2)
    x1, y1, x2, y2 = box
    draw.rectangle((x1, y1, x1 + 10, y2), fill=accent)
    if number:
        draw.text((x1 + 36, y1 + 28), number, font=font(30), fill=accent)
        title_y = y1 + 80
    else:
        title_y = y1 + 34
    draw.text((x1 + 36, title_y), title, font=font(42), fill=INK)
    if body:
        paragraph(draw, body, (x1 + 36, title_y + 72), x2 - x1 - 72, 30, MUTED, 12)


def fit_image(canvas, path, box):
    source = Image.open(path).convert("RGB")
    x1, y1, x2, y2 = box
    scale = min((x2 - x1) / source.width, (y2 - y1) / source.height)
    size = (int(source.width * scale), int(source.height * scale))
    source = source.resize(size, Image.Resampling.LANCZOS)
    x = x1 + (x2 - x1 - size[0]) // 2
    y = y1 + (y2 - y1 - size[1]) // 2
    canvas.paste(source, (x, y))


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def slide_title(index):
    image, draw = base("面向 RVV 1.0 的 Linpack 应用性能优化", index)
    draw.text((90, 205), "Ara2 RTL 实测与 K230 商用板验证  ·  官方 Netlib HPL 2.3",
              font=font(34), fill=MUTED)
    draw.text((90, 335), "国防科技大学  ·  光明未来队", font=font(50), fill=BLUE)
    cards = [
        ("3.75×", "128阶求解全过程加速", BLUE),
        ("3.61×", "256阶求解全过程加速", GREEN),
        ("PASSED", "官方 HPL 残差校验", ORANGE),
    ]
    for i, (value, label, color) in enumerate(cards):
        x = 90 + i * 580
        draw.rounded_rectangle((x, 480, x + 540, 790), radius=28, fill=SURFACE)
        draw.text((x + 38, 535), value, font=font(82), fill=color)
        paragraph(draw, label, (x + 40, 680), 460, 31, INK)
    draw.text((90, 828),
              "李丞阳（方案设计与 RTL 向量优化）  ·  马卓然（K230 移植与官方 HPL 实测）  ·  段智中（数据校验与报告）",
              font=font(29), fill=INK)
    draw.text((90, 878), "指导老师：雷国庆", font=font(28), fill=MUTED)
    return image


def slide_questions(index):
    image, draw = base("三个研究问题", index)
    items = [
        ("自动路径差距", "编译器自动优化是否真正生成 RVV？与手写内核相差多少？", BLUE),
        ("求解过程瓶颈", "矩阵乘、列面板与三角求解，真正该优化哪里？", ORANGE),
        ("结果能否复现", "理论推算与参数选型，能否经 RTL 和商用板验证？", GREEN),
    ]
    for i, (title, body, color) in enumerate(items):
        card(draw, (90, 220 + i * 240, 1830, 420 + i * 240), title, body, color, f"0{i+1}")
    return image


def slide_pipeline(index):
    image, draw = base("同源代码，分层实测", index)
    boxes = [
        ("C / RVV 内核", "参数化 DGEMM\nBlocked LU + solve", BLUE),
        ("QEMU / Spike", "跨 VLEN 功能\nISA 语义与指纹", GREEN),
        ("Ara2 Verilator", "裸机 ELF\nmcycle 真实周期", ORANGE),
        ("K230 / C908", "同一 Linux 二进制\n单 CPU 复测", BLUE),
    ]
    for i, (title, body, color) in enumerate(boxes):
        x = 90 + i * 440
        card(draw, (x, 245, x + 380, 570), title, body, color)
        if i < 3:
            draw.line((x + 385, 405, x + 430, 405), fill=MUTED, width=5)
            draw.polygon([(x + 430, 395), (x + 430, 415), (x + 445, 405)], fill=MUTED)
    draw.rounded_rectangle((90, 670, 1830, 890), radius=24, fill="#EEF5FD", outline=BLUE, width=2)
    draw.text((130, 710), "独立标准负载", font=font(34), fill=BLUE)
    draw.text((130, 775), "Netlib HPL 2.3  +  MPICH 4.2.0  +  OpenBLAS 0.3.34",
              font=font(38), fill=INK)
    draw.text((130, 840), "自研 Linpack 求解程序与官方 HPL 分别呈现", font=font(30), fill=MUTED)
    return image


def slide_optimization(index):
    image, draw = base("核心优化：主元行复用与连续行更新", index)
    fit_image(image, DEMO.parent / "report_archive/2026-11-08/figures/fig_panel_v2_evidence.png",
              (65, 175, 1855, 940))
    draw.text((90, 955), "主元行驻留向量寄存器  ·  RVV 整行交换  ·  跨步列缩放",
              font=font(28), fill=MUTED)
    return image


def slide_reproduce(index):
    image, draw = base("现场校验：从原始日志重新计算", index)
    evidence = subprocess.check_output(
        [sys.executable, "-I", str(DEMO / "scripts/show_evidence.py")],
        cwd=ROOT, text=True, encoding="utf-8")
    validator = subprocess.check_output(
        [sys.executable, "-I", "apps_linpack_draft/scripts/validate_results.py"],
        cwd=ROOT, text=True, encoding="utf-8", errors="replace")
    passed = next(line for line in validator.splitlines() if line.startswith("PASS:"))
    lines = ["$ python -I apps_linpack_draft/scripts/validate_results.py", passed, "",
             "$ python -I demo/scripts/show_evidence.py"] + evidence.splitlines()
    draw.rounded_rectangle((70, 190, 1850, 950), radius=18, fill="#10161D")
    y = 220
    for line in lines:
        color = "#75D69C" if line.startswith(("PASS:", "N=", "K230")) else "#D5DEE7"
        for part in wrapped(draw, line, 1690, font(24, True)):
            draw.text((105, y), part, font=font(24, True), fill=color)
            y += 34
    return image


def slide_results(index):
    image, draw = base("Ara2 RTL：两种规模均获得三倍以上加速", index)
    fit_image(image, DEMO.parent / "report_archive/2026-11-08/figures/fig_fullchain_n128_n256.png",
              (60, 175, 1860, 920))
    draw.text((90, 945), "4 通道  ·  分块 32  ·  关闭分阶段计时  ·  残差与校验和一致",
              font=font(28), fill=MUTED)
    return image


def slide_stages(index):
    image, draw = base("收益来源：列面板与右上矩阵块处理", index)
    fit_image(image, DEMO.parent / "report_archive/2026-11-08/figures/fig_n128_cycle_breakdown.png",
              (60, 175, 1860, 920))
    draw.text((90, 945), "128 阶矩阵  ·  两次运行均开启分阶段计时  ·  总周期减少 73.3%",
              font=font(28), fill=MUTED)
    return image


def slide_hpl(index):
    image, draw = base("K230 官方 HPL：标准负载实板验证", index)
    fit_image(image, DEMO.parent / "report_archive/2026-11-08/figures/fig_hpl_openblas.png",
              (50, 175, 1870, 920))
    draw.text((90, 945), "单 Linux CPU  ·  单 MPI 进程  ·  全部通过官方残差校验",
              font=font(28), fill=MUTED)
    return image


def slide_value(index):
    image, draw = base("这件事的价值", index)
    items = [
        ("一套内核", "从开源向量核到商用芯片\n同源 RVV 代码分平台构建", BLUE),
        ("一键校验", "所有结果从原始日志\n重新计算、自动核对", GREEN),
        ("标准验证", "业界标准 HPL 基准\n残差校验一次通过", ORANGE),
    ]
    for i, (value, body, color) in enumerate(items):
        x = 90 + i * 580
        draw.rounded_rectangle((x, 250, x + 540, 690), radius=24, fill=SURFACE)
        draw.text((x + 38, 320), value, font=font(64), fill=color)
        paragraph(draw, body, (x + 40, 460), 460, 32, INK, 18)
    draw.rounded_rectangle((90, 780, 1830, 900), radius=18, fill="#EEF5FD")
    draw.text((125, 820), "可复现  ·  可校验  ·  可迁移，方法直接复用", font=font(36), fill=BLUE)
    return image


def slide_delivery(index):
    image, draw = base("代码、数据、日志、报告，形成闭环", index)
    items = [
        ("apps_linpack_draft/", "RVV 内核与求解全过程"),
        ("apps_linpack_draft/results/", "配置、反汇编、日志、CSV"),
        ("hpl/", "官方输入与 PASSED 证据"),
        ("demo/", "分镜、讲解词、校验入口"),
        ("report_archive/", "报告修订与图表来源"),
    ]
    y = 235
    for path, description in items:
        draw.ellipse((100, y + 12, 118, y + 30), fill=GREEN)
        draw.text((145, y), path, font=font(29, True), fill=INK)
        draw.text((800, y), description, font=font(29), fill=INK)
        y += 105
    draw.rounded_rectangle((1300, 255, 1820, 740), radius=30, fill="#EEF5FD")
    paragraph(draw, "可复现\n可核验\n可迁移", (1370, 340), 390, 56, BLUE, 42)
    draw.text((90, 875), "固定版本 + 复现命令 + 原始证据", font=font(38), fill=MUTED)
    draw.text((90, 940), "感谢观看", font=font(34), fill=INK)
    return image


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    static_slides = [
        ("01_title", slide_title, 1),
        ("02_questions", slide_questions, 2),
        ("03_pipeline", slide_pipeline, 3),
        ("04_optimization", slide_optimization, 4),
        ("05_reproduce", slide_reproduce, 5),
        ("06_results", slide_results, 6),
        ("06b_stages", slide_stages, 7),
        ("07_hpl", slide_hpl, 8),
        ("08_value", slide_value, 11),
        ("09_delivery", slide_delivery, 12),
    ]
    for slide_id, renderer, number in static_slides:
        image = renderer(number)
        path = OUT / f"{slide_id}.png"
        image.save(path, optimize=True)
        print(f"SLIDE {path}")


if __name__ == "__main__":
    main()
