#!/usr/bin/env python3
"""把官方评测程序 tpj_win.exe 和本地求解器用双向管道接起来。

    python tools/tpj_run.py --judge vendor/samples/tpj_win.exe \
        --params tests/params/oj.in --solver build/solver.exe

官方评测程序的行为：读参数文件 → 生成世界 → 把世界写到自己 stdout → 从自己 stdin
读选手的回复。所以我们开两个进程，各起一个线程把对方的输出转发到对方的输入。
评测报告写到 --report 指定的文件（默认 tmp/tpj_report.txt），同时打到终端。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time


def pump(src, dst, tag, tee=None):
    try:
        while True:
            chunk = src.read(4096)
            if not chunk:
                break
            if tee is not None:
                tee.write(chunk)
                tee.flush()
            dst.write(chunk)
            dst.flush()
    except (BrokenPipeError, ValueError, OSError):
        pass
    finally:
        try:
            dst.close()
        except Exception:  # noqa: BLE001
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", default="vendor/samples/tpj_win.exe")
    ap.add_argument("--params", required=True)
    ap.add_argument("--solver", default="build/solver.exe")
    ap.add_argument("--report", default="tmp/tpj_report.txt")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--tee", default=None, help="把评测器发给求解器的字节流存下来，可单独计时")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)

    judge = subprocess.Popen([args.judge, args.params, args.report],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, bufsize=0)
    solver = subprocess.Popen([args.solver],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, bufsize=0)

    tee = None
    if args.tee:
        os.makedirs(os.path.dirname(args.tee) or ".", exist_ok=True)
        tee = open(args.tee, "wb")
    t1 = threading.Thread(target=pump, args=(judge.stdout, solver.stdin, "j->s", tee), daemon=True)
    t2 = threading.Thread(target=pump, args=(solver.stdout, judge.stdin, "s->j"), daemon=True)
    err_box = {}

    def drain(stream, key):
        err_box[key] = stream.read()

    t3 = threading.Thread(target=drain, args=(judge.stderr, "judge"), daemon=True)
    t4 = threading.Thread(target=drain, args=(solver.stderr, "solver"), daemon=True)
    for t in (t1, t2, t3, t4):
        t.start()

    stats = {"rss": 0, "cpu": 0.0}
    try:
        import psutil
        proc = psutil.Process(solver.pid)

        def sample():
            while solver.poll() is None:
                try:
                    info = proc.memory_info()
                    if info.rss > stats["rss"]:
                        stats["rss"] = info.rss
                    t = proc.cpu_times()
                    stats["cpu"] = t.user + t.system
                except Exception:  # noqa: BLE001
                    return
                time.sleep(0.01)

        threading.Thread(target=sample, daemon=True).start()
    except Exception:  # noqa: BLE001
        pass

    try:
        rc = judge.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        judge.kill()
        solver.kill()
        print(f"[tpj] 超时 {args.timeout}s")
        return 2
    try:
        solver.wait(timeout=10)
    except subprocess.TimeoutExpired:
        solver.kill()
    if stats["cpu"] or stats["rss"]:
        print(f"[tpj] 求解器 CPU {stats['cpu']:.3f}s，峰值内存 {stats['rss'] / 1048576:.1f} MB")

    for t in (t1, t2, t3, t4):
        t.join(timeout=5)

    err = err_box.get("judge", b"") or b""
    if err.strip():
        sys.stdout.write(err.decode(errors="replace"))

    if args.verbose:
        serr = err_box.get("solver", b"") or b""
        if serr.strip():
            lines = serr.decode(errors="replace").strip().splitlines()
            sys.stdout.write("\n".join(lines[-25:]) + "\n")

    text = ""
    try:
        with open(args.report, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        pass
    if text.strip():
        print(text)
    print(f"[tpj] judge return code = {rc}")
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
