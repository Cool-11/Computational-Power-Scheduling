// 星环算力调度系统 —— 交互式调度器（C++17）
//
// 协议：读 TICK t ne nq → 按序处理 ne 个事件 → 回答 nq 个对账 → 输出 ANS →
//       按序输出 RUN/KILL/DROP（逐条改内部状态）→ 输出 END 并刷新；第 T 轮后退出。
//
// 规格见 docs/规格表.md。本文件自包含，可直接作为 OJ 提交物。

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <climits>
#include <string>
#include <vector>
#include <algorithm>
#include <queue>
#include <unordered_map>

#ifdef _WIN32
#include <io.h>
#else
#include <unistd.h>
#endif

typedef long long ll;

// ============================================================ 快速输入输出

namespace io {

#ifdef _WIN32
static inline int sys_read(int fd, char* buf, int n) { return (int)_read(fd, buf, n); }
#else
static inline int sys_read(int fd, char* buf, int n) { return (int)::read(fd, buf, n); }
#endif

static const int IN_BUF = 1 << 16;
static char in_buf[IN_BUF];
static int in_len = 0, in_pos = 0;

static inline int gc() {
    if (in_pos >= in_len) {
        in_len = sys_read(0, in_buf, IN_BUF);
        in_pos = 0;
        if (in_len <= 0) return -1;
    }
    return (unsigned char)in_buf[in_pos++];
}

static inline void skip_ws() {
    int c = gc();
    while (c == ' ' || c == '\n' || c == '\r' || c == '\t') c = gc();
    if (c >= 0) --in_pos;
}

static inline ll read_int() {
    skip_ws();
    int c = gc();
    bool neg = false;
    if (c == '-') { neg = true; c = gc(); }
    ll v = 0;
    while (c >= '0' && c <= '9') { v = v * 10 + (c - '0'); c = gc(); }
    if (c >= 0) --in_pos;
    return neg ? -v : v;
}

// 读单词：字母/数字/下划线
static inline void read_word(char* out, int cap) {
    skip_ws();
    int n = 0;
    int c = gc();
    while (c > ' ') {
        if (n < cap - 1) out[n++] = (char)c;
        c = gc();
    }
    out[n] = '\0';
    if (c >= 0) --in_pos;
}

static inline void read_word(std::string& out) {
    skip_ws();
    out.clear();
    int c = gc();
    while (c > ' ') {
        out.push_back((char)c);
        c = gc();
    }
    if (c >= 0) --in_pos;
}

}  // namespace io

// ============================================================ 静态世界

static int T_, D_, N_, R_, M_, K_, L_, I_, P_, W_, E_;
static ll B_reg, B_rack, B_net, U_reg, U_net;

static std::vector<ll> price;
static std::vector<int> rack_dc, rack_node;
static std::vector<ll> rack_cap;
static std::vector<int> mach_rack;
static std::vector<ll> mach_cpu, mach_mem, mach_cap;
static std::vector<int> eu_, ev_;
static std::vector<ll> ew_;
static std::vector<int> parent_;
static std::vector<ll> quota0;
static std::vector<ll> layer_size;
static std::vector<std::vector<int>> image_layers;
static ll freq9[9];

// 邻接表（CSR）
static std::vector<int> adj_head, adj_to, adj_w, adj_eid, adj_next;

