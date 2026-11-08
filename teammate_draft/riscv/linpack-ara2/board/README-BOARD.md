# K230（C908）商用板卡实测 — 2026-11-05

同一 `build/bench` 二进制（静态 riscv64gcv，qemu 全量验证过的那份）刷入
CanMV-K230 V3.0（创乐博，玄铁 C908，RVV 1.0，VLEN=128）实测。
**结果：28/28 校验全过，残差与 QEMU 逐位一致；板上最优 mr2×m8=1.14 GFLOPS。
2026-11-08 新增 B 面板打包与同形状重复测量：160³ 中位数 1.3218 GFLOPS，
1024³ 从 0.1742 提升至 0.9804 GFLOPS；详见 `../results/k230_packb_summary.md`。**

历史 v2 汇总中的 3.38×/4.23×使用最优 160³ 与 131×126×117 基线，
属于跨用例比较，不能当作同形状加速比。新的 `k230_fair.csv` 与
`k230_fair_packb.csv` 对每个 N 使用相同输入并报告重复测量中位数。

历史数据：`../results/k230_board_vlen2.csv`（原始）、`../results/e12_k230_board.csv`（汇总）、
分析脚本 `../sim/k230_board_analysis.py`。
新增数据：`k230_fair.csv`、`k230_fair_packb.csv`、`k230_board_packb_fair.csv`，
分析脚本 `../sim/k230_packb_analysis.py`。

## 复现流程（Windows + WSL）

1. **注入 bench 到镜像**：`bash board/inject_bench.sh`（WSL；debugfs 方式，
   loop mount 在 WSL 不可用；rootfs 分区 offset 128MiB）。
2. **写卡**：`board/write_flash.ps1`（管理员 PowerShell 裸写 `\\.\PhysicalDrive1`，
   **脚本与镜像路径必须纯 ASCII**——PS 5.1 对中文路径按 ANSI 解析会静默乱码；
   脚本内置安全门：只接受 8-40GB 的 USB 盘）。 Rufus 从 img.gz 写会导致 GPT CRC
   损坏 → 内核 `Cannot open root device` panic，别用。
3. **接线上电**：充电器（≥2A）→ OTG 口（主板唯一供电口，电脑 USB 口带不动，
   欠压时设备枚举为"描述符请求失败"）；电脑 → DEBUG 口（CH342 双串口，
   COM8=控制台 115200）。
4. **串口自动化**：`board/serial_shell2.ps1`（自动 U-Boot→boot→登录→跑 /bench）。
   两个坑：①周期性回车会打断 U-Boot 自动启动倒计时——只在完全无输出时才探测，
   停在 `K230#` 提示符就发 `boot`；②expect 完成标志用 `echo RC=$?` 的展开值
   `RC=0` 匹配，防命令回显自匹配。
5. Linux root 无密码自动登录；`/bench` 输出 CSV 经串口回传。

## 板上关键观察

- GCC 编译的 blocked_autovec 在板上**慢于** naive_scalar（0.269 vs 0.337 GF）——
  GCC 13 未向量化两个基线（e9 诊断），分块只剩开销，跨平台互证；
- 历史小矩阵结果中，C908（VLEN=128）优选 mr2×m8；这只是一个与
  VLEN 选型趋势一致的实测点，不能单凭它宣称通用自适应规则已获验证；
- B 面板连续打包消除了 2/4/8KB 行跨距导致的缓存组冲突，使大矩阵 RVV
  性能从不可持续恢复到约 1 GFLOPS，详见新增公平基准；
- `thead,c900-pmu` 18 个硬件计数器可用（boot log），后续可做 perf 级分析。
