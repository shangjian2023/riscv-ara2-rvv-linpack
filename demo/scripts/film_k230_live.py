#!/usr/bin/env python3
"""Visible K230 filming console: run official HPL live and preserve the serial log."""
from datetime import datetime
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import font
from tkinter import messagebox


ROOT = Path(__file__).resolve().parents[2]
SERIAL_SCRIPT = ROOT / "hpl/scripts/k230_serial.ps1"
PORT = "COM3"
TIMEOUT_SEC = 360
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
REMOTE_LOG = f"/root/hpl/film_hpl_n8192_nb256_{RUN_ID}.log"
LOCAL_LOG = ROOT / f"demo/build/film_k230_live_{RUN_ID}.log"
BOARD_COMMAND = (
    "cd /root/hpl && cp HPL.n8192_nb256.dat HPL.dat && "
    f"echo __FILM_LIVE_BEGIN__={RUN_ID} && nproc && sha256sum xhpl_openblas && "
    f"./xhpl_openblas > {REMOTE_LOG} 2>&1; rc=$?; "
    f"echo __HPL_PROCESS_RC__=$rc; cat {REMOTE_LOG}; test $rc -eq 0"
)


class FilmWindow:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.process = None
        self.saw_one_pass = False
        self.saw_zero_fail = False
        self.saw_passed = False
        self.log_handle = LOCAL_LOG.open("w", encoding="utf-8")
        self.log_handle.write(f"RUN_ID={RUN_ID}\nPORT={PORT}\nREMOTE_LOG={REMOTE_LOG}\n")
        self.log_handle.write(f"COMMAND={BOARD_COMMAND}\n\n")
        self.log_handle.flush()

        root.title(f"K230 官方 HPL 实拍 {RUN_ID}")
        root.state("zoomed")
        root.configure(bg="#0B1118")
        root.bind("<Escape>", lambda _event: self.close())

        header = tk.Frame(root, bg="#12202D", padx=28, pady=18)
        header.pack(fill="x")
        title_font = font.Font(family="Microsoft YaHei UI", size=25, weight="bold")
        info_font = font.Font(family="Microsoft YaHei UI", size=16)
        status_font = font.Font(family="Microsoft YaHei UI", size=18, weight="bold")
        tk.Label(header, text="K230 / C908 实板 · 官方 Netlib HPL 2.3 现场复测",
                 bg="#12202D", fg="#F2F6FA", font=title_font, anchor="w").pack(fill="x")
        tk.Label(header,
                 text="COM3 · 115200  |  单 Linux CPU  |  单 MPI rank  |  N=8192  |  NB=256  |  OpenBLAS 0.3.34 RVV",
                 bg="#12202D", fg="#A9C8E8", font=info_font, anchor="w", pady=8).pack(fill="x")
        self.status = tk.Label(header, text="正在连接实板并启动现场运行……",
                               bg="#12202D", fg="#F3C66D", font=status_font, anchor="w")
        self.status.pack(fill="x")

        body = tk.Frame(root, bg="#0B1118", padx=24, pady=14)
        body.pack(fill="both", expand=True)
        text_font = font.Font(family="Consolas", size=17)
        self.text = tk.Text(body, bg="#080D12", fg="#D8E3EC", insertbackground="#FFFFFF",
                            font=text_font, wrap="none", padx=18, pady=14,
                            relief="flat", highlightthickness=1,
                            highlightbackground="#28445C", spacing1=2, spacing3=2)
        scroll_y = tk.Scrollbar(body, command=self.text.yview)
        scroll_x = tk.Scrollbar(body, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.text.tag_configure("passed", foreground="#75D69C")
        self.text.tag_configure("marker", foreground="#82BDF5")
        self.text.tag_configure("error", foreground="#FF8D7A")
        self.text.configure(state="disabled")

        footer = tk.Label(root,
                          text="CanMV-K230 · C908 · RVV 1.0  |  板上路径 /root/hpl  |  实时串口输出，不是归档回放",
                          bg="#12202D", fg="#C3D0DB", font=info_font, padx=24, pady=12, anchor="w")
        footer.pack(fill="x")

        self.append(f"__FILM_WINDOW__ run={RUN_ID}\n", "marker")
        self.append(f"Board command: {BOARD_COMMAND}\n\n", "marker")
        self.root.after(250, self.start_run)
        self.root.after(100, self.poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def append(self, value, tag=None):
        self.text.configure(state="normal")
        if tag:
            self.text.insert("end", value, tag)
        elif "PASSED" in value:
            self.text.insert("end", value, "passed")
        elif value.startswith(("__FILM", "__HPL", "__K230")):
            self.text.insert("end", value, "marker")
        else:
            self.text.insert("end", value)
        self.text.configure(state="disabled")
        self.text.see("end")

    def start_run(self):
        self.status.configure(text="实板正在运行官方 HPL；通常约 195 秒，请保持供电与串口连接……", fg="#F3C66D")
        argv = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(SERIAL_SCRIPT), "-Port", PORT, "-Login",
            "-TimeoutSec", str(TIMEOUT_SEC), "-Command", BOARD_COMMAND,
        ]
        try:
            self.process = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
        except OSError as error:
            self.status.configure(text=f"无法启动串口命令：{error}", fg="#FF8D7A")
            return
        threading.Thread(target=self.read_output, daemon=True).start()

    def read_output(self):
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.events.put(("output", line))
        return_code = self.process.wait()
        self.events.put(("done", return_code))

    def poll_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "output":
                    self.log_handle.write(value)
                    self.log_handle.flush()
                    self.append(value)
                    if "1 tests completed and passed residual checks" in value:
                        self.saw_one_pass = True
                    if "0 tests completed and failed residual checks" in value:
                        self.saw_zero_fail = True
                    if "PASSED" in value:
                        self.saw_passed = True
                else:
                    self.log_handle.write(f"\nLOCAL_PROCESS_RC={value}\n")
                    self.log_handle.close()
                    if value == 0 and self.saw_one_pass and self.saw_zero_fail and self.saw_passed:
                        self.status.configure(
                            text="现场运行完成：官方 residual check PASSED · 1 项通过 · 0 项失败 · 可以拍摄",
                            fg="#75D69C")
                    else:
                        self.status.configure(
                            text=f"运行结束但未形成完整 PASSED 证据（RC={value}），请勿作为通过镜头",
                            fg="#FF8D7A")
                    self.append(f"\n__FILM_LOCAL_LOG__ {LOCAL_LOG}\n", "marker")
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    def close(self):
        if self.process is not None and self.process.poll() is None:
            messagebox.showinfo("现场运行仍在进行", "请等待官方 HPL 完成后再关闭；不要中断约 195 秒的实板运行。")
            return
        self.root.destroy()


def main():
    root = tk.Tk()
    FilmWindow(root)
    root.mainloop()
    print(f"FILM_LOG {LOCAL_LOG}")


if __name__ == "__main__":
    main()