static void read_init() {
    using io::read_int;
    T_ = (int)read_int(); D_ = (int)read_int(); N_ = (int)read_int();
    R_ = (int)read_int(); M_ = (int)read_int(); K_ = (int)read_int();
    L_ = (int)read_int(); I_ = (int)read_int(); P_ = (int)read_int();
    W_ = (int)read_int(); E_ = (int)read_int();

    B_reg = read_int(); B_rack = read_int(); B_net = read_int();
    U_reg = read_int(); U_net = read_int();

    price.resize(D_);
    for (int d = 0; d < D_; ++d) price[d] = read_int();

    rack_dc.resize(R_); rack_node.resize(R_); rack_cap.resize(R_);
    for (int r = 0; r < R_; ++r) {
        rack_dc[r] = (int)read_int();
        rack_node[r] = (int)read_int();
        rack_cap[r] = read_int();
    }

    mach_rack.resize(M_); mach_cpu.resize(M_);
    mach_mem.resize(M_); mach_cap.resize(M_);
    for (int x = 0; x < M_; ++x) {
        mach_rack[x] = (int)read_int();
        mach_cpu[x] = read_int();
        mach_mem[x] = read_int();
        mach_cap[x] = read_int();
    }

    eu_.resize(E_); ev_.resize(E_); ew_.resize(E_);
    for (int e = 0; e < E_; ++e) {
        eu_[e] = (int)read_int();
        ev_[e] = (int)read_int();
        ew_[e] = read_int();
    }

    parent_.resize(K_); quota0.resize(K_);
    for (int k = 0; k < K_; ++k) {
        parent_[k] = (int)read_int();
        quota0[k] = read_int();
    }

    layer_size.resize(L_);
    for (int l = 0; l < L_; ++l) layer_size[l] = read_int();

    image_layers.resize(I_);
    for (int i = 0; i < I_; ++i) {
        int k = (int)read_int();
        image_layers[i].resize(k);
        for (int j = 0; j < k; ++j) image_layers[i][j] = (int)read_int();
    }

    for (int s = 0; s < 9; ++s) freq9[s] = read_int();

    adj_head.assign(N_, -1);
    int arc = 0;
    adj_to.resize(2 * E_); adj_w.resize(2 * E_); adj_eid.resize(2 * E_); adj_next.resize(2 * E_);
    for (int e = 0; e < E_; ++e) {
        int u = eu_[e], v = ev_[e];
        adj_to[arc] = v; adj_w[arc] = (int)ew_[e]; adj_eid[arc] = e; adj_next[arc] = adj_head[u]; adj_head[u] = arc++;
        adj_to[arc] = u; adj_w[arc] = (int)ew_[e]; adj_eid[arc] = e; adj_next[arc] = adj_head[v]; adj_head[v] = arc++;
    }
}

// ============================================================ Huffman

static int huff_left[32], huff_right[32], huff_root;
static ll huff_w[32];

static void build_huffman(const ll freq[9]) {
    ll w[32];
    int left[32], right[32];
    for (int i = 0; i < 9; ++i) { w[i] = freq[i]; left[i] = right[i] = -1; }
    int alive[32], n = 9;
    for (int i = 0; i < 9; ++i) alive[i] = i;
    int next_id = 9;
    while (n > 1) {
        // 找 (权重, 编号) 最小的两棵树：pa 最小，pb 次小
        int pa = 0, pb = 1;
        if (w[alive[0]] > w[alive[1]] ||
            (w[alive[0]] == w[alive[1]] && alive[0] > alive[1])) { pa = 1; pb = 0; }
        for (int i = 2; i < n; ++i) {
            int c = alive[i];
            if (w[c] < w[alive[pa]] || (w[c] == w[alive[pa]] && c < alive[pa])) {
                pb = pa;
                pa = i;
            } else if (w[c] < w[alive[pb]] || (w[c] == w[alive[pb]] && c < alive[pb])) {
                pb = i;
            }
        }
        int ida = alive[pa], idb = alive[pb];
        left[next_id] = ida;
        right[next_id] = idb;
        w[next_id] = w[ida] + w[idb];
        int lo = std::min(pa, pb), hi = std::max(pa, pb);
        alive[lo] = next_id;
        for (int i = hi; i < n - 1; ++i) alive[i] = alive[i + 1];
        --n;
        ++next_id;
    }
    huff_root = alive[0];
    for (int i = 0; i < next_id; ++i) {
        huff_left[i] = left[i];
        huff_right[i] = right[i];
        huff_w[i] = w[i];
    }
}

// ============================================================ Aho–Corasick

struct AhoCorasick {
    std::vector<int> go;      // states * 9
    std::vector<int> fail;
    std::vector<ll> out;
    int states = 1;

    void init() {
        go.assign(9, 0);
        fail.assign(1, 0);
        out.assign(1, 0);
    }

    void add(const std::string& pat, ll weight) {
        int cur = 0;
        for (char ch : pat) {
            int c = ch - 'a';
            int nxt = go[cur * 9 + c];
            if (nxt == 0) {
                nxt = states++;
                go.resize((size_t)states * 9, 0);
                fail.push_back(0);
                out.push_back(0);
                go[cur * 9 + c] = nxt;
            }
            cur = nxt;
        }
        out[cur] += weight;
    }

