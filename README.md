# 星环算力调度系统

交互式算力调度器：每个 tick 先处理平台事件，再回答对账题，最后输出合法调度指令。
评测程序（平台）与我方程序通过标准输入输出交互。

## 目录

```
src/        C++17 调度程序（提交物为单文件）
tests/      样例原文、自建随机世界、单测场景
tools/      Python 慢速参考评测器（差分测试与对账基准）
docs/       开发计划、规格表、环境记录、实验记录
```

## 快速开始

```bash
# 编译（本地 MSYS2 mingw64 g++）
g++ -std=c++17 -O2 -o build/solver.exe src/main.cpp

# 用参考评测器跑一组世界（word 定义见 docs/环境与构建.md）
python tools/judge.py --world tests/worlds/demo.txt --solver build/solver.exe
```

## 验收顺序

1. 协议正确：持续读写、每轮刷新、第 T 轮后退出。
2. 对账正确：七类对账与参考实现/平台一致。
3. 指令合法：同 tick 内多条指令按顺序执行后仍合法。
4. 利润改进：前三项稳定后再优化策略。
