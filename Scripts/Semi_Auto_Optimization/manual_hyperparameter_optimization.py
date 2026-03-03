#!/usr/bin/env python3
"""
手动超参数优化脚本 - 基于 Optuna

用户手动运行实验并提供 YAML 配置文件和对应的评估 JSON 文件。
脚本解析这些文件，使用 Optuna 学习参数空间，并生成下一批推荐的参数配置。

工作流程：
1. 用户提供已完成实验的 YAML 和 JSON 文件路径
2. 脚本解析参数和评估指标
3. Optuna 学习参数-指标关系
4. 生成新的推荐参数配置 YAML 文件
5. 用户手动运行这些配置，重复循环

使用方法：
    # 第一次运行（添加初始实验数据）
    python3 manual_hyperparameter_optimization.py add \
        --yaml trial_001.yaml \
        --json trial_001_evaluation.json
    
    # 添加更多实验数据
    python3 manual_hyperparameter_optimization.py add \
        --yaml trial_002.yaml \
        --json trial_002_evaluation.json
    
    # 生成新的推荐配置
    python3 manual_hyperparameter_optimization.py suggest --n-suggestions 3
    
    # 查看优化历史
    python3 manual_hyperparameter_optimization.py status
    
    # 查看最佳参数
    python3 manual_hyperparameter_optimization.py best
"""

import os
import json
import yaml
import argparse
import optuna
from optuna.samplers import TPESampler
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime
import shutil

# ==================== 配置 ====================
BASE_DIR = Path(__file__).parent.absolute()
CONFIG_TEMPLATE = BASE_DIR / "Config/HKisland_GNSS03_template.yaml"
TRIALS_DIR = BASE_DIR / "trials"
OUTPUT_DIR = BASE_DIR / "Output"

# Optuna 数据库
STUDY_NAME = "manual_orbslam3_optimization"
STORAGE = f"sqlite:///{BASE_DIR}/manual_optuna_study.db"

# 需要优化的参数及其范围
PARAM_RANGES = {
    'nFeatures': (1500, 8000),
    'scaleFactor': (1.1, 1.3),
    'nLevels': (6, 18),
    'iniThFAST': (10, 25),
    'minThFAST': (5, 12),
    'imageScale': (0.3, 1),
}

# ==================== 工具函数 ====================

def load_yaml_template() -> Dict:
    """加载 YAML 模板"""
    with open(CONFIG_TEMPLATE, 'r') as f:
        return yaml.safe_load(f)


def parse_yaml_params(yaml_path: str) -> Dict:
    """从 YAML 文件解析优化参数"""
    with open(yaml_path, 'r') as f:
       # 跳过 %YAML:1.0 行
       content = f.read()
       if content.startswith('%YAML'):
           lines = content.split('\n', 1)
           if len(lines) > 1:
               content = lines[1]
       config = yaml.safe_load(content)
    
    params = {
        'nFeatures': int(config['ORBextractor.nFeatures']),
        'scaleFactor': float(config['ORBextractor.scaleFactor']),
        'nLevels': int(config['ORBextractor.nLevels']),
        'iniThFAST': int(config['ORBextractor.iniThFAST']),
        'minThFAST': int(config['ORBextractor.minThFAST']),
        'imageScale': float(config['Camera.imageScale']),
    }
    
    return params


def parse_json_metrics(json_path: str) -> Dict:
    """从 JSON 文件解析评估指标"""
    with open(json_path, 'r') as f:
        metrics = json.load(f)
    
    return metrics


def compute_objective(metrics: Dict) -> float:
    """
    计算目标函数值（越小越好）
    综合考虑 4 个指标：
    - ate_rmse_m: 越小越好
    - rpe_trans_drift_m_per_m: 越小越好
    - rpe_rot_drift_deg_per_100m: 越小越好
    - completeness_pct: 越大越好
    """
    # 归一化权重
    w_ate = 0 #1.0
    w_rpe_trans = 0 #0.5
    w_rpe_rot = 0 #0.01  # 旋转漂移权重较小（因为数值较大）
    w_completeness = -1.0 #-0.01  # 负权重（因为越大越好）
    
    # 计算加权目标
    objective = (
        w_ate * metrics.get('ate_rmse_m', 100.0) +
        w_rpe_trans * metrics.get('rpe_trans_drift_m_per_m', 10.0) +
        w_rpe_rot * metrics.get('rpe_rot_drift_deg_per_100m', 200.0) +
        w_completeness * metrics.get('completeness_pct', 0.0)
    )
    
    return objective