    void build() {
        std::queue<int> q;
        for (int c = 0; c < 9; ++c) {
            int v = go[c];
            if (v) { fail[v] = 0; q.push(v); }
        }
        while (!q.empty()) {
            int v = q.front(); q.pop();
            out[v] += out[fail[v]];
            for (int c = 0; c < 9; ++c) {
                int u = go[(size_t)v * 9 + c];
                if (u) {
                    fail[u] = go[(size_t)fail[v] * 9 + c];
                    q.push(u);
                } else {
                    go[(size_t)v * 9 + c] = go[(size_t)fail[v] * 9 + c];
                }
            }
        }
    }

    inline ll step(int st, int sym) const { return out[go[(size_t)st * 9 + sym]]; }
};

static AhoCorasick ac;

// ============================================================ 动态状态

struct Job {
    int ext_id = 0;
    int wf = -1;
    int c = 0;
    ll m = 0;
    int e = 0;
    int img = 0;
    int src_rack = -1;
    ll z_in = 0, z_out = 0;
    int state = 0;              // 0 pending, 1 running, 2 done
    int mach = -1;
    int start = 0;
    int rem = 0;
    int done_rack = -1;
    std::vector<int> preds;
    std::vector<int> succs;
};

struct Wf {
    int tenant = 0;
    ll value = 0;
    int dl = 0;
    int arrive = 0;
    int total = 0;
    int done_cnt = 0;
    bool abandoned = false;
    int finish = -1;
    int job_begin = 0, job_end = 0;
    // SLACK 缓存
    int slack_ver = -1;
    std::vector<int> es, tl;
    ll cp = 0;
};

static std::vector<Job> jobs;
static std::vector<Wf> wfs;
static std::unordered_map<int, int> job_id;
static std::unordered_map<int, int> wf_id;

// 租户
static std::vector<ll> quota, tused, settled, rate_, inter_;
static std::vector<std::pair<int, ll>> undo_stack;

// 机器
static std::vector<char> healthy;
static std::vector<ll> used_cpu, used_mem;

// 两级 LRU 缓存（稠密索引：cache * L + layer）
struct LruSet {
    int nc = 0, nl = 0;
    std::vector<int> prv, nxt, present, head, tail;
    std::vector<ll> used;
    const std::vector<ll>* cap = nullptr;

    void init(int nc_, int nl_, const std::vector<ll>& cap_) {
        nc = nc_; nl = nl_; cap = &cap_;
        prv.assign((size_t)nc * nl, -1);
        nxt.assign((size_t)nc * nl, -1);
        present.assign((size_t)nc * nl, 0);
        head.assign(nc, -1);
        tail.assign(nc, -1);
        used.assign(nc, 0);
    }

    inline bool has(int c, int l) const { return present[(size_t)c * nl + l] != 0; }
    inline ll used_of(int c) const { return used[c]; }

    void unlink(int c, int l) {
        size_t id = (size_t)c * nl + l;
        int p = prv[id], n = nxt[id];
        if (p >= 0) nxt[(size_t)c * nl + p] = n; else head[c] = n;
        if (n >= 0) prv[(size_t)c * nl + n] = p; else tail[c] = p;
        prv[id] = nxt[id] = -1;
    }

    void push_front(int c, int l) {
        size_t id = (size_t)c * nl + l;
        prv[id] = -1;
        nxt[id] = head[c];
        if (head[c] >= 0) prv[(size_t)c * nl + head[c]] = l;
        head[c] = l;
        if (tail[c] < 0) tail[c] = l;
    }

    void touch(int c, int l) {
        if (head[c] == l) return;
        unlink(c, l);
        push_front(c, l);
    }

    // 插入（已存在则移到最近端），每次插入后立即淘汰
    void insert(int c, int l, ll sz) {
        if (has(c, l)) { touch(c, l); return; }
        present[(size_t)c * nl + l] = 1;
        push_front(c, l);
        used[c] += sz;
        while (used[c] > (*cap)[c] && head[c] >= 0) {
            int victim = tail[c];
            unlink(c, victim);
            present[(size_t)c * nl + victim] = 0;
            used[c] -= layer_size[victim];
        }
    }

