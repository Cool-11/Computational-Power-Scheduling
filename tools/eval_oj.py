#!/usr/bin/env python3
"""用官方评测程序并行评估一组参数文件，输出每个 seed 的利润与合计。

    python tools/eval_oj.py --solver build/solver.exe
    python tools/eval_oj.py --solver build/x.exe --params tests/params/oj.in tests/params/oj_11.in
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_one(solver, param, judge):
    rep = os.path.join(ROOT, "tmp", "rep_" + os.path.basename(param) + ".txt")
    pr = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "tpj_run.py"),
                         "--judge", judge, "--params", param, "--solver", solver,
                         "--report", rep],
                        capture_output=True, text=True, timeout=1800)
    m = re.search(r"profit=(-?\d+).*?wf=(\d+)/(\d+).*?ub3=(\d+)", pr.stdout, re.S)
    if not m:
        return (os.path.basename(param), None, 0, 0, 0, pr.stdout[-300:])
    return (os.path.basename(param), int(m.group(1)), int(m.group(2)),
            int(m.group(3)), int(m.group(4)), "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solver", default=os.path.join(ROOT, "build", "solver.exe"))
    ap.add_argument("--judge", default=os.path.join(ROOT, "vendor", "samples", "tpj_win.exe"))
    ap.add_argument("--params", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    params = args.params or sorted(glob.glob(os.path.join(ROOT, "tests", "params", "oj*.in")))
    total = 0
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(lambda p: run_one(args.solver, p, args.judge), params):
            rows.append(res)
    for (name, profit, done, tot, ub3, err) in rows:
        if profit is None:
            print(f"  {name}: 失败 {err}")
            continue
        pct = 100.0 * profit / ub3 if ub3 else 0
        print(f"  {name:<10} 利润 {profit:>9}  完成 {done:>5}/{tot:<5} 上界 {ub3:>9} ({pct:.1f}%)")
        total += profit
    print(f"[{args.tag or os.path.basename(args.solver)}] 合计利润 {total}")


if __name__ == "__main__":
    main()
