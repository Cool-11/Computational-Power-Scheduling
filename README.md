# 星环算力调度系统

交互式算力调度器：每个 tick 先处理平台事件，再回答对账题，最后输出合法调度指令。
评测程序（平台）与我方程序通过标准输入输出交互。提交物是**单文件** `src/main.cpp`（C++17，无第三方依赖）。

## 目录

```
src/main.cpp     提交给 OJ 的单文件调度器
tools/judge.py   慢速参考实现 + 本地评测器（replay 校验参考实现，run 驱动我方程序）
tools/gen_world.py  随机世界生成器（规模/事件密度可配）
tools/bench.py   批量跑世界，输出对账/合法性/利润表
tests/samples/   官方样例的完整交互记录（事件 + 对账 + 官方答案）
tests/worlds/    生成的世界
docs/            开发计划、规格表、环境与构建、实验记录、开发日志
```

## 快速开始

```bash
# 编译（Windows 本地用 MSYS2 mingw64 g++；OJ 上直接 g++ -std=c++17 -O2）
g++ -std=c++17 -O2 -o build/solver.exe src/main.cpp

# 1) 用官方样例校验参考实现本身（应输出 100/100 一致）
python tools/judge.py replay tests/samples/sample1.txt
python tools/judge.py replay tests/samples/sample2.txt

# 2) 用官方评测程序跑（最可信；需要 vendor/samples/tpj_win.exe）
python tools/tpj_run.py --params tests/params/oj.in --solver build/solver.exe

# 3) 生成世界并用自建参考评测器交叉验证
python tools/gen_world.py --seed 1 --T 60 --out tests/worlds/w1.in
python tools/judge.py run --world tests/worlds/w1.in --solver build/solver.exe

# 4) 批量回归（0 对账错误 / 0 非法指令 / 总利润）
python tools/bench.py --tag 我的版本 --seeds 1-16 --T 60
```

## 当前状态

| 项目 | 结果 |
|---|---|
| 官方评测程序 `tpj_win.exe`（题面参数，T=500、182 机器、30612 作业） | 对账 0/1767 错、0 非法，**利润 5057578**（上界 17427102） |
| 官方评测程序另三个 seed | 1288770 / 5524715 / 2162810，均 0 错 0 非法（四组合计 14033873） |
| 官方评测程序满规模（T=600、356 机、83026 作业、3567 道对账） | 0 错 0 非法，利润 6594409，求解器 **0.65 s / <40 MB** |
| 自建参考实现 vs 官方样例 | 100/100 道对账一致（样例 1+2） |
| 自建随机世界（含 big1/huge/edge） | 对账 0 错、0 非法指令 |

## 调度策略（一句话版）

到达时就估三件事：**能不能按时完成**（自适应时长系数 + 逐作业最好准备时间）、
**值不值得跑**（收益 ≥ 估算成本 × 150%，成本含运行费+传输费+拉取费）、
**租户配额放不放得下**（峰值并发 ≤ 祖先链余量）。
准入**不设并发上限**（官方数据实测：限额 2 → 利润 76 万，限额 100 → 475 万），
因为平台是能跑满的；靠"值不值得跑"这一道闸门做筛选。
准入后按**整条链的外部输入距离**给工作流钉一个"主场机架"（并在同等条件下优先空闲机器多的机架），
整条链尽量放同一机架——实测比"按镜像聚簇"更划算，因为这份数据里传输比拉取贵；
就绪作业按松弛时间优先；选机器时在「完成时间相差不超过 1 tick」的候选里挑总费用最低的；
彻底赶不上的工作流 `KILL` 止损。

> 两个旋钮：`MARGIN_PCT`（默认 150，官方数据上 150 最优、200 腰斩）与
> `ADMIT_HORIZON`（默认 100 ≈ 不设上限）。都在 `src/main.cpp` 顶部，
> 用 `-D` 覆盖即可做 A/B。

细节见 `docs/规格表.md`、`docs/实验记录.md`、`docs/开发日志.md`。

### 提交变体

策略只有一个旋钮，改编译宏即可（默认 300）：

```bash
# 默认（官方评测器上最优）
g++ -std=c++17 -O2 -o build/solver.exe src/main.cpp
# 更激进（如果正式数据比本地生成器更"便宜"）
g++ -std=c++17 -O2 -DMARGIN_PCT=120 -o build/solver_aggr.exe src/main.cpp
# 更保守（如果利润为负）
g++ -std=c++17 -O2 -DMARGIN_PCT=200 -o build/solver_safe.exe src/main.cpp
```

三个版本的对账与指令合法性完全相同（只影响"跑哪些工作流"），
可以安全地用掉几次提交机会做对比。

### 用官方评测程序批量对比

```bash
python tools/eval_oj.py --solver build/solver.exe          # 4 个 seed 并行，输出利润/完成数/上界
python tools/eval_oj.py --solver build/solver_aggr.exe --tag 激进版
```

## 验收顺序

1. 协议正确：持续读写、每轮刷新、第 T 轮后退出。
2. 对账正确：七类对账与参考实现/平台一致。
3. 指令合法：同 tick 内多条指令按顺序执行后仍合法。
4. 利润改进：前三项稳定后再优化策略。
