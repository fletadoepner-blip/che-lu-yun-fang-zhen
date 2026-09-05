import os
import subprocess
import tempfile
import zipfile
from flask import Flask, request, send_file, jsonify
import osmnx as ox

app = Flask(__name__)

@app.route('/generate_scenario', methods=['GET'])
def generate_scenario():
    """生成完整的仿真场景：路网 + 车流 + 配置文件，返回 ZIP 包"""
    try:
        lat = float(request.args.get('lat', 38.9429))
        lon = float(request.args.get('lon', 115.8977))
        radius = int(request.args.get('radius', 300))
        duration = int(request.args.get('duration', 3600))
    except ValueError:
        return jsonify({"error": "Invalid parameters"}), 400

    # 1. 下载并转换路网
    try:
        G = ox.graph_from_point((lat, lon), dist=radius, network_type='drive', simplify=False)
    except Exception as e:
        return jsonify({"error": f"OSM download failed: {str(e)}"}), 500

    with tempfile.NamedTemporaryFile(suffix='.osm', delete=False) as tmp_osm:
        ox.save_graph_xml(G, filepath=tmp_osm.name)
        osm_path = tmp_osm.name

    sumo_home = os.environ.get('SUMO_HOME')
    if not sumo_home:
        return jsonify({"error": "SUMO_HOME not set"}), 500

    try:
        # 生成 .net.xml
        net_path = tempfile.NamedTemporaryFile(suffix='.net.xml', delete=False).name
        netconvert_cmd = [
            os.path.join(sumo_home, 'bin', 'netconvert'),
            '--osm-files', osm_path,
            '-o', net_path,
            '--geometry.remove',
            '--roundabouts.guess',
            '--ramps.guess',
            '--junctions.join',
            '--tls.guess-signals',
            '--tls.discard-simple',
            '--tls.join',
        ]
        subprocess.run(netconvert_cmd, check=True, capture_output=True)
        os.unlink(osm_path)

        # 生成 .rou.xml
        rou_path = tempfile.NamedTemporaryFile(suffix='.rou.xml', delete=False).name
        random_trips = os.path.join(sumo_home, 'tools', 'randomTrips.py')
        subprocess.run([
            'python', random_trips,
            '-n', net_path,
            '-r', rou_path,
            '-e', str(duration),
            '--period', '1',
            '--flows', '10'
        ], check=True, capture_output=True)

        # 生成 .sumocfg
        cfg_path = tempfile.NamedTemporaryFile(suffix='.sumocfg', delete=False).name
        cfg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="{os.path.basename(net_path)}"/>
        <route-files value="{os.path.basename(rou_path)}"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="{duration}"/>
    </time>
</configuration>'''
        with open(cfg_path, 'w') as f:
            f.write(cfg_content)

        # 打包 ZIP
        zip_path = tempfile.NamedTemporaryFile(suffix='.zip', delete=False).name
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(net_path, os.path.basename(net_path))
            zf.write(rou_path, os.path.basename(rou_path))
            zf.write(cfg_path, os.path.basename(cfg_path))

        # 清理临时文件
        os.unlink(net_path)
        os.unlink(rou_path)
        os.unlink(cfg_path)

        return send_file(zip_path, as_attachment=True, download_name='scenario.zip', mimetype='application/zip')

    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"SUMO tool failed: {e.stderr.decode()}"}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

if __name__ == '__main__':
    # 启动 Flask 开发服务器
    print("🚦 Starting OSM API service on http://127.0.0.1:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)