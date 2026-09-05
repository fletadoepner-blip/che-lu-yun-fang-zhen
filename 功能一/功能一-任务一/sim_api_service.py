"""兼容入口：启动功能一·任务一 SUMO 数据接口服务。"""
from src.service import create_app

app = create_app()

if __name__ == "__main__":
    print("SUMO 场景建模与数据接口: http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
