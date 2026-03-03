# Run4 - 手动超参数优化

这个文件夹包含手动超参数优化的工具和脚本。与 Run3 的自动化优化不同，Run4 允许您手动运行实验，然后使用 Optuna 学习参数空间并生成推荐配置。

## 📁 目录结构

```
Run4/
├── Config/                              # 配置文件目录
│   └── HKisland_GNSS03_template.yaml   # YAML 模板
├── Output/                              # 输出目录
│   └── groundtruth_tum.txt             # 真值文件
├── trials/                              # 试验目录
│   └── suggestions_YYYYMMDD_HHMMSS/    # 推荐配置目录
├── extract_groundtruth_tum.py          # 真值提取脚本
├── manual_hyperparameter_optimization.py  # 主优化脚本
└── README.md                            # 本文档
```

## 🚀 快速开始

### 1. 准备真值文件

如果真值文件不存在，运行提取脚本：

```bash
cd /root/AAE5305/Run4
python3 extract_groundtruth_tum.py
```

### 2. 手动运行实验

使用您自己的参数创建 YAML 配置文件，或使用模板：

```bash
cp Config/HKisland_GNSS03_template.yaml trials/my_experiment_001.yaml
# 编辑 my_experiment_001.yaml 修改参数
```

运行 ORB-SLAM3：

```bash
cd /root/AAE5305/ORB_SLAM3
xvfb-run -a -s "-screen 0 1024x768x24" \
    ./Examples/Monocular/mono_tum \
    Vocabulary/ORBvoc.txt \
    /root/AAE5305/Run4/trials/my_experiment_001.yaml \
    /root/AAE5305/Datasets/HKisland_GNSS03/images
```

### 3. 评估结果

使用评估脚本计算指标：

```bash
python3 /root/AAE5305/AAE5303_assignment2_orbslam3_demo-/scripts/evaluate_vo_accuracy.py \
    --groundtruth /root/AAE5305/Run4/Output/groundtruth_tum.txt \
    --estimated KeyFrameTrajectory.txt \
    --json-out /root/AAE5305/Run4/trials/my_experiment_001_evaluation.json \
    --workdir /root/AAE5305/Run4/trials/my_experiment_001_evo
```

### 4. 添加实验数据到优化器

```bash
cd /root/AAE5305/Run4
python3 manual_hyperparameter_optimization.py add \
    --yaml trials/my_experiment_001.yaml \
    --json trials/my_experiment_001_evaluation.json
```

### 5. 生成推荐配置

添加多个实验数据后，生成新的推荐配置：

```bash
python3 manual_hyperparameter_optimization.py suggest --n-suggestions 3
```

这将在 `trials/suggestions_YYYYMMDD_HHMMSS/` 目录下生成 3 个推荐的 YAML 配置文件。

### 6. 循环优化

重复步骤 2-5，持续优化参数。

## 📋 命令详解

### `add` - 添加实验数据

将手动运行的实验结果添加到 Optuna study：

```bash
python3 manual_hyperparameter_optimization.py add \
    --yaml <yaml配置文件> \
    --json <评估json文件>
```

**参数：**
- `--yaml`: YAML 配置文件路径
- `--json`: 评估 JSON 文件路径（由 evaluate_vo_accuracy.py 生成）

**示例：**
```bash
python3 manual_hyperparameter_optimization.py add \
    --yaml trials/trial_001.yaml \
    --json trials/trial_001_evaluation.json
```

### `suggest` - 生成推荐配置

基于已有数据，使用 Optuna 生成新的推荐参数配置：

```bash
python3 manual_hyperparameter_optimization.py suggest --n-suggestions <数量>
```

**参数：**
- `--n-suggestions`: 生成的推荐配置数量（默认：3）

**输出：**
- 在 `trials/suggestions_YYYYMMDD_HHMMSS/` 目录下生成推荐的 YAML 文件
- 生成 `suggestions_summary.json` 摘要文件

**示例：**
```bash
python3 manual_hyperparameter_optimization.py suggest --n-suggestions 5
```

### `status` - 查看优化状态

显示当前优化进度和统计信息：

```bash
python3 manual_hyperparameter_optimization.py status
```

**输出：**
- Study 信息（总试验数、完成数）
- 最佳试验的参数和指标
- 最近 5 次试验的结果

### `best` - 查看最佳参数

显示当前最佳参数并生成配置文件：

```bash
python3 manual_hyperparameter_optimization.py best
```

**输出：**
- 最佳试验的详细参数
- 最佳试验的评估指标
- 生成 `Config/HKisland_GNSS03_best.yaml` 配置文件

### `export` - 导出优化历史

导出所有试验的历史记录到 JSON 文件：

```bash
python3 manual_hyperparameter_optimization.py export
```

**输出：**
- `optimization_history.json` 文件，包含所有试验的详细信息

## 🔧 优化参数

脚本会从 YAML 文件中解析以下参数：

| 参数 | 范围 | 说明 |
|------|------|------|
| `nFeatures` | 1500-8000 | ORB 特征点数量 |
| `scaleFactor` | 1.1-1.3 | 金字塔尺度因子 |
| `nLevels` | 6-12 | 金字塔层数 |
| `iniThFAST` | 10-25 | FAST 初始阈值 |
| `minThFAST` | 5-12 | FAST 最小阈值 |
| `imageScale` | 0.3-0.7 | 图像缩放比例 |

## 📊 评估指标

脚本会从 JSON 文件中解析以下指标：

