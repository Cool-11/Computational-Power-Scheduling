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

# 2) 生成世界并评测我方程序
python tools/gen_world.py --seed 1 --T 60 --out tests/worlds/w1.in
python tools/judge.py run --world tests/worlds/w1.in --solver build/solver.exe

# 3) 批量回归（0 对账错误 / 0 非法指令 / 总利润）
python tools/bench.py --tag 我的版本 --seeds 1-16 --T 60
```

## 当前状态

| 项目 | 结果 |
|---|---|
| 参考实现与官方样例 | 100/100 道对账一致（样例 1+2） |
| 20 组随机世界（含 big1/huge） | 对账 0 错、0 非法指令 |
| 满规模（T=600、4.8 万作业、3600 道对账） | 0.59 s、26 MB、利润 +141608 |
| 16 组小世界总利润 | +634080（412/2770 个工作流完成） |

## 调度策略（一句话版）

到达时就用「自适应放大的估计时长 + 每作业准备时间」估算完成时间，
只有**能赶在截止（且不超过 T）前完成、收益覆盖成本、租户配额放得下**的工作流才准入；
准入后在飞工作量不超过平台核数的 2 倍；就绪作业按松弛时间优先；
选机器时在「完成时间相差不超过 1 tick」的候选里挑传输/拉取/运行费最省的那台；
彻底赶不上的工作流直接 `KILL` 止损。细节见 `docs/规格表.md` 与 `docs/实验记录.md`。

## 验收顺序

1. 协议正确：持续读写、每轮刷新、第 T 轮后退出。
2. 对账正确：七类对账与参考实现/平台一致。
3. 指令合法：同 tick 内多条指令按顺序执行后仍合法。
4. 利润改进：前三项稳定后再优化策略。
