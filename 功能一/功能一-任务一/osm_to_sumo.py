import os
import subprocess
import osmnx as ox

# --- 配置部分 ---
# 1. 设置目标地点 (二选一)
# PLACE_NAME = "雄安新区管委会, 中国"  # 可以用地名
LOCATION = (38.9429, 115.8977)  # 或者用 (纬度, 经度)，这里是雄安新区管委会的坐标

# 2. 设置导出的路网范围（米）
NETWORK_RADIUS = 300  # 对于单路口，300-500米通常足够

# 3. 设置输出文件名
OUTPUT_OSM_FILE = "xiongan_intersection.osm"
OUTPUT_NET_FILE = "xiongan_intersection.net.xml"

# --- 核心逻辑 ---

def download_osm_data(lat, lon, radius, output_file):
    """1. 使用OSMnx下载OSM数据并保存为 .osm 文件"""
    print(f"📍 正在从 OpenStreetMap 下载数据 (中心: {lat}, {lon}, 半径: {radius}m)...")
    
    # 关键修复：指定 simplify=False，保留原始节点，才能导出为 OSM XML
    G = ox.graph_from_point((lat, lon), dist=radius, network_type='drive', simplify=False)
    
    # 保存为 OSM XML 格式（注意：需要 unsimplified 图）
    ox.save_graph_xml(G, filepath=output_file)
    print(f"✅ OSM 数据已保存至: {output_file}")
    return output_file

def convert_osm_to_sumo(osm_file, net_file):
    """2. 使用SUMO的netconvert工具将 .osm 转换为 .net.xml"""
    print("⚙️  正在使用 netconvert 将 OSM 数据转换为 SUMO 路网...")
    
    # 检查 SUMO_HOME 环境变量
    sumo_home = os.environ.get('SUMO_HOME')
    if not sumo_home:
        print("❌ 错误: 未找到 SUMO_HOME 环境变量，请确保 SUMO 已正确安装并配置。")
        return False

    # 构建 netconvert 命令
    netconvert_cmd = [
        os.path.join(sumo_home, 'bin', 'netconvert'),
        '--osm-files', osm_file,
        '-o', net_file,
        '--geometry.remove',
        '--roundabouts.guess',
        '--ramps.guess',
        '--junctions.join',
        '--tls.guess-signals',
        '--tls.discard-simple',
        '--tls.join',
    ]
    
    try:
        result = subprocess.run(netconvert_cmd, check=True, capture_output=True, text=True)
        print(f"✅ SUMO 路网已成功生成: {net_file}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ netconvert 执行失败: {e}")
        print(f"错误信息: {e.stderr}")
        return False

# --- 执行主流程 ---
if __name__ == "__main__":
    # 如果提供了地名，则进行地理编码
    if 'PLACE_NAME' in locals() and PLACE_NAME:
        print(f"📍 正在查找地名: {PLACE_NAME}...")
        try:
            lat, lon = ox.geocode(PLACE_NAME)
            print(f"✅ 找到坐标: ({lat}, {lon})")
            LOCATION = (lat, lon)
        except Exception as e:
            print(f"❌ 地名解析失败: {e}. 请检查地名或使用经纬度坐标。")
            exit(1)

    lat, lon = LOCATION
    print("🚦 开始执行 OSM 到 SUMO 的自动转换流程...")

    # 1. 下载 OSM 数据
    osm_file = download_osm_data(lat, lon, NETWORK_RADIUS, OUTPUT_OSM_FILE)

    # 2. 转换为 SUMO 路网
    success = convert_osm_to_sumo(osm_file, OUTPUT_NET_FILE)

    if success:
        print("\n🎉 全部完成！")
        print(f"📂 你可以在 SUMO-GUI 中打开生成的路网文件: {OUTPUT_NET_FILE}")
        print(f"💡 如需调整路网，可用 netedit 工具编辑: netedit {OUTPUT_NET_FILE}")
    else:
        print("\n❌ 转换过程中出现错误，请检查上方错误信息。")