    void clear(int c) {
        int l = head[c];
        while (l >= 0) {
            int n = nxt[(size_t)c * nl + l];
            present[(size_t)c * nl + l] = 0;
            prv[(size_t)c * nl + l] = nxt[(size_t)c * nl + l] = -1;
            l = n;
        }
        head[c] = tail[c] = -1;
        used[c] = 0;
    }
};

static LruSet mc, rc;

// 网络
static std::vector<char> link_up, dc_down;
static std::vector<int> dist_ver;
static std::vector<std::vector<ll>> dist_tab;
static int topo_ver = 0;

// 告警：per (tick, machine) 的分数 + 窗口和
static std::vector<ll> alarm_at;       // (T+2) * M
static std::vector<ll> alarm_win;      // M

// 每机器运行中作业
static std::vector<std::vector<int>> mach_running;

// 就绪队列
static std::vector<int> ready_list;

static std::string out_buf;

// ---------------------------------------------------------------- 初始化

static void init_dynamic() {
    jobs.reserve(70000);
    jobs.resize(0);
    wfs.reserve(20000);
    wfs.resize(0);

    quota.assign(quota0.begin(), quota0.end());
    tused.assign(K_, 0);
    settled.assign(K_, 0);
    rate_.assign(K_, 0);
    inter_.assign(K_, 0);
    undo_stack.reserve(1024);

    healthy.assign(M_, 1);
    used_cpu.assign(M_, 0);
    used_mem.assign(M_, 0);
    mach_running.assign(M_, std::vector<int>());

    mc.init(M_, L_, mach_cap);
    rc.init(R_, L_, rack_cap);

    link_up.assign(E_, 1);
    dc_down.assign(D_, 0);
    dist_ver.assign(N_, -1);
    dist_tab.assign(N_, std::vector<ll>());

    alarm_at.assign((size_t)(T_ + 2) * M_, 0);
    alarm_win.assign(M_, 0);

    out_buf.reserve(1 << 16);
}

// ---------------------------------------------------------------- 网络距离

// 返回机架 ra 到 rb 的最短路；不可达 -1。ROUTE 与 RUN 共用。
static int node_dc_of(int node) { return node * D_ / N_; }

static ll rack_dist(int ra, int rb) {
    int na = rack_node[ra], nb = rack_node[rb];
    if (dc_down[node_dc_of(na)] || dc_down[node_dc_of(nb)]) return -1;
    if (na == nb) return 0;
    if (dist_ver[na] != topo_ver) {
        if (dist_tab[na].empty()) dist_tab[na].assign(N_, LLONG_MAX);
        std::vector<ll>& tab = dist_tab[na];
        std::fill(tab.begin(), tab.end(), LLONG_MAX);
        std::priority_queue<std::pair<ll, int>, std::vector<std::pair<ll, int>>,
                            std::greater<std::pair<ll, int>>> pq;
        tab[na] = 0;
        pq.push({0, na});
        while (!pq.empty()) {
            auto [d, v] = pq.top(); pq.pop();
            if (d != tab[v]) continue;
            if (dc_down[node_dc_of(v)]) continue;
            for (int a = adj_head[v]; a != -1; a = adj_next[a]) {
                if (!link_up[adj_eid[a]]) continue;
                int to = adj_to[a];
                if (dc_down[node_dc_of(to)]) continue;
                ll nd = d + adj_w[a];
                if (nd < tab[to]) { tab[to] = nd; pq.push({nd, to}); }
            }
        }
        dist_ver[na] = topo_ver;
    }
    ll d = dist_tab[na][nb];
    return d == LLONG_MAX ? -1 : d;
}

// ---------------------------------------------------------------- 账单

static inline void add_fee(int tenant, ll fee) {
    for (int a = tenant; a != -1; a = parent_[a]) settled[a] += fee;
}

static void settle_job(int ji, int r) {
    Job& j = jobs[ji];
    if (j.mach < 0) return;
    int x = j.mach;
    int d = rack_dc[mach_rack[x]];
    ll p = price[d];
    ll fee = (ll)j.c * p * (ll)(r - j.start);
    int tenant = wfs[j.wf].tenant;
    for (int a = tenant; a != -1; a = parent_[a]) {
        settled[a] += fee;
        rate_[a] -= (ll)j.c * p;
        inter_[a] += (ll)j.c * p * (ll)j.start;
        tused[a] -= j.c;
    }
    used_cpu[x] -= j.c;
    used_mem[x] -= j.m;
    j.mach = -1;
}

