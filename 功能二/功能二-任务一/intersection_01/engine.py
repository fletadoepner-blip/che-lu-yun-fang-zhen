# -*- coding: utf-8 -*-
"""轻量微观仿真引擎（CityFlow 兼容数据格式）。

在不依赖 CityFlow C++ 引擎（需 Docker/Linux 编译）的前提下，用纯 Python
复现单路口信号仿真核心行为，用于验证独立路口包"可跑通"：

- 车辆按 flow 的 startTime 生成，进入起点道路（feed_XX_D）；
- 沿道路 points 折线行驶，遵守最大速度与跟车间距；
- 在交叉口按 route 的相邻路段 (start,end) 查找 roadLinks 转向，
  并由信号灯 lightphases 的 availableRoadLinks 判定是否放行；
- 到达终点道路（exit / exit_border）末端即完成旅程，进入统计。

数据格式与 CityFlow 完全一致，因此也可被原生 CityFlow 引擎直接加载。
"""
from __future__ import annotations

import json
import math
from pathlib import Path


class SimError(RuntimeError):
    pass


def polyline_length(points) -> float:
    return sum(math.hypot(b["x"] - a["x"], b["y"] - a["y"])
               for a, b in zip(points, points[1:]))


class Network:
    """解析 roadnet.json 与 flow.json。"""

    def __init__(self, dir_path, flow_file=None):
        self.dir = Path(dir_path)
        rd = json.loads((self.dir / "roadnet.json").read_text(encoding="utf-8"))
        cfg = json.loads((self.dir / "cityflow.config.json").read_text(encoding="utf-8"))
        if flow_file is None:
            flow_file = cfg.get("flowFile", "flow.json")
        flow = json.loads((self.dir / flow_file).read_text(encoding="utf-8"))

        self.roads = {}
        for r in rd["roads"]:
            length = polyline_length(r["points"])
            self.roads[r["id"]] = {
                "start": r["startIntersection"], "end": r["endIntersection"],
                "length": length, "lanes": len(r["lanes"]),
                "max_speed": min((ln.get("maxSpeed", 13.89) for ln in r["lanes"]), default=13.89),
            }
        self.intersections = {}
        for it in rd["intersections"]:
            if it.get("virtual"):
                continue
            links = [{"start": l["startRoad"], "end": l["endRoad"], "type": l["type"]}
                     for l in it["roadLinks"]]
            phases = []
            for ph in it["trafficLight"].get("lightphases", []):
                # availableRoadLinks 是 roadLinks 的下标 -> (start, end) 转向对
                allowed = {(it["roadLinks"][idx]["startRoad"], it["roadLinks"][idx]["endRoad"])
                           for idx in ph["availableRoadLinks"]}
                phases.append({"time": ph["time"], "allowed": allowed})
            self.intersections[it["id"]] = {"roads": set(it["roads"]), "links": links,
                                            "phases": phases}
        self.flow = sorted(flow, key=lambda v: v["startTime"])
        # 预生成车辆生成时刻列表（按 startTime 排好）
        self._next_idx = 0
        self._t = 0.0

    # ---- 路由相关 ----
    def transition(self, junction, start_road, end_road) -> bool:
        it = self.intersections.get(junction)
        if not it:
            return start_road == end_road
        return any(l["start"] == start_road and l["end"] == end_road for l in it["links"])


