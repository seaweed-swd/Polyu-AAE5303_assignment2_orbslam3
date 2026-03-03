#!/usr/bin/env python3
"""
从 ROS bag 提取 GPS/GNSS 数据并转换为 TUM 格式的 Ground Truth
TUM 格式: timestamp tx ty tz qx qy qz qw
"""

import rosbag
import numpy as np
import os

def extract_gps_data(bag_file):
    """从 bag 文件提取 GPS 位置数据"""
    
    print("="*70)
    print("提取 GPS Ground Truth 数据")
    print("="*70)
    print(f"Bag 文件: {bag_file}")
    print()
    
    bag = rosbag.Bag(bag_file, 'r')
    
    # 提取 GPS 位置数据
    gps_data = []
    gps_topic = "/dji_osdk_ros/gps_position"
    
    print(f"正在提取 GPS 数据从 topic: {gps_topic}")
    
    count = 0
    for topic, msg, t in bag.read_messages(topics=[gps_topic]):
        timestamp = t.to_sec()
        # GPS 数据：纬度、经度、高度
        latitude = msg.latitude
        longitude = msg.longitude
        altitude = msg.altitude
        
        gps_data.append([timestamp, latitude, longitude, altitude])
        count += 1
        
        if count % 1000 == 0:
            print(f"  已处理: {count} 条 GPS 数据")
    
    bag.close()
    
    print(f"\n✅ 共提取 {len(gps_data)} 条 GPS 数据")
    
    return np.array(gps_data)

def gps_to_enu(gps_data):
    """
    将 GPS (纬度、经度、高度) 转换为 ENU (东北天) 坐标系
    使用第一个点作为原点
    """
    
    print("\n正在转换 GPS 到 ENU 坐标...")
    
    # 地球半径 (米)
    R = 6378137.0
    
    # 参考点（第一个 GPS 点）
    lat0 = np.radians(gps_data[0, 1])
    lon0 = np.radians(gps_data[0, 2])
    alt0 = gps_data[0, 3]
    
    enu_data = []
    
    for i, point in enumerate(gps_data):
        timestamp = point[0]
        lat = np.radians(point[1])
        lon = np.radians(point[2])
        alt = point[3]
        
        # 计算 ENU 坐标
        dLat = lat - lat0
        dLon = lon - lon0
        dAlt = alt - alt0
        
        # ENU 坐标
        E = R * dLon * np.cos(lat0)  # 东
        N = R * dLat                  # 北
        U = dAlt                      # 天
        
        enu_data.append([timestamp, E, N, U])
    
    enu_array = np.array(enu_data)
    
    print(f"✅ GPS 转换完成")
    print(f"  参考点: Lat={np.degrees(lat0):.6f}°, Lon={np.degrees(lon0):.6f}°, Alt={alt0:.2f}m")
    print(f"  ENU 范围:")
    print(f"    E: [{enu_array[:, 1].min():.2f}, {enu_array[:, 1].max():.2f}] 米")
    print(f"    N: [{enu_array[:, 2].min():.2f}, {enu_array[:, 2].max():.2f}] 米")
    print(f"    U: [{enu_array[:, 3].min():.2f}, {enu_array[:, 3].max():.2f}] 米")
    
    return enu_array

def save_tum_format(enu_data, output_file):
    """
    保存为 TUM 格式: timestamp tx ty tz qx qy qz qw
    由于 GPS 只提供位置信息，姿态使用单位四元数 (0, 0, 0, 1)
    """
    
    print(f"\n正在保存 TUM 格式文件: {output_file}")
    
    with open(output_file, 'w') as f:
        f.write("# TUM trajectory format\n")
        f.write("# timestamp tx ty tz qx qy qz qw\n")
        f.write("# Note: Orientation is identity quaternion (0,0,0,1) as GPS only provides position\n")
        
        for point in enu_data:
            timestamp = point[0]
            e, n, u = point[1], point[2], point[3]
            # TUM 格式: timestamp tx ty tz qx qy qz qw
            # 使用单位四元数 (0, 0, 0, 1) 表示无旋转
            f.write(f"{timestamp:.9f} {e:.6f} {n:.6f} {u:.6f} 0.0 0.0 0.0 1.0\n")
    
    print(f"✅ TUM 格式文件已保存")
    print(f"  总共 {len(enu_data)} 个位姿")

def main():
    """主函数"""
    
    # 配置
    bag_file = "/root/AAE5305/Datasets/HKisland_GNSS03/HKisland_GNSS03.bag"
    output_dir = "/root/AAE5305/Run2/Output"
    tum_output = os.path.join(output_dir, "groundtruth_tum.txt")
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. 提取 GPS 数据
    gps_data = extract_gps_data(bag_file)
    
    # 2. 转换为 ENU 坐标
    enu_data = gps_to_enu(gps_data)
    
    # 3. 保存为 TUM 格式
    save_tum_format(enu_data, tum_output)
    
    print("\n" + "="*70)
    print("提取完成！")
    print("="*70)
    print(f"\n输出文件: {tum_output}")
    print(f"格式: TUM (timestamp tx ty tz qx qy qz qw)")
    print(f"坐标系: ENU (East-North-Up)")
    print(f"姿态: 单位四元数 (仅位置真值)")

if __name__ == "__main__":
    main()

