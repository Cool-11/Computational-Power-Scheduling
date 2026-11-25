#!/usr/bin/env python3
"""批量跑世界，输出对账/合法性/利润表，用于策略迭代的可复现实验记录。

    python tools/bench.py --tag v1 --seeds 1-8 --T 60
    python tools/bench.py --tag v2 --seeds 1-8 --T 60 --append docs/实验记录.md
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def parse_range(s):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="run")
    ap.add_argument("--seeds", default="1-6")
    ap.add_argument("--T", type=int, default=60)
    ap.add_argument("--load", type=float, default=0.8)
    ap.add_argument("--larger", action="store_true", help="用接近正式规模的世界")
    ap.add_argument("--solver", default=os.path.join(ROOT, "build", "solver.exe"))
    ap.add_argument("--append", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    seeds = parse_range(args.seeds)
    wdir = os.path.join(ROOT, "tests", "worlds")
    os.makedirs(wdir, exist_ok=True)

    rows = []
    total_profit = 0
    total_bad = 0
    total_illegal = 0
    total_done = 0
    total_wf = 0

    for s in seeds:
        if args.larger:
            name = f"bench_{s}_big.in"
            gen = [sys.executable, os.path.join(HERE, "gen_world.py"), "--seed", str(s),
                   "--T", str(args.T), "--D", "4", "--nodes-per-dc", "30",
                   "--racks-per-dc", "6", "--mach-lo", "6", "--mach-hi", "10",
                   "--K", "80", "--L", "200", "--I", "60", "--P", "500",
                   "--W", "40", "--load", "2.0", "--audit-rate", "5",
                   "--out", os.path.join(wdir, name)]
        else:
            name = f"bench_{s}_{args.T}.in"
            gen = [sys.executable, os.path.join(HERE, "gen_world.py"), "--seed", str(s),
                   "--T", str(args.T), "--load", str(args.load),
                   "--out", os.path.join(wdir, name)]
        path = os.path.join(wdir, name)
        subprocess.run(gen, check=True, stdout=subprocess.DEVNULL)

        pr = subprocess.run([sys.executable, os.path.join(HERE, "judge.py"), "run",
                             "--world", path, "--solver", args.solver],
                            capture_output=True, text=True, timeout=1800)
        txt = pr.stdout
        m_q = re.search(r"对账 (\d+) 道，错 (\d+)", txt)
        m_done = re.search(r"完成工作流 (\d+)/(\d+)，收益 (-?\d+)，费用 (-?\d+)，利润 (-?\d+)", txt)
        illegal = "首次非法" in txt
        if not m_q or not m_done:
            print(txt)
            raise SystemExit("judge 输出无法解析")
        nq, bad = int(m_q.group(1)), int(m_q.group(2))
        done, nwf, rev, fee, profit = (int(m_done.group(i)) for i in range(1, 6))
        rows.append((s, nq, bad, illegal, done, nwf, rev, fee, profit))
        total_bad += bad
        total_illegal += 1 if illegal else 0
        total_done += done
        total_wf += nwf
        total_profit += profit
        if not args.quiet:
            print(f"  seed {s:>3}: 对账 {nq:>4} 错 {bad:>3} | 非法 {'是' if illegal else '否'} | "
                  f"完成 {done:>3}/{nwf:<3} 收益 {rev:>7} 费用 {fee:>7} 利润 {profit:>8}")

    print(f"[{args.tag}] 世界 {len(seeds)}，对账错 {total_bad}，非法组 {total_illegal}，"
          f"完成 {total_done}/{total_wf}，总利润 {total_profit}")

    if args.append:
        with open(os.path.join(ROOT, args.append), "a", encoding="utf-8") as f:
            f.write(f"\n### {args.tag}（T={args.T}{'，大规模' if args.larger else ''}，"
                    f"seeds={args.seeds}）\n\n")
            f.write("| seed | 对账题 | 错 | 非法 | 完成/总数 | 收益 | 费用 | 利润 |\n")
            f.write("|---|---|---|---|---|---|---|---|\n")
            for r in rows:
                f.write(f"| {r[0]} | {r[1]} | {r[2]} | {'是' if r[3] else '否'} | "
                        f"{r[4]}/{r[5]} | {r[6]} | {r[7]} | {r[8]} |\n")
            f.write(f"\n合计：对账错 {total_bad}，非法组 {total_illegal}，"
                    f"完成 {total_done}/{total_wf}，总利润 **{total_profit}**\n")
    return 0 if total_bad == 0 and total_illegal == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
