#!/usr/bin/env python3
"""
批量添加 trials 目录中的所有实验数据到 Optuna study
"""

import os
import subprocess
from pathlib import Path

TRIALS_DIR = Path("/root/AAE5305/Run4/trials")
SCRIPT = Path("/root/AAE5305/Run4/manual_hyperparameter_optimization.py")

def main():
    # 查找所有配置文件
    config_files = sorted(TRIALS_DIR.glob("*_config.yaml"))
    
    print(f"找到 {len(config_files)} 个配置文件")
    print("="*80)
    
    success_count = 0
    fail_count = 0
    
    for config_file in config_files:
        # 构造对应的 evaluation.json 文件名
        trial_name = config_file.stem.replace("_config", "")
        json_file = TRIALS_DIR / f"{trial_name}_evaluation.json"
        
        if not json_file.exists():
            print(f"⚠️  跳过 {trial_name}: 缺少 evaluation.json")
            fail_count += 1
            continue
        
        # 调用 manual_hyperparameter_optimization.py add
        cmd = [
            "python3", str(SCRIPT),
            "add",
            "--yaml", str(config_file),
            "--json", str(json_file)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print(f"✅ {trial_name}")
                success_count += 1
            else:
                print(f"❌ {trial_name}: {result.stderr[:100]}")
                fail_count += 1
        except Exception as e:
            print(f"❌ {trial_name}: {str(e)}")
            fail_count += 1
    
    print("="*80)
    print(f"完成！成功: {success_count}, 失败: {fail_count}")

if __name__ == "__main__":
    main()