| 指标 | 说明 | 优化目标 |
|------|------|----------|
| `ate_rmse_m` | 绝对轨迹误差 RMSE (米) | 越小越好 |
| `rpe_trans_drift_m_per_m` | 相对位置漂移 (米/米) | 越小越好 |
| `rpe_rot_drift_deg_per_100m` | 相对旋转漂移 (度/100米) | 越小越好 |
| `completeness_pct` | 完整度 (%) | 越大越好 |

### 目标函数

目标函数综合考虑上述 4 个指标，计算公式：

```python
objective = (
    1.0 * ate_rmse_m +
    0.5 * rpe_trans_drift_m_per_m +
    0.01 * rpe_rot_drift_deg_per_100m +
    (-0.01) * completeness_pct
)
```

目标值越小越好。

## 💡 工作流程示例

### 完整的优化循环

```bash
# 第一轮：手动运行 3 个初始实验
# 实验 1
vim trials/init_001.yaml  # 编辑参数
# 运行 ORB-SLAM3...
# 评估结果...
python3 manual_hyperparameter_optimization.py add \
    --yaml trials/init_001.yaml \
    --json trials/init_001_evaluation.json

# 实验 2
vim trials/init_002.yaml
# 运行 ORB-SLAM3...
# 评估结果...
python3 manual_hyperparameter_optimization.py add \
    --yaml trials/init_002.yaml \
    --json trials/init_002_evaluation.json

# 实验 3
vim trials/init_003.yaml
# 运行 ORB-SLAM3...
# 评估结果...
python3 manual_hyperparameter_optimization.py add \
    --yaml trials/init_003.yaml \
    --json trials/init_003_evaluation.json

# 查看当前状态
python3 manual_hyperparameter_optimization.py status

# 第二轮：生成推荐配置
python3 manual_hyperparameter_optimization.py suggest --n-suggestions 3

# 运行推荐的配置
# trials/suggestions_20260208_120000/suggestion_01.yaml
# trials/suggestions_20260208_120000/suggestion_02.yaml
# trials/suggestions_20260208_120000/suggestion_03.yaml

# 添加结果
python3 manual_hyperparameter_optimization.py add \
    --yaml trials/suggestions_20260208_120000/suggestion_01.yaml \
    --json trials/suggestion_01_evaluation.json

# ... 继续添加其他结果

# 第三轮：继续优化
python3 manual_hyperparameter_optimization.py suggest --n-suggestions 3

# ... 重复循环
```

## 📈 可视化和分析

### 查看优化进度

```bash
# 查看状态
python3 manual_hyperparameter_optimization.py status

# 查看最佳参数
python3 manual_hyperparameter_optimization.py best

# 导出历史
python3 manual_hyperparameter_optimization.py export
```

### 使用 Optuna Dashboard（可选）

如果安装了 optuna-dashboard：

```bash
pip install optuna-dashboard
optuna-dashboard sqlite:///manual_optuna_study.db
```

然后在浏览器中访问 http://localhost:8080

## 🔍 故障排除

### 问题：真值文件不存在

**解决方案：**
```bash
python3 extract_groundtruth_tum.py
```

### 问题：YAML 解析失败

**原因：** YAML 文件格式不正确

**解决方案：**
- 确保 YAML 文件以 `%YAML:1.0` 开头
- 检查参数名称是否正确（如 `ORBextractor.nFeatures`）
- 使用模板文件作为参考

### 问题：JSON 解析失败

**原因：** JSON 文件缺少必要的指标

**解决方案：**
- 确保使用 `evaluate_vo_accuracy.py` 生成 JSON 文件
- 检查 JSON 文件包含所有必要的指标

### 问题：Optuna 数据库损坏

**解决方案：**
```bash
# 备份数据库
cp manual_optuna_study.db manual_optuna_study.db.backup

# 删除并重新开始
rm manual_optuna_study.db
```

## 📝 注意事项

1. **参数约束：** 脚本会自动确保 `minThFAST <= iniThFAST`
2. **imageScale 范围：** 避免使用 0.2 以下的值，可能导致崩溃
3. **数据持久化：** 所有数据存储在 `manual_optuna_study.db` SQLite 数据库中
4. **并行运行：** 可以同时运行多个实验，然后批量添加结果
5. **备份：** 定期备份数据库文件和试验结果

## 🎯 优化建议

1. **初始探索：** 前 5-10 次实验使用较大的参数变化范围
2. **精细调优：** 后续实验关注最佳参数附近的区域
3. **多样性：** 不要只运行推荐的配置，也可以手动尝试一些极端参数
4. **记录：** 保持良好的实验记录，包括运行时间、观察到的问题等
5. **批量运行：** 一次生成多个推荐配置，批量运行后再添加结果

## 📚 相关文件

- **评估脚本：** `/root/AAE5305/AAE5303_assignment2_orbslam3_demo-/scripts/evaluate_vo_accuracy.py`
- **ORB-SLAM3：** `/root/AAE5305/ORB_SLAM3/`
- **数据集：** `/root/AAE5305/Datasets/HKisland_GNSS03/`

## 🤝 与 Run3 的区别

| 特性 | Run3 (自动) | Run4 (手动) |
|------|-------------|-------------|
| 运行方式 | 自动并行运行 | 手动运行实验 |
| 适用场景 | 快速探索参数空间 | 精细控制和调试 |
| 灵活性 | 较低 | 高 |
| 速度 | 快（并行） | 慢（手动） |
| 控制力 | 自动化 | 完全控制 |

## 📞 帮助

如有问题，请查看：
1. 本 README 文档
2. 脚本的帮助信息：`python3 manual_hyperparameter_optimization.py --help`
3. Optuna 文档：https://optuna.readthedocs.io/