// ---------------------------------------------------------------- 拉取镜像

static void pull_image(int x, int r, int img, ll& q_reg, ll& q_rack) {
    q_reg = 0;
    q_rack = 0;
    const std::vector<int>& layers = image_layers[img];
    for (int l : layers) {
        ll sz = layer_size[l];
        if (mc.has(x, l)) { mc.touch(x, l); continue; }
        if (rc.has(r, l)) {
            q_rack += sz;
            rc.touch(r, l);
        } else {
            q_reg += sz;
            rc.insert(r, l, sz);
        }
        mc.insert(x, l, sz);
    }
}

// ---------------------------------------------------------------- SLACK

static void ensure_slack(int wi) {
    Wf& wf = wfs[wi];
    if (wf.slack_ver == wf.done_cnt) return;
    int n = wf.job_end - wf.job_begin;
    wf.es.assign(n, 0);
    wf.tl.assign(n, 0);
    // 正向
    for (int i = 0; i < n; ++i) {
        Job& j = jobs[wf.job_begin + i];
        if (j.state == 2) continue;
        int best = 0;
        for (int p : j.preds) {
            Job& pj = jobs[p];
            if (pj.state == 2) continue;
            int v = wf.es[p - wf.job_begin] + pj.e;
            if (v > best) best = v;
        }
        wf.es[i] = best;
    }
    // 反向
    ll cp = 0;
    for (int i = n - 1; i >= 0; --i) {
        Job& j = jobs[wf.job_begin + i];
        if (j.state == 2) continue;
        int best = 0;
        for (int s : j.succs) {
            Job& sj = jobs[s];
            if (sj.state == 2) continue;
            int v = wf.tl[s - wf.job_begin];
            if (v > best) best = v;
        }
        wf.tl[i] = j.e + best;
        ll len = (ll)wf.es[i] + wf.tl[i];
        if (len > cp) cp = len;
    }
    wf.cp = cp;
    wf.slack_ver = wf.done_cnt;
}

static ll slack_of(int ji) {
    Job& j = jobs[ji];
    if (j.state == 2) return 0;
    int wi = j.wf;
    ensure_slack(wi);
    Wf& wf = wfs[wi];
    int i = ji - wf.job_begin;
    return wf.cp - wf.es[i] - wf.tl[i];
}

// TL（含自身）用于估算最早完成
static int tl_of(int ji) {
    Job& j = jobs[ji];
    if (j.state == 2) return 0;
    int wi = j.wf;
    ensure_slack(wi);
    return wfs[wi].tl[ji - wfs[wi].job_begin];
}

// ---------------------------------------------------------------- 事件

static int cur_tick = 0;

static void on_done(int jid) {
    auto it = job_id.find(jid);
    if (it == job_id.end()) return;
    int ji = it->second;
    Job& j = jobs[ji];
    if (j.state != 1) return;
    int x = j.mach;
    settle_job(ji, cur_tick);
    j.state = 2;
    j.done_rack = mach_rack[x];
    Wf& wf = wfs[j.wf];
    wf.done_cnt++;
    for (int s : j.succs) {
        Job& sj = jobs[s];
        if (sj.rem > 0) {
            sj.rem--;
            if (sj.rem == 0 && sj.state == 0 && !wf.abandoned) ready_list.push_back(s);
        }
    }
    if (wf.done_cnt == wf.total) wf.finish = cur_tick;
}

static void on_fail(int x) {
    healthy[x] = 0;
    std::vector<int>& lst = mach_running[x];
    for (int ji : lst) {
        Job& j = jobs[ji];
        if (j.state == 1 && j.mach == x) {
            settle_job(ji, cur_tick);
            j.state = 0;
            if (j.rem == 0 && !wfs[j.wf].abandoned) ready_list.push_back(ji);
        }
    }
    lst.clear();
    mc.clear(x);
}

