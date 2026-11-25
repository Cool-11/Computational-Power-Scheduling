#!/usr/bin/env python3
"""星环算力调度系统 —— 慢速参考实现（对账/合法性/账单的唯一事实来源）。

两种用法：

    python tools/judge.py replay tests/samples/sample1.txt
        字面回放官方交互记录：用记录里的官方 ANS 校验本参考实现。
        事件流、指令流都取自记录，不需要真实时长。

    python tools/judge.py run --world tests/worlds/demo.in --solver build/solver.exe
        驱动我方 solver：按世界里的外生事件推进，用参考实现算对账答案、
        校验指令合法性、按真实时长产生 DONE，最后结算利润。

参考实现刻意写得慢而直白：全部用 Python 字典/列表，不做索引优化，
只为“能被人读懂并逐条对照 docs/规格表.md”。
"""

from __future__ import annotations

import heapq
import subprocess
import sys
from collections import OrderedDict, deque

INF = float("inf")


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


# --------------------------------------------------------------------------
# 静态世界
# --------------------------------------------------------------------------


class World:
    """初始化段给出的静态数据。"""

    def __init__(self, toks_by_line):
        it = iter(toks_by_line)
        head = list(map(int, next(it)))
        (self.T, self.D, self.N, self.R, self.M, self.K,
         self.L, self.I, self.P, self.W, self.E) = head
        self.B_reg, self.B_rack, self.B_net, self.U_reg, self.U_net = map(int, next(it))
        self.price = list(map(int, next(it)))

        self.rack_dc = [0] * self.R
        self.rack_node = [0] * self.R
        self.rack_cap = [0] * self.R
        for r in range(self.R):
            dc, node, cap = map(int, next(it))
            self.rack_dc[r] = dc
            self.rack_node[r] = node
            self.rack_cap[r] = cap

        self.mach_rack = [0] * self.M
        self.mach_cpu = [0] * self.M
        self.mach_mem = [0] * self.M
        self.mach_cap = [0] * self.M
        for x in range(self.M):
            rk, cpu, mem, cap = map(int, next(it))
            self.mach_rack[x] = rk
            self.mach_cpu[x] = cpu
            self.mach_mem[x] = mem
            self.mach_cap[x] = cap

        self.eu = [0] * self.E
        self.ev = [0] * self.E
        self.ew = [0] * self.E
        for e in range(self.E):
            u, v, w = map(int, next(it))
            self.eu[e] = u
            self.ev[e] = v
            self.ew[e] = w

        self.tenant_parent = [0] * self.K
        self.tenant_quota0 = [0] * self.K
        for k in range(self.K):
            p, q = map(int, next(it))
            self.tenant_parent[k] = p
            self.tenant_quota0[k] = q

        self.layer_size = list(map(int, next(it)))

        self.image_layers = []
        for _ in range(self.I):
            row = list(map(int, next(it)))
            k = row[0]
            self.image_layers.append(row[1:1 + k])

        self.freq = list(map(int, next(it)))
        self.patterns = []
        for _ in range(self.P):
            row = next(it)
            self.patterns.append((row[0], int(row[1])))

        # 派生：节点 → 机房
        per_dc = self.N // self.D
        self.node_dc = [n // per_dc for n in range(self.N)]
        self.dc_down = [False] * self.D
        self.link_up = [True] * self.E

        # 邻接表
        self.adj = [[] for _ in range(self.N)]
        for e in range(self.E):
            self.adj[self.eu[e]].append((self.ev[e], self.ew[e], e))
            self.adj[self.ev[e]].append((self.eu[e], self.ew[e], e))

        self.huff = Huffman(self.freq)
        self.ac = AhoCorasick(self.patterns)


class Huffman:
    """9 个符号的 Huffman 树，权值相同取编号小的；先取出者为左子树。"""

    def __init__(self, freq):
        n = len(freq)
        self.n = n
        left = [-1] * (2 * n - 1)
        right = [-1] * (2 * n - 1)
        heap = [(freq[i], i) for i in range(n)]
        heapq.heapify(heap)
        nxt = n
        while len(heap) > 1:
            wa, a = heapq.heappop(heap)
            wb, b = heapq.heappop(heap)
            left[nxt] = a
            right[nxt] = b
            heapq.heappush(heap, (wa + wb, nxt))
            nxt += 1
        self.left = left
        self.right = right
        self.root = nxt - 1
        # 每个符号的码字（供生成世界时反向编码）
        self.codes = [None] * n
        stack = [(self.root, [])]
        while stack:
            v, pref = stack.pop()
            if v < n:
                self.codes[v] = pref
            else:
                stack.append((self.left[v], pref + [0]))
                stack.append((self.right[v], pref + [1]))

    def code_of(self, sym):
        return self.codes[sym]

    def decode(self, bit_count: int, hexstr: str) -> list:
        """把 b 位（末位补零丢弃）解码成符号编号序列。"""
        bits = []
        for ch in hexstr:
            v = int(ch, 16)
            bits.append((v >> 3) & 1)
            bits.append((v >> 2) & 1)
            bits.append((v >> 1) & 1)
            bits.append(v & 1)
        out = []
        node = self.root
        for i in range(min(bit_count, len(bits))):
            node = self.left[node] if bits[i] == 0 else self.right[node]
            if node < self.n:          # 叶子
                out.append(node)
                node = self.root
        return out


class AhoCorasick:
    """模式串重叠计数，权重累加；重复模式各自计数（权重相加）。"""

    def __init__(self, patterns):
        self.nxt = [{}]
        self.fail = [0]
        self.out = [0]
        for s, w in patterns:
            cur = 0
            for ch in s:
                node = self.nxt[cur].get(ch)
                if node is None:
                    node = len(self.nxt)
                    self.nxt[cur][ch] = node
                    self.nxt.append({})
                    self.fail.append(0)
                    self.out.append(0)
                cur = node
            self.out[cur] += w
        q = deque()
        for ch, v in self.nxt[0].items():
            self.fail[v] = 0
            q.append(v)
        while q:
            v = q.popleft()
            self.out[v] += self.out[self.fail[v]]
            for ch, u in self.nxt[v].items():
                f = self.fail[v]
                while f and ch not in self.nxt[f]:
                    f = self.fail[f]
                self.fail[u] = self.nxt[f].get(ch, 0)
                q.append(u)

    def score(self, text) -> int:
        total = 0
        v = 0
        for ch in text:
            ch = chr(ord("a") + ch) if isinstance(ch, int) else ch
            while v and ch not in self.nxt[v]:
                v = self.fail[v]
            v = self.nxt[v].get(ch, 0)
            total += self.out[v]
        return total


# --------------------------------------------------------------------------
# 动态状态
# --------------------------------------------------------------------------


class Job:
    __slots__ = ("idx", "jid", "wf", "c", "mem", "e", "img", "src_rack",
                 "z_in", "z_out", "preds", "succs", "rem", "state",
                 "machine", "start", "done_rack", "dur", "fin_tick")

    PENDING, RUNNING, DONE = 0, 1, 2

    def __init__(self):
        self.preds = []
        self.succs = []
        self.state = Job.PENDING
        self.machine = -1
        self.start = 0
        self.done_rack = -1
        self.rem = 0
        self.dur = -1
        self.fin_tick = -1


class Workflow:
    __slots__ = ("idx", "wid", "tenant", "value", "dl", "arrive", "jobs",
                 "total", "done_cnt", "abandoned", "finish")

    def __init__(self):
        self.jobs = []
        self.done_cnt = 0
        self.abandoned = False
        self.finish = -1


class Sim:
    def __init__(self, world: World):
        self.w = world
        self.t = 0
        self.healthy = [True] * world.M
        self.used_cpu = [0] * world.M
        self.used_mem = [0] * world.M

        # 两级 LRU：OrderedDict 的最后一个元素是最近使用端
        self.mcache = [OrderedDict() for _ in range(world.M)]
        self.mused = [0] * world.M
        self.rcache = [OrderedDict() for _ in range(world.R)]
        self.rused = [0] * world.R

        self.quota = list(world.tenant_quota0)
        self.used = [0] * world.K          # 子树内运行中 CPU
        self.settled = [0] * world.K
        self.rate = [0] * world.K
        self.inter = [0] * world.K
        self.undo = []                     # [(tenant, old_quota)]

        self.wfs = []
        self.wf_by_id = {}
        self.wf_fee = []            # 每个工作流已花费用（用于诊断）
        self.fee_run = 0
        self.fee_pull = 0
        self.fee_trans = 0
        self.jobs = []
        self.job_by_id = {}

        self.alarm = [dict() for _ in range(world.M)]   # tick → 分数

        self.topo_ver = 0
        self.dist_cache = {}

    # ---- 工具 -----------------------------------------------------------

    def ancestors(self, k):
        while k != -1:
            yield k
            k = self.w.tenant_parent[k]

    def rack_of_machine(self, x):
        return self.w.mach_rack[x]

    def dc_of_rack(self, r):
        return self.w.rack_dc[r]

    def dist(self, ra, rb):
        """机架 ra → 机架 rb 的最短路；不可达 -1。"""
        w = self.w
        na, nb = w.rack_node[ra], w.rack_node[rb]
        if w.dc_down[w.node_dc[na]] or w.dc_down[w.node_dc[nb]]:
            return -1
        if na == nb:
            return 0
        key = (self.topo_ver, na)
        table = self.dist_cache.get(key)
        if table is None:
            table = [INF] * w.N
            table[na] = 0
            heap = [(0, na)]
            while heap:
                d, v = heapq.heappop(heap)
                if d > table[v]:
                    continue
                if w.dc_down[w.node_dc[v]]:
                    continue
                for (to, wt, e) in w.adj[v]:
                    if not w.link_up[e]:
                        continue
                    if w.dc_down[w.node_dc[to]]:
                        continue
                    nd = d + wt
                    if nd < table[to]:
                        table[to] = nd
                        heapq.heappush(heap, (nd, to))
            self.dist_cache[key] = table
        d = table[nb]
        return -1 if d == INF else d

    def _settle(self, job: Job, r):
        """按 r 结算运行费，并释放资源；不改作业状态。"""
        w = self.w
        if job.machine < 0:
            return
        x = job.machine
        p = w.price[w.rack_dc[w.mach_rack[x]]]
        fee = job.c * p * (r - job.start)
        self.wf_fee[job.wf] += fee
        self.fee_run += fee
        for a in self.ancestors(self.wfs[job.wf].tenant):
            self.settled[a] += fee
            self.rate[a] -= job.c * p
            self.inter[a] += job.c * p * job.start
        self.used_cpu[x] -= job.c
        self.used_mem[x] -= job.mem
        for a in self.ancestors(self.wfs[job.wf].tenant):
            self.used[a] -= job.c
        job.machine = -1

    def _release(self, job: Job, r, to_pending=True):
        self._settle(job, r)
        if to_pending:
            job.state = Job.PENDING
        else:
            job.state = Job.DONE

    # ---- 事件 -----------------------------------------------------------

    def begin_tick(self, t):
        self.t = t

    def apply_event(self, toks):
        w = self.w
        kind = toks[0]
        if kind == "DONE":
            j = self.job_by_id[int(toks[1])]
            job = self.jobs[j]
            if job.state != Job.RUNNING:
                return
            x = job.machine
            self._release(job, self.t, to_pending=False)
            job.done_rack = self.w.mach_rack[x] if x >= 0 else -1
            wf = self.wfs[job.wf]
            wf.done_cnt += 1
            for s in job.succs:
                self.jobs[s].rem -= 1
            if wf.done_cnt == wf.total:
                wf.finish = self.t
        elif kind == "FAIL":
            x = int(toks[1])
            for job in self.jobs:
                if job.state == Job.RUNNING and job.machine == x:
                    self._release(job, self.t, to_pending=True)
            self.healthy[x] = False
            self.mcache[x].clear()
            self.mused[x] = 0
        elif kind == "UP":
            self.healthy[int(toks[1])] = True
        elif kind == "DCDOWN":
            w.dc_down[int(toks[1])] = True
            self.topo_ver += 1
            self.dist_cache.clear()
        elif kind == "DCUP":
            w.dc_down[int(toks[1])] = False
            self.topo_ver += 1
            self.dist_cache.clear()
        elif kind == "LDOWN":
            w.link_up[int(toks[1])] = False
            self.topo_ver += 1
            self.dist_cache.clear()
        elif kind == "LUP":
            w.link_up[int(toks[1])] = True
            self.topo_ver += 1
            self.dist_cache.clear()
        elif kind == "QUOTA":
            k, q = int(toks[1]), int(toks[2])
            self.undo.append((k, self.quota[k]))
            self.quota[k] = q
        elif kind == "UNDO":
            for _ in range(int(toks[1])):
                k, old = self.undo.pop()
                self.quota[k] = old
        elif kind == "LOG":
            x, b, h = int(toks[1]), int(toks[2]), toks[3]
            syms = w.huff.decode(b, h)
            sc = w.ac.score(syms)
            if sc:
                self.alarm[x][self.t] = self.alarm[x].get(self.t, 0) + sc
        else:
            raise ValueError("未知事件 " + " ".join(map(str, toks)))

    def add_workflow(self, toks, job_lines):
        wid, tenant, value, dl, n = (int(toks[1]), int(toks[2]), int(toks[3]),
                                     int(toks[4]), int(toks[5]))
        wf = Workflow()
        wf.idx = len(self.wfs)
        wf.wid = wid
        wf.tenant = tenant
        wf.value = value
        wf.dl = dl
        wf.arrive = self.t
        wf.total = n
        self.wfs.append(wf)
        self.wf_fee.append(0)
        self.wf_by_id[wid] = wf.idx
        for line in job_lines:
            jid, c, mem, e, img, s, z_in, z_out, k = line[:9]
            job = Job()
            job.idx = len(self.jobs)
            job.jid = jid
            job.wf = wf.idx
            job.c, job.mem, job.e, job.img = c, mem, e, img
            job.src_rack, job.z_in, job.z_out = s, z_in, z_out
            job.rem = k
            for pid in line[9:9 + k]:
                pj = self.job_by_id[pid]
                job.preds.append(pj)
                self.jobs[pj].succs.append(job.idx)
            self.jobs.append(job)
            self.job_by_id[jid] = job.idx
            wf.jobs.append(job.idx)

    # ---- 对账 -----------------------------------------------------------

    def query(self, toks):
        w = self.w
        kind = toks[0]
        if kind == "BILL":
            o = int(toks[1])
            return self.settled[o] + self.rate[o] * self.t + self.inter[o]
        if kind == "HEAD":
            o = int(toks[1])
            best = None
            for a in self.ancestors(o):
                v = self.quota[a] - self.used[a]
                if best is None or v < best:
                    best = v
            return best
        if kind == "ROUTE":
            return self.dist(int(toks[1]), int(toks[2]))
        if kind == "ALARM":
            x = int(toks[1])
            lo = self.t - w.W + 1
            if lo < 1:
                lo = 1
            tbl = self.alarm[x]
            return sum(tbl.get(tau, 0) for tau in range(lo, self.t + 1))
        if kind == "SLACK":
            return self.slack(self.job_by_id[int(toks[1])])
        if kind == "CACHE":
            return self.mused[int(toks[1])]
        if kind == "RCACHE":
            return self.rused[int(toks[1])]
        raise ValueError("未知对账 " + " ".join(map(str, toks)))

    def slack(self, ji):
        job = self.jobs[ji]
        wf = self.wfs[job.wf]
        if job.state == Job.DONE:
            return 0
        alive = [u for u in wf.jobs if self.jobs[u].state != Job.DONE]
        es = {}
        for u in alive:                       # 输入顺序即拓扑序
            ju = self.jobs[u]
            best = 0
            for p in ju.preds:
                if self.jobs[p].state == Job.DONE:
                    continue
                v = es[p] + self.jobs[p].e
                if v > best:
                    best = v
            es[u] = best
        tl = {}
        cp = 0
        for u in reversed(alive):
            ju = self.jobs[u]
            best = 0
            for s in ju.succs:
                if self.jobs[s].state == Job.DONE:
                    continue
                if tl[s] > best:
                    best = tl[s]
            tl[u] = ju.e + best
            if es[u] + tl[u] > cp:
                cp = es[u] + tl[u]
        return cp - es[ji] - tl[ji]

    # ---- 指令 -----------------------------------------------------------

    def pull_image(self, x, r, img):
        w = self.w
        q_reg = q_rack = 0
        m_lru, r_lru = self.mcache[x], self.rcache[r]
        for l in w.image_layers[img]:
            sz = w.layer_size[l]
            if l in m_lru:
                m_lru.move_to_end(l)
                continue
            if l in r_lru:
                q_rack += sz
                r_lru.move_to_end(l)
            else:
                q_reg += sz
                self._insert(r_lru, self.rused, r, l, sz, w.rack_cap[r])
            self._insert(m_lru, self.mused, x, l, sz, w.mach_cap[x])
        return q_reg, q_rack

    def _insert(self, lru, used, idx, layer, size, cap):
        if layer in lru:
            lru.move_to_end(layer)
            return
        lru[layer] = size
        used[idx] += size
        while used[idx] > cap and lru:
            old, osz = lru.popitem(last=False)
            used[idx] -= osz

    def check_run(self, jid, x):
        """返回 (ok, msg, 计费信息)。不改状态。"""
        w = self.w
        if jid not in self.job_by_id:
            return False, "未知作业", None
        ji = self.job_by_id[jid]
        job = self.jobs[ji]
        wf = self.wfs[job.wf]
        if job.state != Job.PENDING:
            return False, "作业不在待运行", None
        if wf.abandoned:
            return False, "工作流已放弃", None
        if job.rem != 0:
            return False, "前驱未完成", None
        if not self.healthy[x]:
            return False, "机器故障", None
        if self.used_cpu[x] + job.c > w.mach_cpu[x]:
            return False, "CPU 不足", None
        if self.used_mem[x] + job.mem > w.mach_mem[x]:
            return False, "内存不足", None
        for a in self.ancestors(wf.tenant):
            if self.used[a] + job.c > self.quota[a]:
                return False, "配额不足(租户 %d)" % a, None
        r = w.mach_rack[x]
        inputs = []
        if job.src_rack != -1 and job.src_rack != r:
            inputs.append((job.src_rack, job.z_in))
        for p in job.preds:
            pj = self.jobs[p]
            if pj.done_rack != r:
                inputs.append((pj.done_rack, pj.z_out))
        t_tr = 0
        cost_tr = 0
        for (s, z) in inputs:
            d = self.dist(r, s)
            if d < 0:
                return False, "输入不可达(机架 %d)" % s, None
            t_tr = max(t_tr, d + ceil_div(z, w.B_net))
            cost_tr += z * d * w.U_net
        return True, "", (r, inputs, t_tr, cost_tr)

    def apply_run(self, jid, x, info=None):
        w = self.w
        job = self.jobs[self.job_by_id[jid]]
        if info is None:
            ok, msg, info = self.check_run(jid, x)
            if not ok:
                raise RuntimeError("非法 RUN: " + msg)
        r, inputs, t_tr, cost_tr = info
        q_reg, q_rack = self.pull_image(x, r, job.img)
        t_pull = ceil_div(q_reg, w.B_reg) + ceil_div(q_rack, w.B_rack)
        fee = cost_tr + q_reg * w.U_reg
        wf = self.wfs[job.wf]
        self.wf_fee[job.wf] += fee
        self.fee_trans += cost_tr
        self.fee_pull += q_reg * w.U_reg
        for a in self.ancestors(wf.tenant):
            self.settled[a] += fee
        d = w.rack_dc[r]
        p = w.price[d]
        self.used_cpu[x] += job.c
        self.used_mem[x] += job.mem
        for a in self.ancestors(wf.tenant):
            self.used[a] += job.c
            self.rate[a] += job.c * p
            self.inter[a] -= job.c * p * self.t
        job.state = Job.RUNNING
        job.machine = x
        job.start = self.t
        return max(t_tr, t_pull), fee

    def apply_kill(self, jid):
        job = self.jobs[self.job_by_id[jid]]
        if job.state != Job.RUNNING:
            raise RuntimeError("KILL 非运行作业")
        self._release(job, self.t, to_pending=True)

    def apply_drop(self, wid):
        wf = self.wfs[self.wf_by_id[wid]]
        if wf.abandoned or wf.finish != -1:
            raise RuntimeError("DROP 非法工作流")
        for ji in wf.jobs:
            if self.jobs[ji].state == Job.RUNNING:
                raise RuntimeError("DROP 时工作流仍有运行作业")
        wf.abandoned = True

    def apply_instruction(self, toks):
        if toks[0] == "RUN":
            return self.apply_run(toks[1], toks[2])
        if toks[0] == "KILL":
            return self.apply_kill(toks[1])
        if toks[0] == "DROP":
            return self.apply_drop(toks[1])
        raise ValueError("未知指令 " + " ".join(map(str, toks)))

    # ---- 结算 -----------------------------------------------------------

    def final_profit(self, end_tick=None):
        """按第 T 轮结束后仍在运行的作业以 r=T+1 结算，返回 (利润, 明细)。"""
        w = self.w
        t = end_tick if end_tick is not None else w.T
        # 全平台总费用 = 根租户在 t+1 时刻的账单（含仍运行作业按 r=t+1 结算）
        total_fee = self.settled[0] + self.rate[0] * (t + 1) + self.inter[0]
        revenue = 0
        for wf in self.wfs:
            if wf.finish != -1:
                revenue += revenue_of(wf)
        return revenue - total_fee, revenue, total_fee


def revenue_of(wf):
    a, dl, v = wf.arrive, wf.dl, wf.value
    f = wf.finish
    g = max(5, (dl - a) // 3)
    if f <= dl:
        return v
    if f < dl + g:
        return v * (dl + g - f) // g
    return 0


# --------------------------------------------------------------------------
# 回放：用官方记录校验参考实现
# --------------------------------------------------------------------------


def load_transcript(path):
    """返回 (init_lines, ticks)；ticks 为 [(t, events_lines, query_lines, ans, instrs)]。"""
    raw = [ln.rstrip("\n") for ln in open(path, encoding="utf-8")]
    lines = [ln.strip() for ln in raw if ln.strip()]
    pos = 0

    def take(n=1):
        nonlocal pos
        out = lines[pos:pos + n]
        pos += n
        return out

    head = list(map(int, take()[0].split()))
    T, D, N, R, M, K, L, I, P, W, E = head
    init = [head]
    init.append(list(map(int, take()[0].split())))
    init.append(list(map(int, take()[0].split())))
    init += [[int(v) for v in take()[0].split()] for _ in range(R)]
    init += [[int(v) for v in take()[0].split()] for _ in range(M)]
    init += [[int(v) for v in take()[0].split()] for _ in range(E)]
    init += [[int(v) for v in take()[0].split()] for _ in range(K)]
    init.append(list(map(int, take()[0].split())))
    init += [[int(v) for v in take()[0].split()] for _ in range(I)]
    init.append(list(map(int, take()[0].split())))
    for _ in range(P):
        s, wgt = take()[0].split()
        init.append([s, int(wgt)])

    ticks = []
    while pos < len(lines):
        first = take()[0].split()
        if first[0] != "TICK":
            raise ValueError("期望 TICK，遇到 " + " ".join(first))
        t, ne, nq = int(first[1]), int(first[2]), int(first[3])
        events = []
        for _ in range(ne):
            toks = take()[0].split()
            if toks[0] == "WF":
                n = int(toks[5])
                events.append((toks, take(n)))
            else:
                events.append((toks, []))
        queries = [take()[0].split() for _ in range(nq)]
        ans_line = take()[0].split()
        if ans_line[0] != "ANS":
            raise ValueError("期望 ANS，遇到 " + " ".join(ans_line))
        ans = [int(v) for v in ans_line[1:]]
        instrs = []
        while True:
            line = take()[0].split()
            if line[0] == "END":
                break
            instrs.append((line[0], int(line[1]), int(line[2]) if len(line) > 2 else 0))
        ticks.append((t, events, queries, ans, instrs))
    return init, ticks


def replay(path, verbose=False):
    init, ticks = load_transcript(path)
    world = World(init)
    sim = Sim(world)

    n_q = 0
    bad = 0
    first_bad = None
    for (t, events, queries, ans, instrs) in ticks:
        sim.begin_tick(t)
        for (toks, jl) in events:
            if toks[0] == "WF":
                sim.add_workflow(toks, [list(map(int, x.split())) for x in jl])
            else:
                sim.apply_event(toks)
        if len(ans) != len(queries):
            raise ValueError("ANS 数量与问题数不符，tick %d" % t)
        for i, q in enumerate(queries):
            got = sim.query(q)
            n_q += 1
            if got != ans[i]:
                bad += 1
                if first_bad is None:
                    first_bad = (t, q, ans[i], got)
                if verbose:
                    print(f"  [t={t}] {' '.join(q)}: 官方 {ans[i]} 参考 {got}")
        for ins in instrs:
            try:
                sim.apply_instruction(list(ins))
            except RuntimeError as exc:
                print(f"  [t={t}] 指令非法 {ins}: {exc}")
                bad += 1
                if first_bad is None:
                    first_bad = (t, list(ins), "合法", str(exc))
    print(f"[replay] {path}")
    print(f"  对账题 {n_q} 道，与官方答案不一致 {bad} 处")
    if first_bad:
        print(f"  第一处：tick {first_bad[0]} {' '.join(map(str, first_bad[1]))} "
              f"官方/期望 {first_bad[2]}，参考 {first_bad[3]}")
    else:
        print("  全部一致 ✅")
    return bad == 0


# --------------------------------------------------------------------------
# 世界文件（本仓库自定义格式）与驱动模式
# --------------------------------------------------------------------------

CAT = {"DONE": 0, "FAIL": 1, "UP": 2, "DCDOWN": 3, "DCUP": 4, "LDOWN": 5,
       "LUP": 6, "QUOTA": 7, "UNDO": 8, "LOG": 9, "WF": 10}


def parse_init_text(lines):
    """把初始化段的原始文本行解析成 World 需要的 tokens_by_line。"""
    pos = 0

    def take():
        nonlocal pos
        pos += 1
        return lines[pos - 1].split()

    head = list(map(int, take()))
    T, D, N, R, M, K, L, I, P, W, E = head
    out = [head]
    out.append(list(map(int, take())))
    out.append(list(map(int, take())))
    for _ in range(R):
        out.append(list(map(int, take())))
    for _ in range(M):
        out.append(list(map(int, take())))
    for _ in range(E):
        out.append(list(map(int, take())))
    for _ in range(K):
        out.append(list(map(int, take())))
    out.append(list(map(int, take())))          # 层大小
    for _ in range(I):
        out.append(list(map(int, take())))
    out.append(list(map(int, take())))          # 9 个频数
    for _ in range(P):
        s, wt = take()
        out.append([s, int(wt)])
    return out


def load_world(path):
    """返回 (init_lines, events, durs)；events = [(tick, body_tokens, job_lines|None)]。"""
    raw = [ln.strip() for ln in open(path, encoding="utf-8")]
    lines = [ln for ln in raw if ln and not ln.startswith("#")]
    sec = None
    init_lines, events, durs = [], [], {}
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln in ("INIT", "EVENTS", "DUR", "END"):
            sec = ln
            i += 1
            continue
        if sec == "INIT":
            init_lines.append(ln)
            i += 1
        elif sec == "EVENTS":
            toks = ln.split()
            t, body = int(toks[0]), toks[1:]
            if body[0] == "WF":
                n = int(body[5])
                jl = [lines[i + 1 + k].split() for k in range(n)]
                events.append((t, body, jl))
                i += 1 + n
            else:
                events.append((t, body, None))
                i += 1
        elif sec == "DUR":
            a, b = ln.split()
            durs[int(a)] = int(b)
            i += 1
        else:
            i += 1
    return init_lines, events, durs


def _num(tok):
    try:
        return int(tok)
    except ValueError:
        return tok


def _read_line(proc, timeout):
    import threading
    box = {}

    def rd():
        try:
            box["line"] = proc.stdout.readline()
        except Exception as exc:                      # noqa: BLE001
            box["line"] = b""
            box["err"] = exc

    th = threading.Thread(target=rd, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        return None
    return box.get("line")


def run_world(world_path, solver_exe, timeout=30.0, verbose=False):
    init_lines, events, durs = load_world(world_path)
    world = World(parse_init_text(init_lines))
    sim = Sim(world)

    ev_by_tick = {}
    q_by_tick = {}
    for (t, body, jl) in events:
        if body[0] == "?":
            q_by_tick.setdefault(t, []).append(body[1:])
        else:
            ev_by_tick.setdefault(t, []).append((body, jl))

    due = {}                    # tick → [job_idx]
    util_sum = 0.0
    util_n = 0

    proc = subprocess.Popen([solver_exe], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, bufsize=0)
    send = lambda s: proc.stdin.write(s.encode()) or proc.stdin.flush()

    send("\n".join(init_lines) + "\n")

    n_q = 0
    bad_q = 0
    first_bad = None
    illegal = None
    instr_count = 0
    prep_sum = 0
    prep_n = 0
    prep_max = 0

    for t in range(1, world.T + 1):
        sim.begin_tick(t)
        # 组装本 tick 事件：DONE 在前，其余按类别顺序
        units = []
        seen_done = set()
        for ji in due.get(t, []):
            job = sim.jobs[ji]
            if job.state == Job.RUNNING and job.fin_tick == t and ji not in seen_done:
                seen_done.add(ji)
                units.append((CAT["DONE"], ["DONE", job.jid], None))
        for (body, jl) in ev_by_tick.get(t, []):
            units.append((CAT.get(body[0], 99), body, jl))
        units.sort(key=lambda u: u[0])

        queries = q_by_tick.get(t, [])
        ne = len(units)
        nq = len(queries)
        buf = ["TICK %d %d %d" % (t, ne, nq)]
        for (_, body, jl) in units:
            if body[0] == "WF":
                buf.append(" ".join(body))
                for line in jl:
                    buf.append(" ".join(line))
            else:
                buf.append(" ".join(str(x) for x in body))
        # 交给参考实现
        for (_, body, jl) in units:
            if body[0] == "WF":
                sim.add_workflow(body, [[int(v) for v in line] for line in jl])
            else:
                sim.apply_event(body)
        expect = []
        for q in queries:
            expect.append(sim.query(q))
            buf.append(" ".join(str(x) for x in q))
        n_q += nq

        send("\n".join(buf) + "\n")

        line = _read_line(proc, timeout)
        if line is None:
            print(f"[judge] tick {t}: 求解器 {timeout}s 内无输出，判定卡住")
            proc.kill()
            return False
        line = line.decode(errors="replace").strip()
        if not line.startswith("ANS"):
            print(f"[judge] tick {t}: 期望 ANS，收到 {line!r}")
            proc.kill()
            return False
        got = [int(v) for v in line.split()[1:]]
        if len(got) != nq:
            print(f"[judge] tick {t}: ANS 数量 {len(got)} ≠ {nq}")
            proc.kill()
            return False
        for i in range(nq):
            if got[i] != expect[i]:
                bad_q += 1
                if first_bad is None:
                    first_bad = (t, " ".join(str(x) for x in queries[i]), expect[i], got[i])
                if verbose:
                    print(f"  [t={t}] {' '.join(str(x) for x in queries[i])}: "
                          f"期望 {expect[i]} 得到 {got[i]}")

        util_sum += sum(sim.used_cpu) / max(1, sum(world.mach_cpu))
        util_n += 1

        # 指令
        while True:
            line = _read_line(proc, timeout)
            if line is None:
                print(f"[judge] tick {t}: 等待 END 超时")
                proc.kill()
                return False
            line = line.decode(errors="replace").strip()
            if line == "END":
                break
            if not line:
                continue
            toks = line.split()
            instr_count += 1
            if illegal is None:
                try:
                    if toks[0] == "RUN":
                        jid, x = int(toks[1]), int(toks[2])
                        ok, msg, info = sim.check_run(jid, x)
                        if not ok:
                            if verbose:
                                jj = sim.jobs[sim.job_by_id[jid]]
                                print("  诊断: 作业", jj.jid, "state", jj.state, "rem", jj.rem,
                                      "前驱", [(sim.jobs[p].jid, sim.jobs[p].state)
                                              for p in jj.preds])
                            raise RuntimeError(msg)
                        s_prep, _ = sim.apply_run(jid, x, info)
                        ji = sim.job_by_id[jid]
                        d = durs.get(jid, sim.jobs[ji].e)
                        sim.jobs[ji].dur = d
                        sim.jobs[ji].fin_tick = t + s_prep + d
                        prep_sum += s_prep
                        prep_n += 1
                        prep_max = max(prep_max, s_prep)
                        due.setdefault(sim.jobs[ji].fin_tick, []).append(ji)
                    elif toks[0] == "KILL":
                        sim.apply_kill(int(toks[1]))
                    elif toks[0] == "DROP":
                        sim.apply_drop(int(toks[1]))
                    else:
                        raise RuntimeError("未知指令 " + toks[0])
                except RuntimeError as exc:
                    illegal = (t, line, str(exc))
                    if verbose:
                        print(f"  [t={t}] 非法指令 {line}: {exc}")
            if illegal is not None:
                continue

    profit, revenue, fee = sim.final_profit()
    done_wf = sum(1 for wf in sim.wfs if wf.finish != -1)
    waste = sum(sim.wf_fee[i] for i, wf in enumerate(sim.wfs) if wf.finish == -1)
    ok_fee = sum(sim.wf_fee[i] for i, wf in enumerate(sim.wfs) if wf.finish != -1)

    print(f"[judge] {world_path} vs {solver_exe}")
    print(f"  对账 {n_q} 道，错 {bad_q}" + ("" if not first_bad else
          f"；第一处 t={first_bad[0]} {first_bad[1]} 期望 {first_bad[2]} 得到 {first_bad[3]}"))
    print(f"  指令 {instr_count} 条，" + ("全部合法" if illegal is None else
          f"首次非法 t={illegal[0]} {illegal[1]}（{illegal[2]}）"))
    print(f"  完成工作流 {done_wf}/{len(sim.wfs)}，收益 {revenue}，费用 {fee}，利润 {profit}")
    print(f"  费用构成：完成的工作流 {ok_fee}，未完成（浪费）{waste}")
    print(f"  费用明细：运行 {sim.fee_run}，拉取 {sim.fee_pull}，传输 {sim.fee_trans}")
    n_running = sum(1 for j in sim.jobs if j.state == Job.RUNNING)
    print(f"  结束仍运行作业 {n_running} 个")
    print(f"  平均准备时间 {prep_sum / max(1, prep_n):.1f} tick（最大 {prep_max}）")
    print(f"  平均 CPU 占用率 {util_sum / max(1, util_n):.2%}，指令 {instr_count} 条")
    try:
        proc.wait(timeout=5)
    except Exception:                                  # noqa: BLE001
        proc.kill()
    return bad_q == 0 and illegal is None


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    mode = argv[1]
    if mode == "replay":
        ok = replay(argv[2], verbose="-v" in argv)
        return 0 if ok else 1
    if mode == "run":
        world_path = solver = None
        timeout = 30.0
        i = 2
        while i < len(argv):
            if argv[i] == "--world":
                world_path = argv[i + 1]
                i += 2
            elif argv[i] == "--solver":
                solver = argv[i + 1]
                i += 2
            elif argv[i] == "--timeout":
                timeout = float(argv[i + 1])
                i += 2
            else:
                i += 1
        if not world_path or not solver:
            print("用法: judge.py run --world W.in --solver build/solver.exe")
            return 2
        ok = run_world(world_path, solver, timeout=timeout, verbose="-v" in argv)
        return 0 if ok else 1
    print("未知模式 " + mode)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
