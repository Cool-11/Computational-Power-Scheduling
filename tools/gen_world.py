#!/usr/bin/env python3
"""生成本仓库自定义格式的世界文件（供 tools/judge.py run 使用）。

两种用法：

    # 1) 直接给参数（旧用法，快速造小世界）
    python tools/gen_world.py --seed 1 --T 60 --load 0.8 --out tests/worlds/w1.in

    # 2) 按 OJ 题面里的 .in 参数文件生成（推荐，参数名与官方一致）
    python tools/gen_world.py --param tests/params/oj.in --seed 20261105 --out tests/worlds/oj.in

生成规则是本仓库自行设计的，目标是让**规模、事件密度、时长分布**接近正式数据，
不是复刻官方生成器（官方目标值 P* 无法在本地得到）。
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge import Huffman  # noqa: E402


def parse_param_file(path):
    """解析 OJ 参数文件：每行 `key value`，忽略空行与 # 注释。"""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            out[parts[0]] = parts[1]
    return out


def build_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--param", default=None, help="OJ 题面里的 .in 参数文件")
    ap.add_argument("--T", type=int, default=40)
    ap.add_argument("--D", type=int, default=2)
    ap.add_argument("--nodes-per-dc", type=int, default=4)
    ap.add_argument("--racks-per-dc", type=int, default=2)
    ap.add_argument("--mach-lo", type=int, default=2)
    ap.add_argument("--mach-hi", type=int, default=3)
    ap.add_argument("--K", type=int, default=6)
    ap.add_argument("--L", type=int, default=6)
    ap.add_argument("--I", type=int, default=4)
    ap.add_argument("--P", type=int, default=6)
    ap.add_argument("--W", type=int, default=5)
    ap.add_argument("--load", type=float, default=0.8, help="每 tick 期望到达的工作流数")
    ap.add_argument("--audit-rate", type=float, default=2.0, help="每 tick 期望对账题数")
    ap.add_argument("--fail-frac", type=float, default=0.1)
    ap.add_argument("--link-events", type=int, default=6)
    ap.add_argument("--quota-events", type=int, default=4)
    ap.add_argument("--log-rate", type=float, default=0.2)
    ap.add_argument("--wfs-max", type=int, default=6, help="每 tick 最多到达的工作流数")
    ap.add_argument("--jobs-max", type=int, default=6, help="每个工作流最多作业数")
    ap.add_argument("--pat-len", type=int, default=8, help="模式串最大长度")
    ap.add_argument("--log-len", type=int, default=30, help="单行日志最大符号数")
    ap.add_argument("--sigma", type=float, default=0.35, help="真实时长的对数正态噪声")
    ap.add_argument("--bias-lo", type=float, default=0.7)
    ap.add_argument("--bias-hi", type=float, default=1.8)
    ap.add_argument("--straggler-p", type=float, default=0.08)
    ap.add_argument("--deadline-lo", type=float, default=1.3, help="截止 = 到达 + cp × lo~hi")
    ap.add_argument("--deadline-hi", type=float, default=2.2)
    ap.add_argument("--deadline-pad-lo", type=int, default=10)
    ap.add_argument("--deadline-pad-hi", type=int, default=30)
    ap.add_argument("--p-noise", type=int, default=0, help="噪声模式串个数（权重 1~3）")
    ap.add_argument("--p-signal", type=int, default=0, help="信号模式串个数（权重大）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.param:
        p = parse_param_file(args.param)
        g = p.get
        args.T = int(g("T", args.T))
        args.D = int(g("D", args.D))
        args.nodes_per_dc = int(g("nodes_per_dc", args.nodes_per_dc))
        args.racks_per_dc = int(g("racks_per_dc", args.racks_per_dc))
        args.mach_lo = int(g("mach_per_rack_lo", args.mach_lo))
        args.mach_hi = int(g("mach_per_rack_hi", args.mach_hi))
        args.K = int(g("NT", args.K))
        args.L = int(g("NL", args.L))
        args.I = int(g("NI", args.I))
        args.W = int(g("W", args.W))
        args.load = float(g("load", args.load))
        args.audit_rate = float(g("audit_rate", args.audit_rate))
        args.fail_frac = float(g("fail_frac", args.fail_frac))
        args.link_events = int(g("link_events", args.link_events))
        args.quota_events = int(g("quota_events", args.quota_events))
        args.log_rate = float(g("log_rate", args.log_rate))
        args.sigma = float(g("sigma", args.sigma))
        args.bias_lo = float(g("bias_lo", args.bias_lo))
        args.bias_hi = float(g("bias_hi", args.bias_hi))
        args.straggler_p = float(g("straggler_p", args.straggler_p))
        args.p_noise = int(g("p_noise", args.p_noise))
        args.p_signal = int(g("p_signal", args.p_signal))
        args.P = args.p_noise + args.p_signal
    return args


def main():
    args = build_args()

    rnd = random.Random(args.seed)
    T = args.T
    D = args.D
    N = D * args.nodes_per_dc
    per_dc = N // D
    R = D * args.racks_per_dc

    mach = []
    for r in range(R):
        for _ in range(rnd.randint(args.mach_lo, args.mach_hi)):
            mach.append((r, rnd.choice([4, 8, 16]), rnd.choice([8, 16, 32, 64]),
                         rnd.choice([128, 256, 512, 900])))
    M = len(mach)
    K = args.K
    L = args.L
    I = args.I
    P = args.P
    W = args.W

    price = [rnd.randint(2, 6) for _ in range(D)]

    rack_dc, rack_node, rack_cap = [], [], []
    for r in range(R):
        dc = r // args.racks_per_dc
        rack_dc.append(dc)
        rack_node.append(dc * per_dc + rnd.randrange(per_dc))
        rack_cap.append(rnd.choice([400, 800, 1600]))

    # 网络：机房内部用"枢纽 + 挂载"的两级结构（直径 4~6），机房之间骨干互联
    edges = []
    seen = set()

    def add_edge(u, v, w):
        if u == v:
            return
        key = (min(u, v), max(u, v))
        if key in seen:
            return
        seen.add(key)
        edges.append((u, v, w))

    for d in range(D):
        base = d * per_dc
        nhub = max(4, per_dc // 10)
        hubs = [base + i for i in range(nhub)]
        for i in range(nhub):
            add_edge(hubs[i], hubs[(i + 1) % nhub], rnd.randint(1, 3))
        add_edge(hubs[0], hubs[nhub // 2], rnd.randint(1, 3))
        for i in range(nhub, per_dc):
            add_edge(base + i, hubs[rnd.randrange(nhub)], rnd.randint(1, 2))
    for d in range(D - 1):
        add_edge(d * per_dc + rnd.randrange(max(1, per_dc // 10)),
                 (d + 1) * per_dc + rnd.randrange(max(1, per_dc // 10)),
                 rnd.randint(2, 8))
    if D > 2:
        add_edge(rnd.randrange(max(1, per_dc // 10)),
                 (D - 1) * per_dc + rnd.randrange(max(1, per_dc // 10)), rnd.randint(3, 10))
    E = len(edges)

    parent = [-1]
    for k in range(1, K):
        parent.append(rnd.randrange(0, k))
    quota = [rnd.choice([20, 40, 60, 90, 120]) for _ in range(K)]

    sizes = [rnd.randint(10, 120) for _ in range(L)]
    images = []
    for _ in range(I):
        k = rnd.randint(1, 4)
        images.append(sorted(rnd.sample(range(L), k)))

    freq = [rnd.randint(1, 100) for _ in range(9)]
    huff = Huffman(freq)

    signal_pats = []
    noise_pats = []
    for _ in range(args.p_signal):
        ln = rnd.randint(6, args.pat_len)
        s = "".join(rnd.choice("abcdefgh") for _ in range(ln))
        signal_pats.append((s, rnd.randint(40, 100)))
    for _ in range(args.p_noise):
        ln = rnd.randint(2, 6)
        s = "".join(rnd.choice("abcdefgh") for _ in range(ln))
        noise_pats.append((s, rnd.randint(1, 3)))
    if args.p_noise or args.p_signal:
        patterns = signal_pats + noise_pats
    else:
        patterns = []
        for _ in range(args.P):
            ln = rnd.randint(2, args.pat_len)
            patterns.append(("".join(rnd.choice("abcdefgh") for _ in range(ln)),
                             rnd.randint(1, 50)))
    if not patterns:
        patterns = [("abcd", 5)]
    P = len(patterns)

    B_reg, B_rack, B_net, U_reg, U_net = 60, 200, 40, 2, 1

    tenant_bias = [rnd.uniform(args.bias_lo, args.bias_hi) for _ in range(K)]

    events = defaultdict(list)
    durs = {}
    wf_jobs_range = []
    next_jid = [10 ** 8]

    def new_jid():
        next_jid[0] += rnd.randint(1, 97)
        return next_jid[0]

    for t in range(1, T + 1):
        cnt = 0
        while rnd.random() < args.load and cnt < args.wfs_max:
            cnt += 1
        for _ in range(cnt):
            wid = 10 ** 8 + rnd.randint(0, 8 * 10 ** 8)
            o = rnd.randrange(K)
            v = rnd.choice([500, 1000, 1500, 2000, 3000])
            n = rnd.randint(1, args.jobs_max)
            jl = []
            ids = []
            for idx in range(n):
                jid = new_jid()
                c = rnd.choice([1, 2, 4, 8])
                mm = rnd.choice([1, 2, 4, 8, 16])
                e = rnd.randint(2, 6)
                img = rnd.randrange(I)
                src = rnd.choice([-1, -1] + list(range(R)))
                z_in = rnd.choice([0, 8, 16, 32]) if src >= 0 else 0
                z_out = rnd.choice([0, 1, 4, 9, 16])
                k = 0
                preds = []
                if idx > 0 and rnd.random() < 0.7:
                    k = rnd.randint(1, min(2, idx))
                    preds = rnd.sample(ids, k)
                jl.append([jid, c, mm, e, img, src, z_in, z_out, k] + preds)
                ids.append(jid)
                # 真实时长：租户偏置 × 对数正态噪声；另有 straggler
                dur = e * tenant_bias[o] * math.exp(rnd.gauss(0, args.sigma))
                if rnd.random() < args.straggler_p:
                    dur *= rnd.uniform(1.5, 4.0)
                durs[jid] = max(1, int(round(dur)))
            # 截止时间按关键路径给出
            es = {}
            cp = 0
            for row in jl:
                jid, e, k = row[0], row[3], row[8]
                best = 0
                for pid in row[9:9 + k]:
                    pj = es[pid]
                    if pj[0] + pj[1] > best:
                        best = pj[0] + pj[1]
                es[jid] = (best, e)
                if best + e > cp:
                    cp = best + e
            span = cp * rnd.uniform(args.deadline_lo, args.deadline_hi)
            dl = t + int(span) + rnd.randint(args.deadline_pad_lo, args.deadline_pad_hi)
            events[t].append(("WF %d %d %d %d %d" % (wid, o, v, dl, n), jl))
            wf_jobs_range.append((t, wid, ids))

    n_fail = int(M * args.fail_frac)
    for x in rnd.sample(range(M), n_fail):
        t0 = rnd.randint(2, max(3, T - 5))
        events[t0].append(("FAIL %d" % x, None))
        if rnd.random() < 0.8:
            events[min(T, t0 + rnd.randint(1, 6))].append(("UP %d" % x, None))

    for _ in range(rnd.randint(0, 2)):
        dc = rnd.randrange(D)
        t0 = rnd.randint(2, max(3, T - 4))
        events[t0].append(("DCDOWN %d" % dc, None))
        events[min(T, t0 + rnd.randint(1, 4))].append(("DCUP %d" % dc, None))

    for _ in range(args.link_events):
        e = rnd.randrange(E)
        t0 = rnd.randint(2, max(3, T - 3))
        events[t0].append(("LDOWN %d" % e, None))
        events[min(T, t0 + rnd.randint(1, 5))].append(("LUP %d" % e, None))

    for _ in range(args.quota_events):
        t0 = rnd.randint(2, max(3, T - 2))
        k = rnd.randrange(K)
        events[t0].append(("QUOTA %d %d" % (k, rnd.choice([10, 20, 40, 80, 120])), None))
        if rnd.random() < 0.5:
            events[min(T, t0 + 1)].append(("UNDO 1", None))

    for t in range(1, T + 1):
        for x in range(M):
            if rnd.random() < args.log_rate:
                ln = rnd.randint(3, args.log_len)
                syms = [8 if rnd.random() < 0.15 else rnd.randrange(8) for _ in range(ln)]
                if signal_pats and rnd.random() < 0.25:
                    pat = rnd.choice(signal_pats)[0]
                    pos = rnd.randrange(0, max(1, ln - len(pat)))
                    enc = [ord(ch) - ord("a") for ch in pat]
                    syms[pos:pos + len(enc)] = enc
                events[t].append(("LOG %d" % x, syms))

    queries = defaultdict(list)
    for t in range(1, T + 1):
        cnt = 0
        while rnd.random() < args.audit_rate and cnt < 8:
            cnt += 1
        for _ in range(cnt):
            kind = rnd.choice(["BILL", "HEAD", "ROUTE", "ALARM", "SLACK", "CACHE", "RCACHE"])
            if kind in ("BILL", "HEAD"):
                queries[t].append("%s %d" % (kind, rnd.randrange(K)))
            elif kind == "ROUTE":
                queries[t].append("ROUTE %d %d" % (rnd.randrange(R), rnd.randrange(R)))
            elif kind == "ALARM":
                queries[t].append("ALARM %d" % rnd.randrange(M))
            elif kind == "CACHE":
                queries[t].append("CACHE %d" % rnd.randrange(M))
            elif kind == "RCACHE":
                queries[t].append("RCACHE %d" % rnd.randrange(R))
            else:
                recent = [ids for (a, w, ids) in wf_jobs_range if t - 20 <= a <= t]
                if recent:
                    queries[t].append("SLACK %d" % rnd.choice(rnd.choice(recent)))

    out = ["INIT"]
    out.append("%d %d %d %d %d %d %d %d %d %d %d" % (T, D, N, R, M, K, L, I, P, W, E))
    out.append("%d %d %d %d %d" % (B_reg, B_rack, B_net, U_reg, U_net))
    out.append(" ".join(map(str, price)))
    for r in range(R):
        out.append("%d %d %d" % (rack_dc[r], rack_node[r], rack_cap[r]))
    for (r, cpu, mem, cap) in mach:
        out.append("%d %d %d %d" % (r, cpu, mem, cap))
    for (u, v, w) in edges:
        out.append("%d %d %d" % (u, v, w))
    for k in range(K):
        out.append("%d %d" % (parent[k], quota[k]))
    out.append(" ".join(map(str, sizes)))
    for layers in images:
        out.append("%d %s" % (len(layers), " ".join(map(str, layers))))
    out.append(" ".join(map(str, freq)))
    for (s, wgt) in patterns:
        out.append("%s %d" % (s, wgt))

    out.append("EVENTS")
    for t in range(1, T + 1):
        for (line, jl) in events.get(t, []):
            toks = line.split()
            if toks[0] == "LOG":
                bits = []
                for s in jl:
                    bits.extend(huff.code_of(s))
                b = len(bits)
                padded = bits + [0] * ((4 - b % 4) % 4)
                hx = "".join("%x" % int("".join(map(str, padded[i:i + 4])), 2)
                             for i in range(0, len(padded), 4))
                out.append("%d LOG %s %d %s" % (t, toks[1], b, hx))
            elif toks[0] == "WF":
                out.append("%d %s" % (t, line))
                for jlrow in jl:
                    out.append(" ".join(map(str, jlrow)))
            else:
                out.append("%d %s" % (t, line))
        for q in queries.get(t, []):
            out.append("%d ? %s" % (t, q))

    out.append("DUR")
    for jid, d in durs.items():
        out.append("%d %d" % (jid, d))
    out.append("END")

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print(f"[gen] {args.out}: T={T} D={D} N={N} R={R} M={M} K={K} L={L} I={I} P={P} E={E} "
          f"作业 {len(durs)}，事件 {sum(len(v) for v in events.values())}，"
          f"对账 {sum(len(v) for v in queries.values())}")


if __name__ == "__main__":
    main()