static void on_log(int x, int b, const std::string& hex) {
    int node = huff_root;
    int st = 0;
    ll score = 0;
    for (int i = 0; i < b; ++i) {
        int nib = hex[i >> 2];
        int v = (nib <= '9') ? (nib - '0') : (nib - 'a' + 10);
        int bit = (v >> (3 - (i & 3))) & 1;
        node = bit ? huff_right[node] : huff_left[node];
        if (node < 9) {
            st = ac.go[(size_t)st * 9 + node];
            score += ac.out[st];
            node = huff_root;
        }
    }
    if (score) {
        alarm_at[(size_t)cur_tick * M_ + x] += score;
        alarm_win[x] += score;
    }
}

static void on_wf(int wid, int tenant, ll value, int dl, int n) {
    int wi = (int)wfs.size();
    wfs.emplace_back();
    Wf& wf = wfs.back();
    wf.tenant = tenant;
    wf.value = value;
    wf.dl = dl;
    wf.arrive = cur_tick;
    wf.total = n;
    wf.done_cnt = 0;
    wf.abandoned = false;
    wf.finish = -1;
    wf.job_begin = (int)jobs.size();
    wf.job_end = wf.job_begin + n;
    wf.slack_ver = -1;
    wf_id[wid] = wi;

    int base = (int)jobs.size();
    jobs.resize(jobs.size() + n);
    for (int i = 0; i < n; ++i) {
        int jid = (int)io::read_int();
        Job& j = jobs[base + i];
        j.ext_id = jid;
        j.preds.clear();
        j.succs.clear();
        j.wf = wi;
        j.c = (int)io::read_int();
        j.m = io::read_int();
        j.e = (int)io::read_int();
        j.img = (int)io::read_int();
        j.src_rack = (int)io::read_int();
        j.z_in = io::read_int();
        j.z_out = io::read_int();
        int k = (int)io::read_int();
        j.state = 0; j.mach = -1; j.start = 0; j.done_rack = -1;
        j.rem = k;
        j.preds.resize(k);
        for (int q = 0; q < k; ++q) {
            int pid = (int)io::read_int();
            int pi = job_id[pid];
            j.preds[q] = pi;
            jobs[pi].succs.push_back(base + i);
        }
        job_id[jid] = base + i;
        if (k == 0) ready_list.push_back(base + i);
    }
}

// ---------------------------------------------------------------- 对账

static ll ans_bill(int o) {
    return settled[o] + rate_[o] * (ll)cur_tick + inter_[o];
}

static ll ans_head(int o) {
    ll best = LLONG_MAX;
    for (int a = o; a != -1; a = parent_[a]) {
        ll v = quota[a] - tused[a];
        if (v < best) best = v;
    }
    return best;
}

static ll ans_alarm(int x) { return alarm_win[x]; }

// ---------------------------------------------------------------- RUN 合法性

struct RunPrep {
    int t_tr = 0;
    ll cost_tr = 0;
    bool ok = false;
    int reason = 0;
};

// 检查并计算转移代价（不修改缓存/资源）
static bool prep_transfer(int ji, int x, RunPrep& rp) {
    Job& j = jobs[ji];
    int r = mach_rack[x];
    ll ttr = 0, cost = 0;
    if (j.src_rack >= 0 && j.src_rack != r) {
        ll d = rack_dist(r, j.src_rack);
        if (d < 0) return false;
        ll tt = d + (j.z_in + B_net - 1) / B_net;
        if (tt > ttr) ttr = tt;
        cost += (ll)j.z_in * d * U_net;
    }
    for (int p : j.preds) {
        Job& pj = jobs[p];
        if (pj.done_rack == r) continue;
        ll d = rack_dist(r, pj.done_rack);
        if (d < 0) return false;
        ll tt = d + (pj.z_out + B_net - 1) / B_net;
        if (tt > ttr) ttr = tt;
        cost += (ll)pj.z_out * d * U_net;
    }
    rp.t_tr = (int)ttr;
    rp.cost_tr = cost;
    rp.ok = true;
    return true;
}

// 拉取时间的快速估计（不改状态）
static int est_pull(int x, int r, int img, ll& est_cost) {
    ll qreg = 0, qrack = 0;
    for (int l : image_layers[img]) {
        ll sz = layer_size[l];
        if (mc.has(x, l)) continue;
        if (rc.has(r, l)) qrack += sz;
        else qreg += sz;
    }
    est_cost = qreg * U_reg;
    return (int)((qreg + B_reg - 1) / B_reg + (qrack + B_rack - 1) / B_rack);
}

