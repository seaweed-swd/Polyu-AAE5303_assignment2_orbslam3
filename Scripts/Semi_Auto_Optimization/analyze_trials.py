#!/usr/bin/env python3
"""
分析 trials 目录中所有实验的表现
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

# 配置
TRIALS_DIR = Path("/root/AAE5305/Run4/trials")

# 四个关键指标
METRICS = {
    'ate_rmse_m': 'minimize',  # 越小越好
    'rpe_trans_drift_m_per_m': 'minimize',  # 越小越好
    'rpe_rot_drift_deg_per_100m': 'minimize',  # 越小越好
    'completeness_pct': 'maximize',  # 越大越好
}

def load_all_trials() -> List[Dict]:
    """加载所有试验的评估结果"""
    trials = []
    
    # 查找所有 evaluation.json 文件
    for json_file in sorted(TRIALS_DIR.glob("*evaluation.json")):
        trial_name = json_file.stem.replace("_evaluation", "")
        
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
                data['trial_name'] = trial_name
                data['json_file'] = json_file.name
                trials.append(data)
        except Exception as e:
            print(f"警告: 无法加载 {json_file.name}: {e}")
    
    return trials

def rank_trials(trials: List[Dict]) -> Dict[str, List[Tuple[str, float]]]:
    """对每个指标进行排名"""
    rankings = {}
    
    for metric, direction in METRICS.items():
        # 提取该指标的所有值
        metric_values = []
        for trial in trials:
            if metric in trial:
                metric_values.append((trial['trial_name'], trial[metric]))
        
        # 排序
        reverse = (direction == 'maximize')
        metric_values.sort(key=lambda x: x[1], reverse=reverse)
        
        rankings[metric] = metric_values
    
    return rankings

def compute_composite_score(trial: Dict) -> float:
    """
    计算综合得分（越小越好）
    使用与 manual_hyperparameter_optimization.py 相同的权重
    """
    w_ate = 1.0
    w_rpe_trans = 0.5
    w_rpe_rot = 0.01
    w_completeness = -0.01  # 负权重（因为越大越好）
    
    score = (
        w_ate * trial.get('ate_rmse_m', 100.0) +
        w_rpe_trans * trial.get('rpe_trans_drift_m_per_m', 10.0) +
        w_rpe_rot * trial.get('rpe_rot_drift_deg_per_100m', 200.0) +
        w_completeness * trial.get('completeness_pct', 0.0)
    )
    
    return score

def main():
    print("="*80)
    print("Trials 目录实验表现分析")
    print("="*80)
    
    # 加载所有试验
    trials = load_all_trials()
    print(f"\n找到 {len(trials)} 个试验结果\n")
    
    if len(trials) == 0:
        print("没有找到任何试验结果！")
        return
    
    # 对每个指标进行排名
    rankings = rank_trials(trials)
    
    # 显示每个指标的 Top 10
    print("="*80)
    print("各指标 Top 10 表现")
    print("="*80)
    
    for metric, direction in METRICS.items():
        print(f"\n📊 {metric} ({'越小越好' if direction == 'minimize' else '越大越好'})")
        print("-" * 80)
        
        top_trials = rankings[metric][:10]
        for rank, (trial_name, value) in enumerate(top_trials, 1):
            print(f"  {rank:2d}. {trial_name:30s} {value:10.4f}")
    
    # 计算综合得分
    print("\n" + "="*80)
    print("综合得分排名 (Top 15)")
    print("="*80)
    print("综合得分考虑了所有四个指标，越小越好")
    print("-" * 80)
    
    trial_scores = []
    for trial in trials:
        score = compute_composite_score(trial)
        trial_scores.append((trial['trial_name'], score, trial))
    
    trial_scores.sort(key=lambda x: x[1])
    
    print(f"\n{'排名':<6} {'Trial名称':<30} {'综合得分':<12} {'ATE RMSE':<12} {'RPE Trans':<12} {'RPE Rot':<12} {'完整度%':<10}")
    print("-" * 110)
    
    for rank, (trial_name, score, trial) in enumerate(trial_scores[:15], 1):
        ate = trial.get('ate_rmse_m', 0)
        rpe_trans = trial.get('rpe_trans_drift_m_per_m', 0)
        rpe_rot = trial.get('rpe_rot_drift_deg_per_100m', 0)
        completeness = trial.get('completeness_pct', 0)
        
        print(f"{rank:<6} {trial_name:<30} {score:<12.4f} {ate:<12.4f} {rpe_trans:<12.4f} {rpe_rot:<12.4f} {completeness:<10.2f}")
    
    # 显示新实验（Trial_28, 29, 30）的表现
    print("\n" + "="*80)
    print("新实验 (Trial_28, 29, 30) 表现")
    print("="*80)
    
    new_trials = [t for t in trials if t['trial_name'] in ['trial_28', 'trial_29', 'trial_30']]
    
    if new_trials:
        for trial in new_trials:
            score = compute_composite_score(trial)
            rank = next(i for i, (name, _, _) in enumerate(trial_scores, 1) if name == trial['trial_name'])
            
            print(f"\n🔬 {trial['trial_name'].upper()}")
            print(f"   综合排名: #{rank} / {len(trials)}")
            print(f"   综合得分: {score:.4f}")
            print(f"   ATE RMSE: {trial.get('ate_rmse_m', 0):.4f} m")
            print(f"   RPE Trans Drift: {trial.get('rpe_trans_drift_m_per_m', 0):.4f} m/m")
            print(f"   RPE Rot Drift: {trial.get('rpe_rot_drift_deg_per_100m', 0):.4f} deg/100m")
            print(f"   Completeness: {trial.get('completeness_pct', 0):.2f} %")
    
    # 保存分析结果
    output_file = TRIALS_DIR / "analysis_results.json"
    with open(output_file, 'w') as f:
        json.dump({
            'total_trials': len(trials),
            'rankings': {k: [(name, float(val)) for name, val in v[:10]] for k, v in rankings.items()},
            'top_15_composite': [(name, float(score)) for name, score, _ in trial_scores[:15]],
            'new_trials_performance': [
                {
                    'trial_name': t['trial_name'],
                    'composite_score': float(compute_composite_score(t)),
                    'rank': next(i for i, (name, _, _) in enumerate(trial_scores, 1) if name == t['trial_name']),
                    'metrics': {
                        'ate_rmse_m': t.get('ate_rmse_m', 0),
                        'rpe_trans_drift_m_per_m': t.get('rpe_trans_drift_m_per_m', 0),
                        'rpe_rot_drift_deg_per_100m': t.get('rpe_rot_drift_deg_per_100m', 0),
                        'completeness_pct': t.get('completeness_pct', 0),
                    }
                }
                for t in new_trials
            ]
        }, f, indent=2)
    
    print(f"\n✅ 分析结果已保存到: {output_file}")
    print("="*80)

if __name__ == "__main__":
    main()