class Simulator:
    """离散时间推进的信号灯微观仿真。"""

    def __init__(self, network: Network, algorithm="max_pressure", dt=1.0,
                 max_sim_time=3600.0, seed=20260816, acc=2.6, dec=4.5, headway=1.5):
        self.net = network
        self.algorithm = algorithm
        self.dt = dt
        self.max_time = max_sim_time
        self.acc = acc
        self.dec = dec
        self.headway = headway
        # 车辆：id -> dict
        self.vehicles = {}
        self.finished = []
        self._seq = 0
        # 每个控制路口的相位状态
        self.phase_state = {jid: {"idx": 0, "remain": self.net.intersections[jid]["phases"][0]["time"]}
                            for jid in self.net.intersections}

    def _gen_id(self):
        self._seq += 1
        return f"car_{self._seq}"

    def _lane_positions(self, road_id):
        """返回该道路当前车辆的车头位置列表（用于跟车）。"""
        out = []
        for v in self.vehicles.values():
            if v["road"] == road_id and v["status"] == "run":
                out.append(v["dist"])
        return out

    def step_phase(self):
        for jid, st in self.phase_state.items():
            st["remain"] -= self.dt
            if st["remain"] <= 0:
                phases = self.net.intersections[jid]["phases"]
                if self.algorithm == "max_pressure":
                    # 选择放行(进道,出道)对总车辆数最大的相位
                    best = 0
                    best_score = -1
                    counts = self._movement_counts(jid)
                    for idx, ph in enumerate(phases):
                        score = sum(counts.get(pair, 0) for pair in ph["allowed"])
                        if score > best_score:
                            best, best_score = idx, score
                    st["idx"] = best
                else:  # fixed: 顺序轮换
                    st["idx"] = (st["idx"] + 1) % len(phases)
                st["remain"] = phases[st["idx"]]["time"]

    def _movement_counts(self, jid):
        it = self.net.intersections[jid]
        # 统计当前在交叉口等待的车辆，按其(进道,出道)计数
        counts = {}
        for v in self.vehicles.values():
            if v["status"] != "run" or v["road"] not in it["roads"]:
                continue
            if v["idx"] + 1 < len(v["route"]):
                key = (v["road"], v["route"][v["idx"] + 1])
                counts[key] = counts.get(key, 0) + 1
        return counts

    def _phase_allows(self, jid, start_road, end_road):
        st = self.phase_state[jid]
        phases = self.net.intersections[jid]["phases"]
        return (start_road, end_road) in phases[st["idx"]]["allowed"]

    def spawn(self):
        net = self.net
        while net._next_idx < len(net.flow) and net.flow[net._next_idx]["startTime"] <= net._t:
            spec = net.flow[net._next_idx]
            net._next_idx += 1
            route = spec["route"]
            if not route:
                continue
            veh_spec = spec.get("vehicle", {})
            v = {
                "id": self._gen_id(), "route": route, "idx": 0,
                "road": route[0], "dist": 0.0, "status": "run",
                "speed": 0.0, "start": net._t,
                "max_speed": veh_spec.get("maxSpeed", 13.89),
                "length": veh_spec.get("length", 5.0),
                "max_acc": veh_spec.get("maxPosAcc", self.acc),
                "max_dec": veh_spec.get("maxNegAcc", self.dec),
                "t0": net._t,
            }
            # 禁止在同一道路出生时重叠到已有车（简单后移）
            self.vehicles[v["id"]] = v

    def move(self):
        net = self.net
        # 1) 确定每个控制路口该相位放行的进入道路
        # 2) 更新每辆车位置
        ordered = sorted(self.vehicles.values(), key=lambda v: v["dist"])
        for v in ordered:
            if v["status"] != "run":
                continue
            road = self.roads_of(v["road"])
            max_speed = v["max_speed"]
            # 距下一道路/交叉口的距离
            remaining = road["length"] - v["dist"]
            # 前车距离
            ahead = self._ahead_distance(v, road)
            # 信号灯限制
            allowed = True
            next_road = None
            if v["idx"] + 1 < len(v["route"]):
                next_road = v["route"][v["idx"] + 1]
            junction = road["end"]
            if road["end"] in net.intersections:
                if next_road is not None and not net.transition(junction, v["road"], next_road):
                    # 无效转向：标记异常（正常包不应出现）
                    allowed = False
                elif next_road is not None and not self._phase_allows(road["end"], v["road"], next_road):
                    # 信号灯未放行该转向
                    allowed = False
            # 速度更新（简化的加速/限速）
            if next_road is None:
                # 旅程最后一段（exit / exit_border）：自由行驶到终点
                v["speed"] = min(max_speed, v["speed"] + v["max_acc"] * self.dt)
            elif allowed:
                # 信号灯放行：加速通过
                v["speed"] = min(max_speed, v["speed"] + v["max_acc"] * self.dt)
            else:
                # 信号灯未放行 / 无效转向：减速或停车等待
                v["speed"] = max(0.0, v["speed"] - v["max_dec"] * self.dt)
            # 跟车限制：保持 headway 车距
            if ahead is not None:
                gap = ahead - v["dist"]
                v["speed"] = min(v["speed"], max(0.0, gap / max(self.headway, 1e-6)))
            # 移动
            v["dist"] += v["speed"] * self.dt
            # 到达道路末端
            if v["dist"] >= road["length"] - 1e-6:
                v["dist"] = 0.0
                if v["idx"] + 1 < len(v["route"]):
                    v["idx"] += 1
                    v["road"] = v["route"][v["idx"]]
                else:
                    # 旅程完成
                    v["status"] = "done"
                    v["finish"] = net._t
                    self.finished.append(v)

    def roads_of(self, rid):
        return self.net.roads[rid]

    def _ahead_distance(self, v, road):
        """返回同路同向（朝 end）的前车车头距离；无前车返回 None。"""
        ahead = None
        for other in self.vehicles.values():
            if other["id"] == v["id"] or other["status"] != "run":
                continue
            if other["road"] == v["road"] and other["dist"] > v["dist"]:
                d = other["dist"] - v["dist"] - other["length"]
                if ahead is None or d < ahead:
                    ahead = max(d, 0.0)
        return ahead

    def run(self, report_every=None):
        net = self.net
        max_time = self.max_time
        while net._t <= max_time and (net._next_idx < len(net.flow) or self.vehicles):
            self.spawn()
            self.step_phase()
            self.move()
            # 清理已完成车辆
            self.vehicles = {k: v for k, v in self.vehicles.items() if v["status"] != "done"}
            net._t += self.dt
            if report_every and int(net._t) % report_every == 0:
                print(f"  t={int(net._t):5d}s  active={len(self.vehicles):4d}  finished={len(self.finished)}")
        return self.summary()

    def summary(self):
        net = self.net
        total = len(net.flow)
        n = len(self.finished)
        tt = [v["finish"] - v["t0"] for v in self.finished]
        avg_tt = sum(tt) / len(tt) if tt else 0.0
        # 理想自由流时间（按最大速度沿路由）
        free = 0.0
        for spec in net.flow:
            route = spec["route"]
            t = sum(net.roads[r]["length"] for r in route) / max(spec.get("vehicle", {}).get("maxSpeed", 13.89), 1e-6)
            free += t
        free = free / total if total else 0.0
        return {
            "total_demand": total,
            "generated": net._next_idx,
            "finished": n,
            "active_at_end": len(self.vehicles),
            "throughput": round(n / max(total, 1), 4),
            "average_travel_time_s": round(avg_tt, 3),
            "freeflow_mean_s": round(free, 3),
            "estimated_delay_s": round(max(0.0, avg_tt - free), 3),
        }
