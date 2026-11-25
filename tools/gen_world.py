#!/usr/bin/env python3
"""生成本仓库自定义格式的世界文件（供 tools/judge.py run 使用）。

用的参数名对齐题面里的 .in 参数文件，但生成规则是本仓库自行设计的：
目的是造出“规模与结构像正式数据”的随机世界，用来做差分测试与压力测试，
而不是复现官方生成器（官方目标值 P* 无法在本地得到）。

    python tools/gen_world.py --seed 1 --T 40 --out tests/worlds/demo.in
    python tools/gen_world.py --seed 7 --T 500 --load 3 --out tests/worlds/big.in
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge import Huffman  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
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
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

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

    # 机房单价
    price = [rnd.randint(2, 6) for _ in range(D)]

    rack_dc, rack_node, rack_cap = [], [], []
    for r in range(R):
        dc = r // args.racks_per_dc
        rack_dc.append(dc)
        rack_node.append(dc * per_dc + rnd.randrange(per_dc))
        rack_cap.append(rnd.choice([400, 800, 1600]))

    # 网络：随机生成连通图（先环形保证连通，再加边）
    edges = []
    for v in range(N - 1):
        edges.append((v, v + 1, rnd.randint(1, 20)))
    edges.append((N - 1, 0, rnd.randint(1, 20)))
    extra = max(0, min(N * 2, N + 2 * D))
    seen = {tuple(sorted((u, v))) for u, v, _ in edges}
    while len(edges) < extra:
        u, v = rnd.randrange(N), rnd.randrange(N)
        if u == v or tuple(sorted((u, v))) in seen:
            continue
        seen.add(tuple(sorted((u, v))))
        edges.append((u, v, rnd.randint(1, 20)))
    E = len(edges)

    # 租户树
    parent = [-1]
    for k in range(1, K):
        parent.append(rnd.randrange(0, k))
    quota = [rnd.choice([20, 40, 60, 90, 120]) for _ in range(K)]

    sizes = [rnd.randint(10, 120) for _ in range(L)]
    images = []
    for _ in range(I):
        k = rnd.randint(1, 3)
        images.append(sorted(rnd.sample(range(L), k)))

    freq = [rnd.randint(1, 100) for _ in range(9)]
    huff = Huffman(freq)
    patterns = []
    for _ in range(P):
        ln = rnd.randint(2, 6)
        s = "".join(rnd.choice("abcdefgh") for _ in range(ln))
        patterns.append((s, rnd.randint(1, 50)))

    B_reg, B_rack, B_net, U_reg, U_net = 60, 200, 40, 2, 1

    # 时间轴：工作流到达
    events = defaultdict(list)      # tick → [line]
    durs = {}
    wf_jobs_range = []              # (arrive, wid, [jid...])
    next_jid = [10 ** 8]

    def new_jid():
        next_jid[0] += rnd.randint(1, 97)
        return next_jid[0]

    for t in range(1, T + 1):
        cnt = 0
        while rnd.random() < args.load and cnt < 6:
            cnt += 1
        for _ in range(cnt):
            wid = 10 ** 8 + rnd.randint(0, 8 * 10 ** 8)
            o = rnd.randrange(K)
            v = rnd.choice([500, 1000, 1500, 2000, 3000])
            dl = t + rnd.randint(8, 30)
            n = rnd.randint(1, 6)
            e_scale = rnd.uniform(0.7, 1.8)
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
                line = [jid, c, mm, e, img, src, z_in, z_out, k] + preds
                jl.append(line)
                ids.append(jid)
                durs[jid] = max(1, int(round(e * e_scale * rnd.uniform(0.6, 1.6))))
            events[t].append(("WF %d %d %d %d %d" % (wid, o, v, dl, n), jl))
            wf_jobs_range.append((t, wid, ids))

    # 故障
    n_fail = int(M * args.fail_frac)
    for x in rnd.sample(range(M), n_fail):
        t0 = rnd.randint(2, max(3, T - 5))
        events[t0].append(("FAIL %d" % x, None))
        if rnd.random() < 0.8:
            events[min(T, t0 + rnd.randint(1, 6))].append(("UP %d" % x, None))

    # 停电
    for _ in range(rnd.randint(0, 2)):
        dc = rnd.randrange(D)
        t0 = rnd.randint(2, max(3, T - 4))
        events[t0].append(("DCDOWN %d" % dc, None))
        events[min(T, t0 + rnd.randint(1, 4))].append(("DCUP %d" % dc, None))

    # 链路
    for _ in range(args.link_events):
        e = rnd.randrange(E)
        t0 = rnd.randint(2, max(3, T - 3))
        events[t0].append(("LDOWN %d" % e, None))
        events[min(T, t0 + rnd.randint(1, 5))].append(("LUP %d" % e, None))

    # 配额
    for _ in range(args.quota_events):
        t0 = rnd.randint(2, max(3, T - 2))
        k = rnd.randrange(K)
        events[t0].append(("QUOTA %d %d" % (k, rnd.choice([10, 20, 40, 80, 120])), None))
        if rnd.random() < 0.5:
            events[min(T, t0 + 1)].append(("UNDO 1", None))

    # 日志
    for t in range(1, T + 1):
        for x in range(M):
            if rnd.random() < args.log_rate:
                ln = rnd.randint(3, 30)
                syms = []
                for _ in range(ln):
                    syms.append(8 if rnd.random() < 0.15 else rnd.randrange(8))
                events[t].append(("LOG %d" % x, syms))

    # 对账题
    queries = defaultdict(list)
    all_wf = []
    for t in range(1, T + 1):
        all_wf.extend(w for (a, w, ids) in wf_jobs_range if a == t)
        cnt = 0
        while rnd.random() < args.audit_rate / 2:
            cnt += 1
            if cnt > 5:
                break
        for _ in range(cnt):
            kind = rnd.choice(["BILL", "HEAD", "ROUTE", "ALARM", "SLACK",
                               "CACHE", "RCACHE"])
            if kind in ("BILL", "HEAD"):
                queries[t].append("%s %d" % (kind, rnd.randrange(K)))
            elif kind == "ROUTE":
                queries[t].append("ROUTE %d %d" % (rnd.randrange(R), rnd.randrange(R)))
            elif kind == "ALARM":
                queries[t].append("ALARM %d" % rnd.randrange(M))
            elif kind in ("CACHE",):
                queries[t].append("CACHE %d" % rnd.randrange(M))
            elif kind == "RCACHE":
                queries[t].append("RCACHE %d" % rnd.randrange(R))
            else:
                recent = [ids for (a, w, ids) in wf_jobs_range if t - 12 <= a <= t]
                if recent:
                    ids = rnd.choice(recent)
                    queries[t].append("SLACK %d" % rnd.choice(ids))

    out = []
    out.append("INIT")
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
    for (s, w) in patterns:
        out.append("%s %d" % (s, w))

    out.append("EVENTS")
    for t in range(1, T + 1):
        for (line, jl) in events.get(t, []):
            toks = line.split()
            if toks[0] == "LOG":
                syms = jl
                bits = []
                for s in syms:
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
    print(f"[gen] {args.out}: T={T} D={D} N={N} R={R} M={M} K={K} I={I} E={E} "
          f"作业 {len(durs)}，事件 {sum(len(v) for v in events.values())}，"
          f"对账 {sum(len(v) for v in queries.values())}")


if __name__ == "__main__":
    main()
