#!/usr/bin/env python3
"""
自动化超参数优化 Pipeline

自动执行完整的优化循环：
1. 生成新的推荐配置
2. 创建Trial目录并复制配置
3. 生成运行脚本
4. 并行运行所有Trial
5. 等待完成并收集结果
6. 将结果添加到Optuna study
7. 重复循环

使用方法：
    python3 auto_optimization_pipeline.py --n-trials 3 --max-iterations 5 --timeout 1800
"""

import os
import sys
import time
import json
import yaml
import shutil
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

# ==================== 配置 ====================
BASE_DIR = Path(__file__).parent.absolute()
EXPERIMENTS_DIR = BASE_DIR / "Experiments"
TRIALS_DIR = BASE_DIR / "trials"
GROUNDTRUTH = BASE_DIR / "Output/groundtruth_tum.txt"
EVAL_SCRIPT = BASE_DIR.parent / "AAE5303_assignment2_orbslam3_demo-/scripts/evaluate_vo_accuracy.py"
OPTUNA_SCRIPT = BASE_DIR / "manual_hyperparameter_optimization.py"

# ORB-SLAM3 配置
ORBSLAM3_DIR = BASE_DIR.parent / "ORB_SLAM3"
VOCABULARY = ORBSLAM3_DIR / "Vocabulary/ORBvoc.txt"
IMAGE_DIR = BASE_DIR.parent / "Datasets/HKisland_GNSS03/images"

# 运行脚本模板
RUN_SCRIPT_TEMPLATE = """#!/bin/bash

#==============================================================================
# ORB-SLAM3 单目模式运行脚本 - {trial_name}
# 自动生成的脚本
#==============================================================================

# 配置路径
ORBSLAM3_DIR="{orbslam3_dir}"
VOCABULARY="{vocabulary}"
CONFIG="{config}"
IMAGE_DIR="{image_dir}"
RGB_TXT="${{IMAGE_DIR}}/rgb.txt"
OUTPUT_DIR="{output_dir}"
GROUNDTRUTH="{groundtruth}"
EVAL_SCRIPT="{eval_script}"

# 创建输出目录
mkdir -p "${{OUTPUT_DIR}}"

echo "======================================================================"
echo "    ORB-SLAM3 单目模式 - {trial_name}"
echo "======================================================================"
echo ""

# 检查文件
echo "[1/5] 检查必要文件..."
if [ ! -f "${{VOCABULARY}}" ]; then
    echo "错误: 词汇表文件不存在: ${{VOCABULARY}}"
    exit 1
fi

if [ ! -f "${{CONFIG}}" ]; then
    echo "错误: 配置文件不存在: ${{CONFIG}}"
    exit 1
fi

if [ ! -f "${{RGB_TXT}}" ]; then
    echo "错误: rgb.txt 文件不存在: ${{RGB_TXT}}"
    exit 1
fi

echo "✓ 所有文件检查通过"

# 统计图像数量
IMAGE_COUNT=$(ls -1 "${{IMAGE_DIR}}"/*.png 2>/dev/null | wc -l)
echo ""
echo "[2/5] 数据集信息"
echo "  图像数量: ${{IMAGE_COUNT}}"
echo "  配置文件: ${{CONFIG}}"
echo "  输出目录: ${{OUTPUT_DIR}}"

# 运行 ORB-SLAM3
echo ""
echo "[3/5] 启动 ORB-SLAM3..."
echo "======================================================================"
echo ""

# 在Trial目录下运行，避免多进程冲突
cd "${{OUTPUT_DIR}}"

# 使用 Xvfb 运行 ORB-SLAM3
xvfb-run -a -s "-screen 0 1024x768x24" \\
    "${{ORBSLAM3_DIR}}/Examples/Monocular/mono_tum" \\
    "${{VOCABULARY}}" \\
    "${{CONFIG}}" \\
    "${{IMAGE_DIR}}"

# 检查运行结果
if [ $? -eq 0 ]; then
    echo ""
    echo "======================================================================"
    echo "✓ ORB-SLAM3 运行完成！"
    echo "======================================================================"
    
    # 检查轨迹文件
    if [ -f "KeyFrameTrajectory.txt" ]; then
        echo "  关键帧轨迹: ${{OUTPUT_DIR}}/KeyFrameTrajectory.txt"
        TRAJECTORY_FILE="${{OUTPUT_DIR}}/KeyFrameTrajectory.txt"
    else
        echo "  警告: KeyFrameTrajectory.txt 未生成"
        exit 1
    fi
    
else
    echo ""
    echo "✗ ORB-SLAM3 运行失败"
    exit 1
fi

# 评估轨迹精度
echo ""
echo "[4/5] 评估轨迹精度..."
echo "======================================================================"

if [ -f "${{GROUNDTRUTH}}" ] && [ -f "${{TRAJECTORY_FILE}}" ]; then
    EVAL_JSON="${{OUTPUT_DIR}}/evaluation.json"
    EVAL_WORKDIR="${{OUTPUT_DIR}}/evaluation_results"
    
    python3 "${{EVAL_SCRIPT}}" \\
        --groundtruth "${{GROUNDTRUTH}}" \\
        --estimated "${{TRAJECTORY_FILE}}" \\
        --t-max-diff 0.1 \\
        --delta-m 10.0 \\
        --workdir "${{EVAL_WORKDIR}}" \\
        --json-out "${{EVAL_JSON}}"
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✓ 评估完成！"
        echo "  评估结果: ${{EVAL_JSON}}"
    else
        echo ""
        echo "✗ 评估失败"
    fi
else
    echo "跳过评估（缺少 ground truth 或轨迹文件）"
fi

# 总结
echo ""
echo "[5/5] 任务完成总结"
echo "======================================================================"
echo "输出文件:"
ls -lh "${{OUTPUT_DIR}}"/*.txt 2>/dev/null
ls -lh "${{OUTPUT_DIR}}"/*.json 2>/dev/null
echo ""
echo "======================================================================"
echo "任务完成！"
echo "======================================================================"
"""