def create_config_from_params(params: Dict, output_path: Path) -> None:
    """根据参数创建配置文件"""
    config = load_yaml_template()
    
    # 更新 ORB 参数
    config['ORBextractor.nFeatures'] = int(params['nFeatures'])
    config['ORBextractor.scaleFactor'] = float(params['scaleFactor'])
    config['ORBextractor.nLevels'] = int(params['nLevels'])
    config['ORBextractor.iniThFAST'] = int(params['iniThFAST'])
    config['ORBextractor.minThFAST'] = int(params['minThFAST'])
    config['Camera.imageScale'] = float(params['imageScale'])
    
    # 保存配置文件
    with open(output_path, 'w') as f:
        f.write('%YAML:1.0\n')
        yaml.dump(config, f, default_flow_style=False)


def get_or_create_study() -> optuna.Study:
    """获取或创建 Optuna study"""
    sampler = TPESampler(seed=42)
    study = optuna.create_study(
        study_name=STUDY_NAME,
        storage=STORAGE,
        load_if_exists=True,
        direction='minimize',
        sampler=sampler
    )
    return study


# ==================== 命令函数 ====================

def cmd_add(args):
    """添加实验数据到 Optuna study"""
    print("="*80)
    print("添加实验数据")
    print("="*80)
    
    yaml_path = Path(args.yaml).absolute()
    json_path = Path(args.json).absolute()
    
    # 检查文件是否存在
    if not yaml_path.exists():
        print(f"❌ 错误: YAML 文件不存在: {yaml_path}")
        return 1
    
    if not json_path.exists():
        print(f"❌ 错误: JSON 文件不存在: {json_path}")
        return 1
    
    # 解析参数和指标
    print(f"\n📄 解析 YAML: {yaml_path.name}")
    params = parse_yaml_params(str(yaml_path))
    print(f"  参数:")
    for key, value in params.items():
        print(f"    {key}: {value}")
    
    print(f"\n📊 解析 JSON: {json_path.name}")
    metrics = parse_json_metrics(str(json_path))
    print(f"  指标:")
    print(f"    ATE RMSE: {metrics['ate_rmse_m']:.3f} m")
    print(f"    RPE Trans Drift: {metrics['rpe_trans_drift_m_per_m']:.3f} m/m")
    print(f"    RPE Rot Drift: {metrics['rpe_rot_drift_deg_per_100m']:.3f} deg/100m")
    print(f"    Completeness: {metrics['completeness_pct']:.2f} %")
    
    # 计算目标值
    objective = compute_objective(metrics)
    print(f"\n🎯 目标值: {objective:.3f}")
    
    # 添加到 Optuna study
    study = get_or_create_study()
    
    # 使用 enqueue_trial 添加固定参数的试验
    trial = study.ask()
    
    # 手动设置参数
    for key, value in params.items():
        trial.suggest_float(key, value, value) if isinstance(value, float) else trial.suggest_int(key, value, value)
    
    # 保存指标到 trial 的 user_attrs
    trial.set_user_attr('ate_rmse_m', metrics['ate_rmse_m'])
    trial.set_user_attr('rpe_trans_drift_m_per_m', metrics['rpe_trans_drift_m_per_m'])
    trial.set_user_attr('rpe_rot_drift_deg_per_100m', metrics['rpe_rot_drift_deg_per_100m'])
    trial.set_user_attr('completeness_pct', metrics['completeness_pct'])
    trial.set_user_attr('matched_poses', metrics['matched_poses'])
    trial.set_user_attr('yaml_file', str(yaml_path.name))
    trial.set_user_attr('json_file', str(json_path.name))
    
    # 报告结果
    study.tell(trial, objective)

    print(f"\n✅ 数据已添加到 study (Trial #{trial.number})")
    print(f"   总试验数: {len(study.trials)}")
    
    return 0


