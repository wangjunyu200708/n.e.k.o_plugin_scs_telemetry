from plugin.sdk.plugin import (
    NekoPluginBase, neko_plugin, plugin_entry, lifecycle,
    Ok, Err, SdkError, get_plugin_logger
)
from typing import Any, Optional
import asyncio
import time
import os
import datetime
from .scs_telemetry import SCSTelemetryReader

# 文件日志——不依赖 get_plugin_logger，直接写 data 目录
_FLOG_PATH = None

def _flog(msg: str):
    """写文件日志到 data/scs_debug.log"""
    global _FLOG_PATH
    try:
        if _FLOG_PATH is None:
            # 延迟确定路径——在 startup 之后 config_dir 才可用
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"{ts} {msg}\n"
        with open(_FLOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


@neko_plugin
class SCSTelemetryPlugin(NekoPluginBase):
    """SCS 遥测数据插件"""

    # ── P0 驾驶安全阈值 ──
    _SPEED_LIMIT_TOLERANCE = 5     # 超出限速 +5 km/h 才算超速
    _FUEL_WARN_FACTOR = 0.25       # 油量 < 25%
    _ADBLUE_WARN_FACTOR = 0.20     # 尿素 < 20%
    _WATER_TEMP_WARN = 100         # 水温 > 100°C
    _OIL_TEMP_WARN = 110           # 油温 > 110°C
    _BRAKE_TEMP_WARN = 200         # 刹车温度 > 200°C
    _AIR_PRESSURE_WARN = 0.6       # 气压 < 0.6 bar
    _OIL_PRESSURE_WARN = 10        # 油压 < 10
    _STALL_SPEED_KMH = 10          # 车速 > 此值且熄火=行驶中熄火
    _OVERSPEED_WINDOW = 60         # 连续超速窗口(秒)
    _OVERSPEED_LIMIT = 3           # 窗口内超速次数触发"连续超速"

    # ── P0 驾驶行为阈值 ──
    _HARD_BRAKE_THRESHOLD = 0.7    # 刹车力度
    _HARD_BRAKE_WINDOW = 300       # 急刹窗口 5 分钟
    _HIGH_SPEED_KMH = 60           # 高速阈值
    _CRUISE_INTERFERENCE = 0.5     # 巡航中油门超过此值=乱踩
    _PARKING_DRIVE_KMH = 5         # 手刹未松速度阈值

    # ── P1 阈值 ──
    _DAMAGE_WARN = 0.2             # 任一磨损 > 20%
    _CARGO_DAMAGE_WARN = 0.3       # 挂车货物损伤 > 30%
    _IDLE_WARN_SEC = 600           # 怠速 > 10 分钟
    _ARRIVE_DIST_M = 5000          # 接近目的地 < 5km

    # ── P2/P3 周期 ──
    _ROUTE_REPORT_SEC = 180        # 路程播报间隔 3 分钟(真实时间)
    _FUEL_REMIND_ONCE = True       # 低油量只推一次

    # ── 夜间判断 ──
    _NIGHT_START_HOUR = 22
    _NIGHT_END_HOUR = 5

    # ── 推送冷却 ──
    _COOLDOWN_P0 = 8.0             # P0 驾驶安全/行为 8 秒
    _COOLDOWN_P1 = 60.0            # P1 车辆状态 60 秒
    _COOLDOWN_P2 = 30.0            # P2 系统提示 30 秒
    _COOLDOWN_P3 = 180.0           # P3 周期陪伴 3 分钟

    def __init__(self, ctx: Any):
        super().__init__(ctx)
        self.logger = get_plugin_logger(__name__)
        self.telemetry_reader = None
        self._cached_data = None      # 最新遥测数据缓存
        self._cache_time = 0          # 缓存时间戳
        # ── 推送冷却 ──
        self._cool = {}               # {category: last_push_monotonic}
        # ── 状态记忆（只推变化） ──
        self._prev = {}               # 上次轮询的状态快照
        # ── 持续计时器 ──
        self._idle_start = 0.0        # 怠速开始时间
        self._night_sent = False      # 夜间提醒已发
        self._fuel_reminded = False   # 低油量提醒已发（只一次）
        # ── 超速窗口计数器 ──
        self._overspeed_times = []    # 最近超速帧的时间戳
        # ── 急刹窗口 ──
        self._hbrake_times = []       # 最近急刹的时间戳
        # ── 首次连接标志 ──
        self._was_connected = False   # 用于上车问候

    @lifecycle(id="startup")
    async def on_startup(self, **_):
        """插件启动"""
        # 初始化文件日志路径
        global _FLOG_PATH
        _FLOG_PATH = str(self.config_dir / "scs_debug.log")
        _flog("========== SCS 插件启动 ==========")
        _flog(f"config_dir = {self.config_dir}")
        _flog(f"Python: {os.sys.executable}, {os.sys.version}")
        _flog(f"PID: {os.getpid()}")

        self.logger.info("SCS 遥测插件启动中...")

        # 初始化遥测读取器
        try:
            self.telemetry_reader = SCSTelemetryReader()
            _flog(f"Reader 初始化成功: view={hex(self.telemetry_reader._map_view)}, handle={hex(self.telemetry_reader._map_handle)}")
            self.logger.info("✅ SCS 遥测读取器初始化成功")
            # 立即读一次，填充缓存
            try:
                data = await asyncio.to_thread(self.telemetry_reader.read_data)
                if data:
                    self._cached_data = data
                    self._cache_time = time.monotonic()
                    _flog(f"startup read_data OK: sdk={data.get('sdk_active')}, speed={data.get('truck',{}).get('dashboard',{}).get('speed',0)}")
                else:
                    _flog("startup read_data returned None")
            except Exception as e:
                _flog(f"startup read_data failed: {type(e).__name__}: {e}")
        except Exception as e:
            _flog(f"Reader 初始化失败: {type(e).__name__}: {e}")
            self.logger.warning(f"⚠️ 初始化遥测读取器失败: {e}（游戏未启动？启动后会自动重试）")

        # 启动轮询循环
        self._poll_running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        _flog("Poll loop started")

        return Ok({
            "status": "ready",
            "message": "SCS 遥测插件已启动",
            "cached_data_available": self._cached_data is not None
        })

    @lifecycle(id="shutdown")
    async def on_shutdown(self, **_):
        """插件关闭"""
        self.logger.info("SCS 遥测插件关闭中...")
        self._poll_running = False
        if self.telemetry_reader:
            self.telemetry_reader.close()
        return Ok({"status": "stopped"})

    async def _poll_loop(self):
        """轮询主循环，每 0.5 秒读取遥测并检测事件"""
        _flog("_poll_loop: started")
        while self._poll_running:
            try:
                await asyncio.sleep(0.5)
            except Exception:
                break

            # 如果读取器未初始化，尝试重新初始化
            if not self.telemetry_reader:
                try:
                    self.telemetry_reader = SCSTelemetryReader()
                    _flog(f"Reader 重连成功: view={hex(self.telemetry_reader._map_view)}")
                except Exception as e:
                    _flog(f"Reader 重连失败: {type(e).__name__}: {e}")
                    continue

            try:
                data = await asyncio.to_thread(self.telemetry_reader.read_data)
                if data:
                    self._cached_data = data
                    self._cache_time = time.monotonic()
                    _flog(f"poll OK: sdk={data.get('sdk_active')}, speed={data.get('truck',{}).get('dashboard',{}).get('speed',0)}")
                    self._check_and_alert(data)
                else:
                    _flog("poll: read_data() 返回 None")

            except AttributeError as e:
                _flog(f"poll AttributeError: {e}")
            except OSError as e:
                _flog(f"poll OSError: {e}, closing reader")
                self.telemetry_reader.close()
                self.telemetry_reader = None
                self._cached_data = None
            except Exception as e:
                _flog(f"poll Exception: {type(e).__name__}: {e}")
                _flog(f"  detail: {e}")

        _flog("_poll_loop: stopped")

    def _push(self, category: str, priority: int, events: list, msg_type: str = "proactive_read"):
        """统一推送：聚合同类事件，单次 push_message"""
        if not events:
            return
        method_map = {0: "proactive_notification", 1: "proactive_read", 2: "hud"}
        self.push_message(
            source="scs_telemetry",
            message_type=method_map.get(priority, msg_type),
            description=f"ETS2 {category}",
            priority=1 if priority == 0 else 3,
            content={
                "game": "ETS2",
                "category": category,
                "priority": priority,
                "events": events,
                "timestamp": time.time(),
            },
        )

    def _ok_cooldown(self, key: str, sec: float) -> bool:
        """检查是否超过冷却时间，是则更新时间戳"""
        now = time.monotonic()
        last = self._cool.get(key, 0)
        if now - last < sec:
            return False
        self._cool[key] = now
        return True

    def _chg(self, key, cur_or: bool, trigger_or: bool = True) -> bool:
        """检测 bool 型状态变化并更新记忆"""
        prev = self._prev.get(key, False)
        cur = bool(cur_or == trigger_or)
        self._prev[key] = cur
        return cur and not prev  # 从 False → True

    def _chg_set(self, key, cur):
        """记录当前值到 prev，返回是否不同"""
        prev = self._prev.get(key)
        self._prev[key] = cur
        return cur != prev

    # ══════════════════════════════════════════════════════════════
    #  核心 - 事件检测与分类推送 (每 0.5s 轮询)
    # ══════════════════════════════════════════════════════════════
    def _check_and_alert(self, data: dict):
        now = time.monotonic()
        truck  = data.get("truck", {})
        dash   = truck.get("dashboard", {})
        nav    = data.get("navigation", {})
        job    = data.get("job", {})
        events = data.get("special_events", {})
        ctrl   = data.get("controls", {})

        speed_ms   = dash.get("speed", 0)
        speed_kmh  = speed_ms * 3.6
        limit_ms   = nav.get("speed_limit", 0)
        limit_kmh  = limit_ms * 3.6 if limit_ms > 0 else 0
        has_limit  = limit_kmh > 0
        engine_on  = truck.get("engine", {}).get("enabled", False)
        parking_on = truck.get("brakes", {}).get("parking", False)
        cruise_on  = truck.get("cruise_control", False)
        on_job     = job.get("on_job", False)
        route_dist = nav.get("route_distance", 0)

        # ── 上车问候 ──
        if engine_on and self._chg("engine_on", engine_on):
            ident = truck.get("identity", {})
            brand = ident.get("brand", "")
            name  = ident.get("name", "")
            if self._ok_cooldown("p2", self._COOLDOWN_P2):
                self._push("greeting", 1, [{
                    "type": "engine_on",
                    "truck": f"{brand} {name}".strip() or "未知卡车",
                }], "hud")

        # ── 熄火 ──
        if not engine_on and self._chg("engine_off", engine_on, True):
            if self._ok_cooldown("p2", self._COOLDOWN_P2):
                self._push("system", 2, [{"type": "engine_off"}], "hud")

        # ── 夜间提醒 ──
        game_mins = data.get("common", {}).get("game_time_minutes", 0)
        game_hour = (game_mins // 60) % 24
        is_night  = (game_hour >= self._NIGHT_START_HOUR) or (game_hour < self._NIGHT_END_HOUR)
        if is_night and not self._night_sent and self._ok_cooldown("p2", self._COOLDOWN_P2):
            lights = truck.get("lights", {})
            no_lights = not lights.get("beam_low") and not lights.get("beam_high")
            self._push("night", 1, [{
                "type": "night",
                "hour": game_hour,
                "lights_off": no_lights,
            }], "hud")
            self._night_sent = True
        if not is_night:
            self._night_sent = False

        # ═════════════════════════════════════════
        #  P0 驾驶安全 (respond, 8s 冷却)
        # ═════════════════════════════════════════
        p0_safety = []

        # 超速
        if has_limit:
            speeding = speed_kmh > (limit_kmh + self._SPEED_LIMIT_TOLERANCE)
            if speeding:
                self._overspeed_times.append(now)
                if self._chg("speeding", speeding):
                    p0_safety.append({
                        "type": "overspeed",
                        "speed_kmh": round(speed_kmh, 1),
                        "limit_kmh": round(limit_kmh, 1),
                    })
            else:
                self._prev["speeding"] = False
            # 清理超速窗口
            self._overspeed_times = [t for t in self._overspeed_times if now - t <= self._OVERSPEED_WINDOW]
            # 连续超速
            if len(self._overspeed_times) >= self._OVERSPEED_LIMIT:
                if self._chg("consecutive_overspeed", True):
                    p0_safety.append({
                        "type": "consecutive_overspeed",
                        "count": len(self._overspeed_times),
                        "window_sec": self._OVERSPEED_WINDOW,
                    })
                self._overspeed_times = []
        else:
            self._prev["speeding"] = False

        # 燃油过低 (<25%) —— 只推一次
        fuel_amt = dash.get("fuel", {}).get("amount", 0)
        fuel_cap = dash.get("fuel", {}).get("capacity", 1) or 1
        fuel_pct = fuel_amt / fuel_cap
        fuel_range = dash.get("fuel", {}).get("range", 0)
        if fuel_pct < self._FUEL_WARN_FACTOR and not self._fuel_reminded:
            p0_safety.append({
                "type": "low_fuel",
                "amount_l": round(fuel_amt, 1),
                "capacity_l": round(fuel_cap, 1),
                "range_km": round(fuel_range, 1) if fuel_range else None,
            })
            self._fuel_reminded = True
        if fuel_pct >= self._FUEL_WARN_FACTOR:
            self._fuel_reminded = False

        # AdBlue 过低
        if self._chg("adblue_warn",
                     dash.get("adblue", {}).get("amount", 1) / max(dash.get("adblue", {}).get("capacity", 1), 1)
                     < self._ADBLUE_WARN_FACTOR):
            p0_safety.append({"type": "low_adblue"})

        # 水温过高
        if self._chg("water_warn", dash.get("temperature", {}).get("water", 0) > self._WATER_TEMP_WARN):
            p0_safety.append({"type": "water_overheat", "temp_c": round(dash.get("temperature", {}).get("water", 0), 1)})

        # 油温过高
        if self._chg("oil_temp_warn", dash.get("temperature", {}).get("oil", 0) > self._OIL_TEMP_WARN):
            p0_safety.append({"type": "oil_overheat", "temp_c": round(dash.get("temperature", {}).get("oil", 0), 1)})

        # 刹车温度过高
        bt = dash.get("pressure", {}).get("brake_temperature", 0)
        if self._chg("brake_temp_warn", bt > self._BRAKE_TEMP_WARN):
            p0_safety.append({"type": "brake_overheat", "temp_c": round(bt, 1)})

        # 气压过低
        ap = dash.get("pressure", {}).get("air", 0)
        if self._chg("air_warn", ap > 0 and ap < self._AIR_PRESSURE_WARN):
            p0_safety.append({"type": "low_air_pressure", "pressure_bar": round(ap, 2)})

        # 机油压力异常
        op = dash.get("pressure", {}).get("oil", 0)
        if self._chg("oil_press_warn", op > 0 and op < self._OIL_PRESSURE_WARN):
            p0_safety.append({"type": "low_oil_pressure", "pressure": round(op, 1)})

        # 行驶中熄火
        stalled = not engine_on and speed_kmh > self._STALL_SPEED_KMH
        if self._chg("stalled", stalled):
            p0_safety.append({"type": "stalled_while_moving", "speed_kmh": round(speed_kmh, 1)})

        # 收到罚单
        if self._chg("fined", events.get("fined", False)):
            p0_safety.append({"type": "fined"})

        if p0_safety and self._ok_cooldown("p0_safety", self._COOLDOWN_P0):
            self._push("driving_safety", 0, p0_safety, "proactive_notification")

        # ═════════════════════════════════════════
        #  P0 驾驶行为 (respond, 8s 冷却)
        # ═════════════════════════════════════════
        p0_behav = []

        # 急刹车
        gbrake = ctrl.get("game_brake", 0)
        hbrake = gbrake >= self._HARD_BRAKE_THRESHOLD
        if hbrake and not self._prev.get("_hbrake_active"):
            self._hbrake_times.append(now)
        self._prev["_hbrake_active"] = hbrake
        # 清理与检测
        cutoff = now - self._HARD_BRAKE_WINDOW if hasattr(self, '_HARD_BRAKE_WINDOW') else now - 300
        self._hbrake_times = [t for t in self._hbrake_times if t > cutoff]
        if self._chg("hard_brake", hbrake):
            p0_behav.append({"type": "hard_brake", "brake_strength": round(gbrake, 2)})

        # 高速急刹（同时触发，单独标记）
        if hbrake and speed_kmh >= self._HIGH_SPEED_KMH and self._chg("high_speed_hard_brake", True):
            p0_behav.append({"type": "high_speed_hard_brake", "speed_kmh": round(speed_kmh, 1), "brake_strength": round(gbrake, 2)})
        if not hbrake:
            self._prev["high_speed_hard_brake"] = False

        # 巡航乱踩
        throttle = ctrl.get("user_throttle", 0)
        cruise_interference = cruise_on and throttle >= self._CRUISE_INTERFERENCE
        if self._chg("cruise_interference", cruise_interference):
            p0_behav.append({"type": "cruise_interference", "throttle": round(throttle, 2)})

        # 手刹未松行驶
        parking_drive = parking_on and speed_kmh > self._PARKING_DRIVE_KMH
        if self._chg("parking_drive", parking_drive):
            p0_behav.append({"type": "parking_brake_on_drive", "speed_kmh": round(speed_kmh, 1)})

        if p0_behav and self._ok_cooldown("p0_behav", self._COOLDOWN_P0):
            self._push("driving_behavior", 0, p0_behav, "proactive_notification")

        # ═════════════════════════════════════════
        #  P1 任务语义 (read, 不打断)
        # ═════════════════════════════════════════
        p1_job = []

        if self._chg("on_job", on_job):
            if on_job:
                cargo   = job.get("cargo", {})
                dst     = job.get("destination", {})
                src     = job.get("source", {})
                ident   = truck.get("identity", {})
                p1_job.append({
                    "type": "job_started",
                    "cargo": cargo.get("name", ""),
                    "cargo_mass_t": round(cargo.get("mass", 0) / 1000, 1),
                    "from_city": src.get("city", ""),
                    "to_city": dst.get("city", ""),
                    "to_company": dst.get("company", ""),
                    "distance_km": round(job.get("planned_distance_km", 0), 1),
                    "income": (job.get("income", 0) or 0) / 100,
                    "truck": f"{ident.get('brand','')} {ident.get('name','')}".strip(),
                })

        if self._chg("job_delivered", job.get("job_delivered", False)):
            p1_job.append({"type": "job_delivered"})
        if self._chg("job_cancelled", job.get("job_cancelled", False)):
            p1_job.append({"type": "job_cancelled"})

        # 接近目的地
        if on_job and 0 < route_dist < self._ARRIVE_DIST_M:
            if self._chg("near_dest", True):
                dst_city = job.get("destination", {}).get("city", "")
                p1_job.append({
                    "type": "approaching_destination",
                    "city": dst_city,
                    "remaining_km": round(route_dist / 1000, 1),
                })
        else:
            self._prev["near_dest"] = False

        # 加油完成
        if self._chg("refuel_payed", events.get("refuel_payed", False)):
            p1_job.append({"type": "refuel_complete"})

        if p1_job:
            self._push("job_event", 1, p1_job)

        # ═════════════════════════════════════════
        #  P1 车辆状态 (read, 60s 冷却)
        # ═════════════════════════════════════════
        p1_wear = []

        # 车辆磨损
        dmg = truck.get("damage", {})
        worn = {k: round(v, 3) for k, v in dmg.items() if v and v > self._DAMAGE_WARN}
        if worn and self._chg_set("worn_parts", frozenset(worn.keys())):
            p1_wear.append({"type": "truck_wear", "parts": worn})

        # 挂车货物损伤 - 需要从 trailer_zone 读取
        # TODO: 等 trailer 数据加入 read_data()

        # 长时间怠速 (10分钟)
        is_idling = engine_on and speed_kmh < 1 and not parking_on
        if is_idling:
            if self._idle_start == 0:
                self._idle_start = now
            elif (now - self._idle_start) >= self._IDLE_WARN_SEC and self._chg("long_idle", True):
                p1_wear.append({"type": "long_idle", "minutes": int((now - self._idle_start) // 60)})
                self._idle_start = now
        else:
            self._idle_start = 0
            self._prev["long_idle"] = False

        if p1_wear and self._ok_cooldown("p1_wear", self._COOLDOWN_P1):
            self._push("vehicle_status", 1, p1_wear)

        # ═════════════════════════════════════════
        #  P3 路程播报 (read, 3min 冷却)
        # ═════════════════════════════════════════
        if on_job and route_dist > 0 and self._ok_cooldown("p3_route", self._COOLDOWN_P3):
            dst_city = job.get("destination", {}).get("city", "目的地")
            rt_min   = nav.get("route_time", 0) / 60 if nav.get("route_time", 0) > 0 else 0
            h, m     = int(rt_min // 60), int(rt_min % 60)
            eta      = f"{h}h{m}m" if h > 0 else f"{m}min"
            self._push("route_update", 3, [{
                "type": "route_progress",
                "destination": dst_city,
                "remaining_km": round(route_dist / 1000, 1),
                "eta": eta,
            }])

    async def _ensure_fresh(self):
        """确保缓存未过期，过期则刷新。返回 True 表示有可用数据"""
        if not self.telemetry_reader:
            try:
                self.telemetry_reader = SCSTelemetryReader()
            except Exception:
                return False
        stale = (time.monotonic() - self._cache_time) > self._CACHE_STALE_SEC
        if stale or self._cached_data is None:
            try:
                data = await asyncio.to_thread(self.telemetry_reader.read_data)
                if data:
                    self._cached_data = data
                    self._cache_time = time.monotonic()
                    # 惰性刷新时也检测状态变化
                    self._check_and_alert(data)
            except Exception:
                self.telemetry_reader.close()
                self.telemetry_reader = None
                return False
        return self._cached_data is not None

    @plugin_entry(
        id="get_telemetry",
        name="获取遥测数据",
        description="获取当前完整的车辆遥测数据，包含速度、油量、位置、任务等所有字段",
        input_schema={
            "type": "object",
            "properties": {}
        }
    )
    async def get_telemetry(self, **_):
        """获取当前完整遥测数据（缓存过期时惰性刷新）"""
        if not await self._ensure_fresh():
            return Err(SdkError("未获取到遥测数据（SDK 未激活或游戏暂停）"))
        return Ok({"data": self._cached_data})

    @plugin_entry(
        id="get_truck_status",
        name="获取车辆状态",
        description="获取车辆关键状态摘要：速度、转速、油量、温度、气压、灯光、档位、里程",
        input_schema={
            "type": "object",
            "properties": {}
        }
    )
    async def get_truck_status(self, **_):
        """获取车辆关键状态摘要（缓存过期时惰性刷新）"""
        if not await self._ensure_fresh():
            return Err(SdkError("遥测读取器未初始化或无数据"))
        data = self._cached_data
        if not data:
            return Err(SdkError("未获取到车辆状态数据"))

        truck = data.get("truck", {})
        dashboard = truck.get("dashboard", {})
        status = {
            "speed": dashboard.get("speed", 0),
            "rpm": dashboard.get("rpm", 0),
            "fuel": {
                "amount": dashboard.get("fuel", {}).get("amount", 0),
                "capacity": dashboard.get("fuel", {}).get("capacity", 0),
                "consumption": dashboard.get("fuel", {}).get("average_consumption", 0),
                "range": dashboard.get("fuel", {}).get("range", 0),
            },
            "temperature": {
                "water": dashboard.get("temperature", {}).get("water", 0),
                "oil": dashboard.get("temperature", {}).get("oil", 0),
            },
            "pressure": {
                "oil": dashboard.get("pressure", {}).get("oil", 0),
                "air": dashboard.get("pressure", {}).get("air", 0),
            },
            "battery_voltage": dashboard.get("battery_voltage", 0),
            "odometer": dashboard.get("odometer", 0),
            "cruise_control_speed": dashboard.get("cruise_control_speed", 0),
            "engine": {
                "enabled": truck.get("engine", {}).get("enabled", False),
                "electric": truck.get("engine", {}).get("electric", False),
            },
            "gears": {
                "current": truck.get("gears", {}).get("current", 0),
                "dashboard": truck.get("gears", {}).get("dashboard", 0),
                "shifter_slot": truck.get("gears", {}).get("shifter_slot", 0),
            },
            "brakes": {
                "parking": truck.get("brakes", {}).get("parking", False),
                "motor_brake": truck.get("brakes", {}).get("motor_brake", False),
                "air_pressure_warning": truck.get("brakes", {}).get("air_pressure_warning", False),
                "air_pressure_emergency": truck.get("brakes", {}).get("air_pressure_emergency", False),
            },
            "lights": {
                "parking": truck.get("lights", {}).get("parking", False),
                "beam_low": truck.get("lights", {}).get("beam_low", False),
                "beam_high": truck.get("lights", {}).get("beam_high", False),
                "brake": truck.get("lights", {}).get("brake", False),
                "reverse": truck.get("lights", {}).get("reverse", False),
                "hazard": truck.get("lights", {}).get("hazard", False),
                "blinker_left": truck.get("lights", {}).get("blinker_left", False),
                "blinker_right": truck.get("lights", {}).get("blinker_right", False),
            },
            "damage": {
                "engine": truck.get("damage", {}).get("engine", 0),
                "transmission": truck.get("damage", {}).get("transmission", 0),
                "cabin": truck.get("damage", {}).get("cabin", 0),
                "chassis": truck.get("damage", {}).get("chassis", 0),
                "wheels": truck.get("damage", {}).get("wheels", 0),
            },
            "identity": truck.get("identity", {}),
            "position": truck.get("position", {}),
        }
        return Ok({"status": status})

    @plugin_entry(
        id="get_navigation",
        name="获取导航信息",
        description="获取当前导航信息：剩余距离、预计时间、限速、是否超速",
        input_schema={
            "type": "object",
            "properties": {}
        }
    )
    async def get_navigation(self, **_):
        """获取导航信息（缓存过期时惰性刷新）"""
        if not await self._ensure_fresh():
            return Err(SdkError("遥测读取器未初始化或无数据"))
        data = self._cached_data

        nav = data.get("navigation", {})
        dashboard = data.get("truck", {}).get("dashboard", {})
        job = data.get("job", {})

        speed_ms = dashboard.get("speed", 0)
        speed_kmh = speed_ms * 3.6
        limit_ms = nav.get("speed_limit", 0)
        limit_kmh = limit_ms * 3.6 if limit_ms > 0 else 0
        route_dist_m = nav.get("route_distance", 0)
        route_dist_km = route_dist_m / 1000 if route_dist_m > 0 else 0
        route_time_s = nav.get("route_time", 0)
        route_time_min = route_time_s / 60 if route_time_s > 0 else 0

        is_speeding = limit_kmh > 0 and speed_kmh > (limit_kmh + self._SPEED_LIMIT_TOLERANCE)

        result = {
            "speed_kmh": round(speed_kmh, 1),
            "speed_limit_kmh": round(limit_kmh, 1) if limit_kmh > 0 else None,
            "is_speeding": is_speeding,
            "route_distance_km": round(route_dist_km, 1),
            "route_time_minutes": round(route_time_min, 1),
            "on_job": job.get("on_job", False),
            "destination": job.get("destination", {}).get("city", "") if job.get("on_job") else None,
        }
        return Ok({"navigation": result})