static bool quota_ok(int ji, ll& cap_free) {
    Job& j = jobs[ji];
    int tenant = wfs[j.wf].tenant;
    ll best = LLONG_MAX;
    for (int a = tenant; a != -1; a = parent_[a]) {
        ll v = quota[a] - tused[a];
        if (v < best) best = v;
    }
    cap_free = best;
    return j.c <= best;
}

// 实际执行 RUN（调用前须已通过全部检查）
static void do_run(int ji, int x) {
    Job& j = jobs[ji];
    int r = mach_rack[x];
    RunPrep rp;
    prep_transfer(ji, x, rp);
    ll qreg = 0, qrack = 0;
    pull_image(x, r, j.img, qreg, qrack);
    ll pull_time = (qreg + B_reg - 1) / B_reg + (qrack + B_rack - 1) / B_rack;
    ll fee = rp.cost_tr + qreg * U_reg;
    int tenant = wfs[j.wf].tenant;
    add_fee(tenant, fee);
    ll p = price[rack_dc[r]];
    used_cpu[x] += j.c;
    used_mem[x] += j.m;
    for (int a = tenant; a != -1; a = parent_[a]) {
        tused[a] += j.c;
        rate_[a] += (ll)j.c * p;
        inter_[a] -= (ll)j.c * p * (ll)cur_tick;
    }
    j.state = 1;
    j.mach = x;
    j.start = cur_tick;
    mach_running[x].push_back(ji);
    (void)pull_time;
    (void)rp;
}

// ---------------------------------------------------------------- 调度

static const int TRY_PER_TICK = 400;

// 为一个就绪作业选机器；返回 -1 表示本 tick 放不下
static int choose_machine(int ji) {
    Job& j = jobs[ji];
    ll cap_free;
    if (!quota_ok(ji, cap_free)) return -1;

    int best_x = -1;
    ll best_key1 = LLONG_MAX, best_key2 = LLONG_MAX;

    for (int x = 0; x < M_; ++x) {
        if (!healthy[x]) continue;
        if (used_cpu[x] + j.c > mach_cpu[x]) continue;
        if (used_mem[x] + j.m > mach_mem[x]) continue;
        int r = mach_rack[x];
        ll p = price[rack_dc[r]];

        RunPrep rp;
        if (!prep_transfer(ji, x, rp)) continue;
        ll est_cost = 0;
        int tp = est_pull(x, r, j.img, est_cost);
        int prep = std::max(rp.t_tr, tp);
        ll finish = (ll)cur_tick + prep + j.e;
        ll cost = rp.cost_tr + est_cost + p * (ll)j.c * (ll)j.e;
        if (finish < best_key1 || (finish == best_key1 && cost < best_key2)) {
            best_key1 = finish;
            best_key2 = cost;
            best_x = x;
        }
    }
    return best_x;
}

static void schedule_tick() {
    if (ready_list.empty()) return;
    int attempted = 0;
    int w = 0;
    size_t i = 0, n = ready_list.size();
    for (; i < n; ++i) {
        if (attempted >= TRY_PER_TICK) break;
        int ji = ready_list[i];
        Job& j = jobs[ji];
        Wf& wf = wfs[j.wf];
        if (j.state != 0 || j.rem != 0 || wf.abandoned || wf.finish != -1) continue;
        int tl = tl_of(ji);
        ll G = std::max<ll>(5, (wf.dl - wf.arrive) / 3);
        if ((ll)cur_tick + tl >= (ll)wf.dl + G) continue;      // 收益必为 0，不必跑
        ++attempted;
        int x = choose_machine(ji);
        if (x >= 0) {
            do_run(ji, x);
            out_buf += "RUN ";
            out_buf += std::to_string(j.ext_id);
            out_buf += ' ';
            out_buf += std::to_string(x);
            out_buf += '\n';
        } else {
            ready_list[w++] = ji;
        }
    }
    for (; i < n; ++i) ready_list[w++] = ready_list[i];
    ready_list.resize(w);
}

// ---------------------------------------------------------------- 主循环