def cmd_suggest(args):
    """生成新的推荐参数配置"""
    print("="*80)
    print("生成推荐参数配置")
    print("="*80)
    
    study = get_or_create_study()
    
    if len(study.trials) == 0:
        print("❌ 错误: 还没有任何实验数据，请先使用 'add' 命令添加数据")
        return 1
    
    print(f"\n当前 study 状态:")
    print(f"  总试验数: {len(study.trials)}")
    print(f"  最佳目标值: {study.best_value:.3f}")
    
    n_suggestions = args.n_suggestions
    print(f"\n生成 {n_suggestions} 个推荐配置...")
    
    # 创建建议目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suggest_dir = TRIALS_DIR / f"suggestions_{timestamp}"
    suggest_dir.mkdir(parents=True, exist_ok=True)
    
    suggestions = []
    
    for i in range(n_suggestions):
        # 使用 Optuna 的 ask 方法获取建议
        trial = study.ask()
        
        # 定义参数范围
        params = {
            'nFeatures': trial.suggest_int('nFeatures', PARAM_RANGES['nFeatures'][0], PARAM_RANGES['nFeatures'][1], step=500),
            'scaleFactor': trial.suggest_float('scaleFactor', PARAM_RANGES['scaleFactor'][0], PARAM_RANGES['scaleFactor'][1], step=0.05),
            'nLevels': trial.suggest_int('nLevels', PARAM_RANGES['nLevels'][0], PARAM_RANGES['nLevels'][1], step=2),
            'iniThFAST': trial.suggest_int('iniThFAST', PARAM_RANGES['iniThFAST'][0], PARAM_RANGES['iniThFAST'][1], step=2),
            'minThFAST': trial.suggest_int('minThFAST', PARAM_RANGES['minThFAST'][0], PARAM_RANGES['minThFAST'][1], step=2),
            'imageScale': trial.suggest_float('imageScale', PARAM_RANGES['imageScale'][0], PARAM_RANGES['imageScale'][1], step=0.1),
        }
        
        # 确保 minThFAST <= iniThFAST
        if params['minThFAST'] > params['iniThFAST']:
            params['minThFAST'] = params['iniThFAST']
        
        # 生成配置文件
        config_path = suggest_dir / f"suggestion_{i+1:02d}.yaml"
        create_config_from_params(params, config_path)
        
        suggestions.append({
            'file': config_path.name,
            'params': params
        })
        
        print(f"\n📝 建议 {i+1}: {config_path.name}")
        for key, value in params.items():
            print(f"    {key}: {value}")
    
    # 保存建议摘要
    summary_path = suggest_dir / "suggestions_summary.json"
    with open(summary_path, 'w') as f:
        json.dump({
            'timestamp': timestamp,
            'n_suggestions': n_suggestions,
            'current_best_value': study.best_value,
            'current_best_params': study.best_params,
            'suggestions': suggestions
        }, f, indent=2)
    
    print(f"\n✅ 已生成 {n_suggestions} 个推荐配置")
    print(f"   保存位置: {suggest_dir}")
    print(f"   摘要文件: {summary_path.name}")
    print(f"\n📋 下一步:")
    print(f"   1. 手动运行这些配置文件")
    print(f"   2. 使用 evaluate_vo_accuracy.py 评估结果")
    print(f"   3. 使用 'add' 命令添加结果到 study")
    print(f"   4. 重复此过程以持续优化")
    
    return 0


def cmd_status(args):
    """显示优化状态"""
    print("="*80)
    print("优化状态")
    print("="*80)
    
    study = get_or_create_study()
    
    if len(study.trials) == 0:
        print("\n还没有任何实验数据")
        return 0
    
    print(f"\n📊 Study 信息:")
    print(f"   名称: {study.study_name}")
    print(f"   总试验数: {len(study.trials)}")
    print(f"   完成试验数: {len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])}")
    
    print(f"\n🏆 最佳试验:")
    best_trial = study.best_trial
    print(f"   Trial #{best_trial.number}")
    print(f"   目标值: {best_trial.value:.3f}")
    
    print(f"\n   参数:")
    for key, value in best_trial.params.items():
        print(f"     {key}: {value}")
    
    if 'ate_rmse_m' in best_trial.user_attrs:
        print(f"\n   指标:")
        print(f"     ATE RMSE: {best_trial.user_attrs['ate_rmse_m']:.3f} m")
        print(f"     RPE Trans Drift: {best_trial.user_attrs['rpe_trans_drift_m_per_m']:.3f} m/m")
        print(f"     RPE Rot Drift: {best_trial.user_attrs['rpe_rot_drift_deg_per_100m']:.3f} deg/100m")
        print(f"     Completeness: {best_trial.user_attrs['completeness_pct']:.2f} %")
    
    print(f"\n📈 最近 5 次试验:")
    for trial in study.trials[-5:]:
        status = "✓" if trial.state == optuna.trial.TrialState.COMPLETE else "✗"
        print(f"   {status} Trial #{trial.number}: 目标值 = {trial.value:.3f}")
    
    return 0


