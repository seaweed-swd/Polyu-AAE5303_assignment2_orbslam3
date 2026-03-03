# 交互式超参优化使用指南

## 概述

这是一个**半自动化的超参优化系统**，允许你手动控制每个实验的运行，同时利用 Optuna 的贝叶斯优化算法来建议下一组参数。

## 优点

✅ **避免超时问题** - 你可以让实验运行任意长时间  
✅ **实时监控** - 可以随时查看日志和进度  
✅ **灵活控制** - 可以随时暂停、继续或跳过实验  
✅ **资源管理** - 可以选择何时运行，避免资源冲突  
✅ **智能建议** - 仍然使用 Optuna 的 TPE 算法优化参数  

## 工作流程

```
1. suggest  → 获取建议参数
2. run      → 运行 ORB-SLAM3 (手动或自动)
3. evaluate → 评估结果
4. submit   → 提交到 Optuna
5. 重复步骤 1-4
```

## 命令详解

### 1. 获取建议参数

```bash
python3 /root/AAE5305/Run3/interactive_optimize.py suggest
```

**输出:**
- 建议的参数组合
- 生成的配置文件路径
- 运行命令（可以直接复制执行）

**示例输出:**
```
================================================================================
Trial 0 - 建议参数
================================================================================

参数:
  nFeatures: 3500
  scaleFactor: 1.2
  nLevels: 10
  iniThFAST: 14
  minThFAST: 11
  imageScale: 0.6

配置文件: /root/AAE5305/Run3/manual_trials/trial_0000_config.yaml
输出目录: /root/AAE5305/Run3/manual_trials/trial_0000_output

================================================================================
运行命令
================================================================================

1. 运行 ORB-SLAM3:

cd /root/AAE5305/Run3/manual_trials/trial_0000_output
xvfb-run -a -s '-screen 0 1024x768x24' \
  /root/AAE5305/ORB_SLAM3/Examples/Monocular/mono_tum \
  /root/AAE5305/ORB_SLAM3/Vocabulary/ORBvoc.txt \
  /root/AAE5305/Run3/manual_trials/trial_0000_config.yaml \
  /root/AAE5305/Datasets/HKisland_GNSS03/images \
  2>&1 | tee /root/AAE5305/Run3/manual_trials/trial_0000_output/orbslam3.log
```

### 2. 运行 ORB-SLAM3

#### 方式 A: 手动运行（推荐）

复制 `suggest` 输出的命令，在新终端中运行：

```bash
# 复制并执行 suggest 输出的命令
cd /root/AAE5305/Run3/manual_trials/trial_XXXX_output
xvfb-run -a -s '-screen 0 1024x768x24' \
  /root/AAE5305/ORB_SLAM3/Examples/Monocular/mono_tum \
  ...
```

**优点:**
- 可以实时看到输出
- 可以随时 Ctrl+C 中断
- 可以在另一个终端监控

#### 方式 B: 自动运行

```bash
python3 /root/AAE5305/Run3/interactive_optimize.py run <trial_id>
```

**优点:**
- 一条命令完成
- 自动记录日志

**监控运行:**
```bash
# 实时查看日志
tail -f /root/AAE5305/Run3/manual_trials/trial_XXXX_output/orbslam3.log

# 检查进程
ps aux | grep mono_tum

# 检查轨迹文件
ls -lh /root/AAE5305/Run3/manual_trials/trial_XXXX_output/KeyFrameTrajectory.txt
```

### 3. 评估结果

运行完成后，评估轨迹：

```bash
python3 /root/AAE5305/Run3/interactive_optimize.py evaluate <trial_id>
```

**输出:**
```
================================================================================
评估 Trial 0
================================================================================

✓ 轨迹文件: /root/AAE5305/Run3/manual_trials/trial_0000_output/KeyFrameTrajectory.txt
  大小: 84754 bytes
  位姿数: 860

正在评估...

✅ 评估成功

指标:
  ATE RMSE: 7.970 m
  RPE Trans Drift: 1.611 m/m
  RPE Rot Drift: 125.796 deg/100m
  Completeness: 4.40 %
  Matched Poses: 860

目标值: 9.989
```

### 4. 提交结果

将结果提交到 Optuna：

```bash
python3 /root/AAE5305/Run3/interactive_optimize.py submit <trial_id>
```

**输出:**
```
================================================================================
提交 Trial 0 到 Optuna
================================================================================

✅ 结果已提交
  Trial ID: 0
  目标值: 9.989

当前最佳:
  Trial ID: 0
  目标值: 9.989

下一步: 获取新的建议参数
  python3 /root/AAE5305/Run3/interactive_optimize.py suggest
```

### 5. 查看状态

查看所有试验的状态：

```bash
python3 /root/AAE5305/Run3/interactive_optimize.py status
```