int main() {
    read_init();
    init_dynamic();

    char word[16];
    std::string hexbuf;
    hexbuf.reserve(1 << 16);

    build_huffman(freq9);

    // 读模式串建自动机
    ac.init();
    {
        std::string pat;
        for (int i = 0; i < P_; ++i) {
            io::read_word(pat);
            ll wgt = io::read_int();
            ac.add(pat, wgt);
        }
        ac.build();
    }

    for (int t = 1; t <= T_; ++t) {
        io::read_word(word, sizeof(word));       // TICK
        (void)io::read_int();
        int ne = (int)io::read_int();
        int nq = (int)io::read_int();
        cur_tick = t;
        // 滑出窗口：t-W 及更早的分数不再计入
        {
            int old = t - W_;
            if (old >= 1) {
                const ll* row = &alarm_at[(size_t)old * M_];
                for (int x = 0; x < M_; ++x) {
                    if (row[x]) alarm_win[x] -= row[x];
                }
            }
        }

        for (int i = 0; i < ne; ++i) {
            io::read_word(word, sizeof(word));
            if (strcmp(word, "DONE") == 0) {
                on_done((int)io::read_int());
            } else if (strcmp(word, "FAIL") == 0) {
                on_fail((int)io::read_int());
            } else if (strcmp(word, "UP") == 0) {
                healthy[(int)io::read_int()] = 1;
            } else if (strcmp(word, "DCDOWN") == 0) {
                dc_down[(int)io::read_int()] = 1;
                ++topo_ver;
            } else if (strcmp(word, "DCUP") == 0) {
                dc_down[(int)io::read_int()] = 0;
                ++topo_ver;
            } else if (strcmp(word, "LDOWN") == 0) {
                link_up[(int)io::read_int()] = 0;
                ++topo_ver;
            } else if (strcmp(word, "LUP") == 0) {
                link_up[(int)io::read_int()] = 1;
                ++topo_ver;
            } else if (strcmp(word, "QUOTA") == 0) {
                int k = (int)io::read_int();
                ll q = io::read_int();
                undo_stack.push_back({k, quota[k]});
                quota[k] = q;
            } else if (strcmp(word, "UNDO") == 0) {
                int k = (int)io::read_int();
                while (k-- > 0 && !undo_stack.empty()) {
                    quota[undo_stack.back().first] = undo_stack.back().second;
                    undo_stack.pop_back();
                }
            } else if (strcmp(word, "LOG") == 0) {
                int x = (int)io::read_int();
                int b = (int)io::read_int();
                io::read_word(hexbuf);
                if (b > 0) on_log(x, b, hexbuf);
            } else if (strcmp(word, "WF") == 0) {
                int wid = (int)io::read_int();
                int tenant = (int)io::read_int();
                ll value = io::read_int();
                int dl = (int)io::read_int();
                int n = (int)io::read_int();
                on_wf(wid, tenant, value, dl, n);
            }
        }

        // 对账
        out_buf += "ANS";
        for (int i = 0; i < nq; ++i) {
            io::read_word(word, sizeof(word));
            ll v = 0;
            if (strcmp(word, "BILL") == 0) v = ans_bill((int)io::read_int());
            else if (strcmp(word, "HEAD") == 0) v = ans_head((int)io::read_int());
            else if (strcmp(word, "ROUTE") == 0) {
                int a = (int)io::read_int(), b = (int)io::read_int();
                v = rack_dist(a, b);
            } else if (strcmp(word, "ALARM") == 0) v = ans_alarm((int)io::read_int());
            else if (strcmp(word, "SLACK") == 0) {
                int eid = (int)io::read_int();
                auto it = job_id.find(eid);
                v = (it == job_id.end()) ? 0 : slack_of(it->second);
            }
            else if (strcmp(word, "CACHE") == 0) v = mc.used_of((int)io::read_int());
            else if (strcmp(word, "RCACHE") == 0) v = rc.used_of((int)io::read_int());
            out_buf += ' ';
            out_buf += std::to_string(v);
        }
        out_buf += '\n';

        // 调度
        schedule_tick();

        out_buf += "END\n";
        fwrite(out_buf.data(), 1, out_buf.size(), stdout);
        fflush(stdout);
        out_buf.clear();
    }
    return 0;
}