def cmd_best(args):
    """显示最佳参数并生成配置文件"""
    print("="*80)
    print("最佳参数")
    print("="*80)
    
    study = get_or_create_study()
    
    if len(study.trials) == 0:
        print("\n还没有任何实验数据")
        return 0
    
    best_trial = study.best_trial
    
    print(f"\n🏆 最佳 Trial: #{best_trial.number}")
    print(f"   目标值: {best_trial.value:.3f}")
    
    print(f"\n📋 参数:")
    for key, value in best_trial.params.items():
        print(f"   {key}: {value}")
    
    if 'ate_rmse_m' in best_trial.user_attrs:
        print(f"\n📊 指标:")
        print(f"   ATE RMSE: {best_trial.user_attrs['ate_rmse_m']:.3f} m")
        print(f"   RPE Trans Drift: {best_trial.user_attrs['rpe_trans_drift_m_per_m']:.3f} m/m")
        print(f"   RPE Rot Drift: {best_trial.user_attrs['rpe_rot_drift_deg_per_100m']:.3f} deg/100m")
        print(f"   Completeness: {best_trial.user_attrs['completeness_pct']:.2f} %")
        print(f"   Matched Poses: {best_trial.user_attrs['matched_poses']}")
    
    # 生成最佳配置文件
    best_config_path = BASE_DIR / "Config/HKisland_GNSS03_best.yaml"
    create_config_from_params(best_trial.params, best_config_path)
    
    print(f"\n✅ 最佳配置已保存: {best_config_path}")
    
    return 0


def cmd_export(args):
    """导出优化历史"""
    print("="*80)
    print("导出优化历史")
    print("="*80)
    
    study = get_or_create_study()
    
    if len(study.trials) == 0:
        print("\n还没有任何实验数据")
        return 0
    
    # 导出历史
    history = []
    for trial in study.trials:
        history.append({
            'number': trial.number,
            'params': trial.params,
            'value': trial.value,
            'user_attrs': trial.user_attrs,
            'state': trial.state.name,
            'datetime_start': trial.datetime_start.isoformat() if trial.datetime_start else None,
            'datetime_complete': trial.datetime_complete.isoformat() if trial.datetime_complete else None,
        })
    
    output_path = BASE_DIR / "optimization_history.json"
    with open(output_path, 'w') as f:
        json.dump({
            'study_name': study.study_name,
            'n_trials': len(study.trials),
            'best_value': study.best_value,
            'best_params': study.best_params,
            'trials': history
        }, f, indent=2)
    
    print(f"\n✅ 优化历史已导出: {output_path}")
    print(f"   总试验数: {len(history)}")
    
    return 0


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(
        description="手动超参数优化脚本 - 基于 Optuna",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 添加实验数据
  %(prog)s add --yaml trial_001.yaml --json trial_001_evaluation.json
  
  # 生成推荐配置
  %(prog)s suggest --n-suggestions 3
  
  # 查看状态
  %(prog)s status
  
  # 查看最佳参数
  %(prog)s best
  
  # 导出历史
  %(prog)s export
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # add 命令
    parser_add = subparsers.add_parser('add', help='添加实验数据')
    parser_add.add_argument('--yaml', required=True, help='YAML 配置文件路径')
    parser_add.add_argument('--json', required=True, help='评估 JSON 文件路径')
    
    # suggest 命令
    parser_suggest = subparsers.add_parser('suggest', help='生成推荐配置')
    parser_suggest.add_argument('--n-suggestions', type=int, default=3, help='生成的推荐数量')
    
    # status 命令
    parser_status = subparsers.add_parser('status', help='显示优化状态')
    
    # best 命令
    parser_best = subparsers.add_parser('best', help='显示最佳参数')
    
    # export 命令
    parser_export = subparsers.add_parser('export', help='导出优化历史')
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 1
    
    # 确保目录存在
    TRIALS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 执行命令
    if args.command == 'add':
        return cmd_add(args)
    elif args.command == 'suggest':
        return cmd_suggest(args)
    elif args.command == 'status':
        return cmd_status(args)
    elif args.command == 'best':
        return cmd_best(args)
    elif args.command == 'export':
        return cmd_export(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    exit(main())