**输出:**
```
================================================================================
试验状态
================================================================================

Optuna Study: 3 个试验
最佳目标值: 5.526 (Trial 1)

手动试验:
ID     状态          目标值      创建时间            
------------------------------------------------------------
0      completed    9.989      2026-02-08 21:00:00
1      completed    5.526      2026-02-08 21:30:00
2      evaluated    8.234      2026-02-08 22:00:00
3      suggested    N/A        2026-02-08 22:30:00
```

## 完整示例

```bash
# 第一轮
python3 interactive_optimize.py suggest
# 复制运行命令，手动执行
python3 interactive_optimize.py evaluate 0
python3 interactive_optimize.py submit 0

# 第二轮
python3 interactive_optimize.py suggest
# 复制运行命令，手动执行
python3 interactive_optimize.py evaluate 1
python3 interactive_optimize.py submit 1

# 第三轮
python3 interactive_optimize.py suggest
# 复制运行命令，手动执行
python3 interactive_optimize.py evaluate 2
python3 interactive_optimize.py submit 2

# 查看进度
python3 interactive_optimize.py status
```

## 快捷工作流（自动运行）

如果你信任自动运行，可以使用：

```bash
# 获取建议
python3 interactive_optimize.py suggest

# 自动运行（会等待完成）
python3 interactive_optimize.py run 0

# 评估并提交
python3 interactive_optimize.py evaluate 0
python3 interactive_optimize.py submit 0
```

## 高级用法

### 并行运行多个实验

```bash
# 终端 1
python3 interactive_optimize.py suggest  # 得到 Trial 0
# 手动运行 Trial 0

# 终端 2
python3 interactive_optimize.py suggest  # 得到 Trial 1
# 手动运行 Trial 1

# 终端 3
python3 interactive_optimize.py suggest  # 得到 Trial 2
# 手动运行 Trial 2

# 等待全部完成后，依次评估和提交
python3 interactive_optimize.py evaluate 0 && python3 interactive_optimize.py submit 0
python3 interactive_optimize.py evaluate 1 && python3 interactive_optimize.py submit 1
python3 interactive_optimize.py evaluate 2 && python3 interactive_optimize.py submit 2
```

### 处理失败的实验

如果实验失败（没有生成轨迹文件），可以：

1. **跳过该试验** - 直接获取下一组参数
2. **手动提交失败结果** - 修改 `trial_XXXX_info.json`，设置 `objective: inf`

### 恢复中断的优化

所有数据都保存在：
- Optuna 数据库: `/root/AAE5305/Run3/optuna_manual.db`
- 试验信息: `/root/AAE5305/Run3/manual_trials/trial_XXXX_info.json`

可以随时中断和恢复，只需继续运行 `suggest` 命令。

## 参数范围

当前参数范围（可在脚本中修改）：

```python
'nFeatures': 1500-8000 (步长 500)
'scaleFactor': 1.1-1.3 (步长 0.05)
'nLevels': 6-12 (步长 2)
'iniThFAST': 10-25 (步长 2)
'minThFAST': 5-12 (步长 2)
'imageScale': 0.5-0.8 (步长 0.1)  # 已调整，避免太小
```

## 目标函数

```python
objective = 1.0 * ate_rmse_m 
          + 0.5 * rpe_trans_drift_m_per_m 
          + 0.01 * rpe_rot_drift_deg_per_100m 
          - 0.01 * completeness_pct
```

越小越好。

## 文件结构

```
Run3/
├── interactive_optimize.py          # 主脚本
├── optuna_manual.db                 # Optuna 数据库
└── manual_trials/                   # 手动试验目录
    ├── trial_0000_config.yaml       # 配置文件
    ├── trial_0000_info.json         # 试验信息
    └── trial_0000_output/           # 输出目录
        ├── KeyFrameTrajectory.txt   # 轨迹文件
        ├── orbslam3.log             # 运行日志
        ├── evaluation.json          # 评估结果
        └── evo_results/             # evo 详细结果
```

## 常见问题

### Q: 如何知道实验是否完成？

A: 检查轨迹文件是否生成：
```bash
ls -lh manual_trials/trial_XXXX_output/KeyFrameTrajectory.txt
```

### Q: 实验运行太慢怎么办？

A: 可以：
1. 减小 `imageScale`（但不要低于 0.5）
2. 减少 `nFeatures`
3. 使用更少的图像进行测试

### Q: 如何查看 Optuna 的优化历史？

A: 使用 Optuna Dashboard：
```bash
optuna-dashboard sqlite:////root/AAE5305/Run3/optuna_manual.db
```

### Q: 可以修改参数范围吗？

A: 可以，编辑 `interactive_optimize.py` 中的 `cmd_suggest` 函数。

## 总结

这个交互式系统让你可以：
- ✅ 完全控制每个实验的运行
- ✅ 避免超时和资源冲突
- ✅ 仍然享受贝叶斯优化的智能建议
- ✅ 随时查看进度和结果
- ✅ 灵活地并行或串行运行

**推荐工作流程：**
1. 先用 `suggest` 获取 3-5 组参数
2. 手动运行这些实验（可以并行）
3. 等待全部完成后，批量评估和提交
4. 查看结果，继续下一轮