class AutoOptimizationPipeline:
    """自动化优化Pipeline"""
    
    def __init__(self, n_trials: int, max_iterations: int, timeout: int):
        self.n_trials = n_trials
        self.max_iterations = max_iterations
        self.timeout = timeout
        self.current_iteration = 0
        
    def log(self, message: str, level: str = "INFO"):
        """打印日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = {
            "INFO": "ℹ️ ",
            "SUCCESS": "✅",
            "ERROR": "❌",
            "WARNING": "⚠️ ",
            "STEP": "📍"
        }.get(level, "")
        print(f"[{timestamp}] {prefix} {message}")
    
    def run_command(self, cmd: List[str], cwd: Path = None) -> Tuple[int, str, str]:
        """运行命令并返回结果"""
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            self.log(f"命令超时: {' '.join(cmd)}", "WARNING")
            return -1, "", "Timeout"
        except Exception as e:
            self.log(f"命令执行失败: {e}", "ERROR")
            return -1, "", str(e)
    
    def generate_suggestions(self) -> Path:
        """步骤1: 生成新的推荐配置"""
        self.log("=" * 80, "STEP")
        self.log(f"步骤 1: 生成 {self.n_trials} 个推荐配置", "STEP")
        self.log("=" * 80, "STEP")
        
        cmd = [
            "python3",
            str(OPTUNA_SCRIPT),
            "suggest",
            "--n-suggestions", str(self.n_trials)
        ]
        
        returncode, stdout, stderr = self.run_command(cmd, cwd=BASE_DIR)
        
        if returncode != 0:
            self.log(f"生成推荐配置失败: {stderr}", "ERROR")
            return None
        
        # 解析输出找到suggestions目录
        for line in stdout.split('\n'):
            if 'suggestions_' in line and 'trials/' in line:
                # 提取路径
                parts = line.split('trials/')
                if len(parts) > 1:
                    dir_name = parts[1].strip()
                    suggestions_dir = TRIALS_DIR / dir_name
                    if suggestions_dir.exists():
                        self.log(f"推荐配置已生成: {suggestions_dir}", "SUCCESS")
                        return suggestions_dir
        
        # 如果解析失败，查找最新的suggestions目录
        suggestions_dirs = list(TRIALS_DIR.glob("suggestions_*"))
        if suggestions_dirs:
            latest_dir = max(suggestions_dirs, key=lambda p: p.stat().st_mtime)
            self.log(f"使用最新的推荐配置目录: {latest_dir}", "SUCCESS")
            return latest_dir
        
        self.log("未找到推荐配置目录", "ERROR")
        return None
    
    def create_trial_directories(self, suggestions_dir: Path) -> List[Path]:
        """步骤2: 创建Trial目录并复制配置"""
        self.log("=" * 80, "STEP")
        self.log("步骤 2: 创建Trial目录并复制配置", "STEP")
        self.log("=" * 80, "STEP")
        
        # 找到下一个可用的Trial编号
        existing_trials = list(EXPERIMENTS_DIR.glob("Trial_*"))
        if existing_trials:
            max_num = max([int(t.name.split('_')[1]) for t in existing_trials])
            start_num = max_num + 1
        else:
            start_num = 1
        
        trial_dirs = []
        suggestion_files = sorted(suggestions_dir.glob("suggestion_*.yaml"))
        
        for i, suggestion_file in enumerate(suggestion_files[:self.n_trials]):
            trial_num = start_num + i
            trial_name = f"Trial_{trial_num:02d}"
            trial_dir = EXPERIMENTS_DIR / trial_name
            
            # 创建目录
            trial_dir.mkdir(parents=True, exist_ok=True)
            
            # 复制配置文件
            config_dest = trial_dir / "config.yaml"
            shutil.copy(suggestion_file, config_dest)
            
            self.log(f"创建 {trial_name}: {config_dest}", "SUCCESS")
            trial_dirs.append(trial_dir)
        
        return trial_dirs
    
    def generate_run_scripts(self, trial_dirs: List[Path]) -> List[Path]:
        """步骤3: 生成运行脚本"""
        self.log("=" * 80, "STEP")
        self.log("步骤 3: 生成运行脚本", "STEP")
        self.log("=" * 80, "STEP")
        
        script_paths = []
        
        for trial_dir in trial_dirs:
            trial_name = trial_dir.name
            script_path = trial_dir / "run_orbslam3.sh"
            
            # 生成脚本内容
            script_content = RUN_SCRIPT_TEMPLATE.format(
                trial_name=trial_name,
                orbslam3_dir=ORBSLAM3_DIR,
                vocabulary=VOCABULARY,
                config=trial_dir / "config.yaml",
                image_dir=IMAGE_DIR,
                output_dir=trial_dir,
                groundtruth=GROUNDTRUTH,
                eval_script=EVAL_SCRIPT
            )
            
            # 写入脚本
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            # 添加执行权限
            script_path.chmod(0o755)
            
            self.log(f"生成脚本: {script_path}", "SUCCESS")
            script_paths.append(script_path)
        
        return script_paths
    
    def run_trials_parallel(self, trial_dirs: List[Path]) -> List[subprocess.Popen]:
        """步骤4: 并行运行所有Trial"""
        self.log("=" * 80, "STEP")
        self.log("步骤 4: 并行运行所有Trial", "STEP")
        self.log("=" * 80, "STEP")
        
        processes = []
        
        for trial_dir in trial_dirs:
            trial_name = trial_dir.name
            script_path = trial_dir / "run_orbslam3.sh"
            log_path = trial_dir / f"{trial_name.lower()}.log"
            
            # 启动进程
            with open(log_path, 'w') as log_file:
                process = subprocess.Popen(
                    ["bash", str(script_path)],
                    cwd=trial_dir,
                    stdout=log_file,
                    stderr=subprocess.STDOUT
                )
            
            processes.append((process, trial_name, log_path))
            self.log(f"启动 {trial_name} (PID: {process.pid})", "SUCCESS")
        
        return processes
    
    def wait_for_completion(self, processes: List[Tuple]) -> List[Path]:
        """步骤5: 等待所有进程完成（每个进程独立超时）"""
        self.log("=" * 80, "STEP")
        self.log(f"步骤 5: 等待所有进程完成 (每个Trial超时: {self.timeout}秒)", "STEP")
        self.log("=" * 80, "STEP")
        
        completed_trials = []
        # 记录每个进程的启动时间
        process_start_times = {trial_name: time.time() for _, trial_name, _ in processes}
        
        while processes:
            time.sleep(10)  # 每10秒检查一次
            
            # 检查完成的进程和超时的进程
            remaining = []
            for process, trial_name, log_path in processes:
                elapsed = time.time() - process_start_times[trial_name]
                
                # 检查是否超时
                if elapsed > self.timeout:
                    if process.poll() is None:
                        self.log(f"{trial_name} 超时 ({int(elapsed)}秒)，终止进程", "WARNING")
                        process.terminate()
                        time.sleep(2)  # 等待进程终止
                        if process.poll() is None:
                            process.kill()  # 强制终止
                    continue  # 不添加到completed_trials
                
                # 检查是否完成
                if process.poll() is not None:
                    returncode = process.returncode
                    if returncode == 0:
                        self.log(f"{trial_name} 完成 ✓ (用时: {int(elapsed)}秒)", "SUCCESS")
                        trial_dir = log_path.parent
                        completed_trials.append(trial_dir)
                    else:
                        self.log(f"{trial_name} 失败 (退出码: {returncode}, 用时: {int(elapsed)}秒)", "ERROR")
                else:
                    remaining.append((process, trial_name, log_path))
            
            processes = remaining
            
            if processes:
                status_info = []
                for _, trial_name, _ in processes:
                    elapsed = time.time() - process_start_times[trial_name]
                    remaining_time = self.timeout - elapsed
                    status_info.append(f"{trial_name}({int(elapsed)}s, 剩余{int(remaining_time)}s)")
                self.log(f"剩余 {len(processes)} 个进程: {', '.join(status_info)}", "INFO")
        
        return completed_trials
    
    def validate_json_file(self, json_path: Path) -> bool:
        """验证JSON文件是否有效且包含必要字段"""
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # 检查必要字段
            required_fields = ['rmse_ate', 'mean_ate', 'median_ate', 'std_ate', 
                             'min_ate', 'max_ate', 'rmse_rpe', 'mean_rpe', 
                             'median_rpe', 'std_rpe', 'min_rpe', 'max_rpe']
            
            for field in required_fields:
                if field not in data:
                    self.log(f"JSON缺少字段: {field}", "WARNING")
                    return False
                
                # 检查值是否为有效数字
                if not isinstance(data[field], (int, float)) or data[field] != data[field]:  # NaN检查
                    self.log(f"JSON字段 {field} 值无效: {data[field]}", "WARNING")
                    return False
            
            return True
            
        except json.JSONDecodeError as e:
            self.log(f"JSON解析失败: {e}", "WARNING")
            return False
        except Exception as e:
            self.log(f"JSON验证失败: {e}", "WARNING")
            return False
    
    def generate_fallback_evaluation(self, trial_dir: Path) -> bool:
        """为失败的Trial生成差值评估结果"""
        self.log(f"为 {trial_dir.name} 生成差值评估结果", "WARNING")
        
        eval_file = trial_dir / "evaluation.json"
        
        # 生成一个差值结果（所有指标设为较大的值，表示性能不佳）
        fallback_data = {
            "rmse_ate": 999.0,
            "mean_ate": 999.0,
            "median_ate": 999.0,
            "std_ate": 999.0,
            "min_ate": 999.0,
            "max_ate": 999.0,
            "rmse_rpe": 999.0,
            "mean_rpe": 999.0,
            "median_rpe": 999.0,
            "std_rpe": 999.0,
            "min_rpe": 999.0,
            "max_rpe": 999.0,
            "note": "Fallback evaluation - Trial failed or timed out"
        }
        
        try:
            with open(eval_file, 'w') as f:
                json.dump(fallback_data, f, indent=2)
            self.log(f"差值评估结果已生成: {eval_file}", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"生成差值评估失败: {e}", "ERROR")
            return False
    
    def collect_and_add_results(self, trial_dirs: List[Path]) -> int:
        """步骤6: 收集结果并添加到Optuna study（支持差值生成）"""
        self.log("=" * 80, "STEP")
        self.log("步骤 6: 收集结果并添加到Optuna study", "STEP")
        self.log("=" * 80, "STEP")
        
        added_count = 0
        
        for trial_dir in trial_dirs:
            trial_name = trial_dir.name
            config_file = trial_dir / "config.yaml"
            eval_file = trial_dir / "evaluation.json"
            
            # 检查配置文件
            if not config_file.exists():
                self.log(f"{trial_name}: 配置文件不存在，跳过", "WARNING")
                continue
            
            # 检查评估文件
            eval_valid = False
            if eval_file.exists():
                eval_valid = self.validate_json_file(eval_file)
                if eval_valid:
                    self.log(f"{trial_name}: 评估文件有效", "SUCCESS")
                else:
                    self.log(f"{trial_name}: 评估文件无效", "WARNING")
            else:
                self.log(f"{trial_name}: 评估文件不存在", "WARNING")
            
            # 如果评估文件无效或不存在，生成差值
            if not eval_valid:
                if not self.generate_fallback_evaluation(trial_dir):
                    self.log(f"{trial_name}: 无法生成差值，跳过", "ERROR")
                    continue
            
            # 复制到trials目录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            config_dest = TRIALS_DIR / f"{trial_name.lower()}_{timestamp}_config.yaml"
            eval_dest = TRIALS_DIR / f"{trial_name.lower()}_{timestamp}_evaluation.json"
            
            shutil.copy(config_file, config_dest)
            shutil.copy(eval_file, eval_dest)
            
            self.log(f"复制 {trial_name} 结果到 trials/", "SUCCESS")
            
            # 添加到Optuna study
            cmd = [
                "python3",
                str(OPTUNA_SCRIPT),
                "add",
                "--yaml", str(config_dest),
                "--json", str(eval_dest)
            ]
            
            returncode, stdout, stderr = self.run_command(cmd, cwd=BASE_DIR)
            
            if returncode == 0:
                self.log(f"{trial_name} 已添加到 Optuna study", "SUCCESS")
                added_count += 1
            else:
                self.log(f"{trial_name} 添加失败: {stderr}", "ERROR")
        
        return added_count
    
    def run_iteration(self) -> bool:
        """运行一次完整的迭代"""
        self.current_iteration += 1
        
        self.log("", "INFO")
        self.log("=" * 80, "STEP")
        self.log(f"开始第 {self.current_iteration} 次迭代", "STEP")
        self.log("=" * 80, "STEP")
        self.log("", "INFO")
        
        # 步骤1: 生成推荐配置
        suggestions_dir = self.generate_suggestions()
        if not suggestions_dir:
            return False
        
        # 步骤2: 创建Trial目录
        trial_dirs = self.create_trial_directories(suggestions_dir)
        if not trial_dirs:
            self.log("未能创建Trial目录", "ERROR")
            return False
        
        # 步骤3: 生成运行脚本
        script_paths = self.generate_run_scripts(trial_dirs)
        
        # 步骤4: 并行运行
        processes = self.run_trials_parallel(trial_dirs)
        
        # 步骤5: 等待完成
        completed_trials = self.wait_for_completion(processes)
        
        # 注意：即使没有Trial成功完成，我们也尝试收集结果（会生成差值）
        self.log(f"成功完成的Trial: {len(completed_trials)}/{len(trial_dirs)}", "INFO")
        
        # 步骤6: 收集结果（包括失败的Trial，会生成差值）
        added_count = self.collect_and_add_results(trial_dirs)
        
        self.log("", "INFO")
        self.log("=" * 80, "STEP")
        self.log(f"第 {self.current_iteration} 次迭代完成", "STEP")
        self.log(f"成功添加 {added_count}/{len(trial_dirs)} 个结果到Optuna", "STEP")
        self.log("=" * 80, "STEP")
        self.log("", "INFO")
        
        return added_count > 0
    
    def run(self):
        """运行完整的优化Pipeline"""
        self.log("", "INFO")
        self.log("=" * 80, "STEP")
        self.log("自动化超参数优化 Pipeline 启动", "STEP")
        self.log("=" * 80, "STEP")
        self.log(f"配置: {self.n_trials} 个Trial/迭代, 最多 {self.max_iterations} 次迭代", "INFO")
        self.log(f"超时: {self.timeout} 秒/Trial", "INFO")
        self.log("", "INFO")
        
        for i in range(self.max_iterations):
            success = self.run_iteration()
            
            if not success:
                self.log(f"迭代 {i+1} 失败，停止Pipeline", "ERROR")
                break
            
            if i < self.max_iterations - 1:
                self.log(f"等待5秒后开始下一次迭代...", "INFO")
                time.sleep(5)
        
        self.log("", "INFO")
        self.log("=" * 80, "STEP")
        self.log("自动化优化Pipeline完成", "STEP")
        self.log(f"总共完成 {self.current_iteration} 次迭代", "STEP")
        self.log("=" * 80, "STEP")


def main():
    parser = argparse.ArgumentParser(
        description="自动化超参数优化Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--n-trials',
        type=int,
        default=3,
        help='每次迭代运行的Trial数量 (默认: 3)'
    )
    
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=5,
        help='最大迭代次数 (默认: 5)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=2400,
        help='每个Trial的超时时间(秒) (默认: 1800 = 30分钟)'
    )
    
    args = parser.parse_args()
    
    # 创建并运行Pipeline
    pipeline = AutoOptimizationPipeline(
        n_trials=args.n_trials,
        max_iterations=args.max_iterations,
        timeout=args.timeout
    )
    
    try:
        pipeline.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断，正在退出...")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Pipeline失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
