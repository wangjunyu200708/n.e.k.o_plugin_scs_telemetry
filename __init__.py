from plugin.sdk.plugin import (
    NekoPluginBase, neko_plugin, plugin_entry, lifecycle, timer_interval,
    Ok, Err, SdkError, get_plugin_logger
)
from typing import Any, Optional
import asyncio
import time
from .scs_telemetry import SCSTelemetryReader


@neko_plugin
class SCSTelemetryPlugin(NekoPluginBase):
    """SCS 遥测数据插件"""

    # ── 状态变化推送阈值 ──
    _FUEL_WARN_FACTOR = 0.25       # 油量低于容量 25% 时推送
    _ADBLUE_WARN_FACTOR = 0.20     # 尿素低于容量 20% 时推送
    _AIR_PRESSURE_WARN = 0.6       # 气压低于 0.6 bar 时推送
    _OIL_PRESSURE_WARN = 40        # 油压低于 40 时推送
    _WATER_TEMP_WARN = 100         # 水温超过 100°C 时推送
    _OIL_TEMP_WARN = 110           # 油温超过 110°C 时推送
    _BRAKE_TEMP_WARN = 200         # 刹车温度超过 200°C 时推送
    _SPEED_LIMIT_TOLERANCE = 5     # 超速容忍值 km/h（限速+5以内不报）

    def __init__(self, ctx: Any):
        super().__init__(ctx)
        self.logger = get_plugin_logger(__name__)
        self.telemetry_reader = None
        self._last_alert_state = {}  # 记录上一次推送的状态，用于变化检测
        self._cached_data = None      # 最新遥测数据缓存
        self._cache_time = 0          # 缓存时间戳

    @lifecycle(id="startup")
    async def on_startup(self, **_):
        """插件启动"""
        self.logger.info("SCS 遥测插件启动中...")

        # 初始化遥测读取器
        try:
            self.telemetry_reader = SCSTelemetryReader()
            self.logger.info("✅ SCS 遥测读取器初始化成功")
        except Exception as e:
            self.logger.warning(f"⚠️ 初始化遥测读取器失败: {e}（游戏未启动？插件启动后会自动重试）")
            # 不阻止插件启动，timer_interval 里会重试

        # 注册静态 UI
        if (self.config_dir / "static").exists():
            ok = self.register_static_ui(
                "static",
                index_file="index.html",
                cache_control="no-cache, no-store, must-revalidate",
            )
            if ok:
                self.logger.info("✅ 遥测控制台已注册，访问: http://localhost:48916/plugin/scs_telemetry/ui/")
            else:
                self.logger.warning("注册静态UI失败")

        return Ok({
            "status": "ready",
            "message": "SCS 遥测插件已启动"
        })

    @lifecycle(id="shutdown")
    async def on_shutdown(self, **_):
        """插件关闭"""
        self.logger.info("SCS 遥测插件关闭中...")
        if self.telemetry_reader:
            self.telemetry_reader.close()
        return Ok({"status": "stopped"})

    @timer_interval(id="telemetry_poll", seconds=0.5, auto_start=True)
    async def _poll_telemetry(self, **_):
        """定时轮询遥测数据，更新缓存并检测状态突变"""
        # 如果读取器未初始化，尝试重新初始化
        if not self.telemetry_reader:
            try:
                self.telemetry_reader = SCSTelemetryReader()
                self.logger.info("✅ 遥测读取器重新连接成功")
            except Exception:
                return  # 游戏还没启动，静默等待

        try:
            data = await asyncio.to_thread(self.telemetry_reader.read_data)
            if data:
                self._cached_data = data
                self._cache_time = time.monotonic()
                # ── 状态变化检测 ──
                self._check_and_alert(data)
            else:
                self.logger.debug("read_data() 返回 None（sdkActive=False 或游戏暂停）")

        except AttributeError as e:
            # 结构体字段访问错误——代码 bug，不应重置连接
            self.logger.error(f"结构体字段错误（代码问题）: {e}")
        except OSError as e:
            # access violation 等内存访问错误
            self.logger.error(f"内存访问错误（指针截断?）: {e}, map_view={self.telemetry_reader._map_view}")
            self.telemetry_reader.close()
            self.telemetry_reader = None
            self._cached_data = None
        except Exception as e:
            self.logger.error(f"采集遥测数据失败: {type(e).__name__}: {e}")
            # 读取失败可能是游戏关闭了，释放读取器等待重连
            if self.telemetry_reader:
                self.telemetry_reader.close()
                self.telemetry_reader = None
            self._cached_data = None



    def _check_and_alert(self, data: dict):
        """检测关键状态变化，只在突变时推送消息给主系统"""
        alerts = []
        truck = data.get("truck", {})
        dashboard = truck.get("dashboard", {})
        nav = data.get("navigation", {})
        job = data.get("job", {})
        events = data.get("special_events", {})
        identity = truck.get("identity", {})
        last = self._last_alert_state

        fuel = dashboard.get("fuel", {})
        adblue = dashboard.get("adblue", {})
        temp = dashboard.get("temperature", {})
        pressure = dashboard.get("pressure", {})

        # ═══════════════════════════════════════════
        #  1. 超速判断
        # ═══════════════════════════════════════════
        speed_ms = dashboard.get("speed", 0)
        speed_kmh = speed_ms * 3.6
        limit_ms = nav.get("speed_limit", 0)
        limit_kmh = limit_ms * 3.6 if limit_ms > 0 else 0
        was_speeding = last.get("speeding", False)
        is_speeding = limit_kmh > 0 and speed_kmh > (limit_kmh + self._SPEED_LIMIT_TOLERANCE)
        if is_speeding and not was_speeding:
            alerts.append(f"🚨 超速警告！当前 {speed_kmh:.0f} km/h，限速 {limit_kmh:.0f} km/h")
        elif not is_speeding and was_speeding:
            alerts.append(f"✅ 已恢复限速内: {speed_kmh:.0f} km/h")

        # ═══════════════════════════════════════════
        #  2. 油量预警
        # ═══════════════════════════════════════════
        fuel_amount = fuel.get("amount", 0)
        fuel_capacity = fuel.get("capacity", 1) or 1
        fuel_ratio = fuel_amount / fuel_capacity
        was_fuel_warn = last.get("fuel_warning", False)
        is_fuel_warn = fuel_ratio < self._FUEL_WARN_FACTOR
        if is_fuel_warn and not was_fuel_warn:
            alerts.append(f"⛽ 低油量警报！剩余 {fuel_amount:.1f}L ({fuel_ratio*100:.0f}%)，续航 {fuel.get('range', 0):.0f} km")
        elif not is_fuel_warn and was_fuel_warn:
            alerts.append(f"⛽ 油量已恢复: {fuel_amount:.1f}L ({fuel_ratio*100:.0f}%)")

        # ═══════════════════════════════════════════
        #  3. 尿素预警
        # ═══════════════════════════════════════════
        adblue_amount = adblue.get("amount", 0)
        adblue_capacity = adblue.get("capacity", 1) or 1
        adblue_ratio = adblue_amount / adblue_capacity
        was_adblue_warn = last.get("adblue_warning", False)
        is_adblue_warn = adblue_ratio < self._ADBLUE_WARN_FACTOR
        if is_adblue_warn and not was_adblue_warn:
            alerts.append(f"💧 尿素不足！剩余 {adblue_amount:.1f}L ({adblue_ratio*100:.0f}%)")
        elif not is_adblue_warn and was_adblue_warn:
            alerts.append(f"💧 尿素已恢复: {adblue_amount:.1f}L ({adblue_ratio*100:.0f}%)")

        # ═══════════════════════════════════════════
        #  4. 水温预警
        # ═══════════════════════════════════════════
        water_temp = temp.get("water", 0)
        was_water_warn = last.get("water_warning", False)
        is_water_warn = water_temp > self._WATER_TEMP_WARN
        if is_water_warn and not was_water_warn:
            alerts.append(f"🌡️ 水温过高！{water_temp:.0f}°C（阈值 {self._WATER_TEMP_WARN}°C）")
        elif not is_water_warn and was_water_warn:
            alerts.append(f"🌡️ 水温已恢复: {water_temp:.0f}°C")

        # ═══════════════════════════════════════════
        #  5. 油温预警
        # ═══════════════════════════════════════════
        oil_temp = temp.get("oil", 0)
        was_oil_temp_warn = last.get("oil_temp_warning", False)
        is_oil_temp_warn = oil_temp > self._OIL_TEMP_WARN
        if is_oil_temp_warn and not was_oil_temp_warn:
            alerts.append(f"🌡️ 油温过高！{oil_temp:.0f}°C（阈值 {self._OIL_TEMP_WARN}°C）")
        elif not is_oil_temp_warn and was_oil_temp_warn:
            alerts.append(f"🌡️ 油温已恢复: {oil_temp:.0f}°C")

        # ═══════════════════════════════════════════
        #  6. 刹车温度预警
        # ═══════════════════════════════════════════
        brake_temp = pressure.get("brake_temperature", 0)
        was_brake_temp_warn = last.get("brake_temp_warning", False)
        is_brake_temp_warn = brake_temp > self._BRAKE_TEMP_WARN
        if is_brake_temp_warn and not was_brake_temp_warn:
            alerts.append(f"🔥 刹车过热！{brake_temp:.0f}°C（阈值 {self._BRAKE_TEMP_WARN}°C）")
        elif not is_brake_temp_warn and was_brake_temp_warn:
            alerts.append(f"🔥 刹车温度已恢复: {brake_temp:.0f}°C")

        # ═══════════════════════════════════════════
        #  7. 气压预警
        # ═══════════════════════════════════════════
        air_pressure = pressure.get("air", 0)
        was_air_warn = last.get("air_warning", False)
        is_air_warn = air_pressure < self._AIR_PRESSURE_WARN and air_pressure > 0
        if is_air_warn and not was_air_warn:
            alerts.append(f"🛑 低气压警报！气压 {air_pressure:.2f} bar")
        elif not is_air_warn and was_air_warn:
            alerts.append(f"🛑 气压已恢复: {air_pressure:.2f} bar")

        # ═══════════════════════════════════════════
        #  8. 油压预警
        # ═══════════════════════════════════════════
        oil_pressure = pressure.get("oil", 0)
        was_oil_press_warn = last.get("oil_press_warning", False)
        is_oil_press_warn = oil_pressure > 0 and oil_pressure < self._OIL_PRESSURE_WARN
        if is_oil_press_warn and not was_oil_press_warn:
            alerts.append(f"⚠️ 油压过低！{oil_pressure:.1f}（阈值 {self._OIL_PRESSURE_WARN}）")
        elif not is_oil_press_warn and was_oil_press_warn:
            alerts.append(f"⚠️ 油压已恢复: {oil_pressure:.1f}")

        # ═══════════════════════════════════════════
        #  9. 发动机状态变化
        # ═══════════════════════════════════════════
        engine_on = truck.get("engine", {}).get("enabled", False)
        was_engine_on = last.get("engine_on", False)
        if engine_on and not was_engine_on:
            brand = identity.get("brand", "")
            name = identity.get("name", "")
            truck_label = f"{brand} {name}".strip() or "卡车"
            alerts.append(f"🔑 发动机已启动！{truck_label} 准备出发")
        elif not engine_on and was_engine_on:
            alerts.append("🔑 发动机已熄火")

        # ═══════════════════════════════════════════
        #  10. 任务状态变化
        # ═══════════════════════════════════════════
        on_job = job.get("on_job", False)
        was_on_job = last.get("on_job", False)
        if on_job and not was_on_job:
            cargo_name = job.get("cargo", {}).get("name", "未知货物")
            dst_city = job.get("destination", {}).get("city", "未知")
            dst_company = job.get("destination", {}).get("company", "")
            src_city = job.get("source", {}).get("city", "")
            distance = job.get("planned_distance_km", 0)
            income = (job.get("income", 0) or 0) / 100
            brand = identity.get("brand", "")
            name = identity.get("name", "")
            truck_label = f"{brand} {name}".strip() or "卡车"

            msg = f"📋 新任务！从 {src_city} 出发 → {dst_city}"
            if dst_company:
                msg += f"（{dst_company}）"
            msg += f"\n🚛 驾驶 {truck_label}"
            msg += f"\n📦 货物: {cargo_name}"
            msg += f"\n📏 距离: {distance:.0f} km"
            msg += f"\n💰 预计收入: ¥{income:,.0f}"
            alerts.append(msg)

        # 10b. 任务交付/取消——独立监听脉冲信号，不等 on_job 变 False
        job_delivered = job.get("job_delivered", False)
        job_cancelled = job.get("job_cancelled", False)
        was_delivered = last.get("job_delivered", False)
        was_cancelled = last.get("job_cancelled", False)
        if job_delivered and not was_delivered:
            alerts.append("📋 任务已交付！辛苦了！")
        if job_cancelled and not was_cancelled:
            alerts.append("📋 任务已取消")

        # ═══════════════════════════════════════════
        #  11. 罚款事件
        # ═══════════════════════════════════════════
        fined = events.get("fined", False)
        was_fined = last.get("fined", False)
        if fined and not was_fined:
            alerts.append(f"💸 收到罚单！请注意遵守交通规则")

        # ═══════════════════════════════════════════
        #  12. 导航提醒（接近目的地）
        # ═══════════════════════════════════════════
        route_dist = nav.get("route_distance", 0)
        route_time = nav.get("route_time", 0)
        # 距目的地 5km 以内且在任务中
        was_near_dest = last.get("near_destination", False)
        is_near_dest = on_job and 0 < route_dist < 5000 and route_dist > 0
        if is_near_dest and not was_near_dest:
            dst_city = job.get("destination", {}).get("city", "目的地")
            alerts.append(f"📍 即将到达 {dst_city}！剩余 {route_dist/1000:.1f} km")
        elif not is_near_dest and was_near_dest:
            pass  # 离开近距范围不报

        # ═══════════════════════════════════════════
        #  更新状态快照
        # ═══════════════════════════════════════════
        self._last_alert_state = {
            "speeding": is_speeding,
            "fuel_warning": is_fuel_warn,
            "adblue_warning": is_adblue_warn,
            "water_warning": is_water_warn,
            "oil_temp_warning": is_oil_temp_warn,
            "brake_temp_warning": is_brake_temp_warn,
            "air_warning": is_air_warn,
            "oil_press_warning": is_oil_press_warn,
            "engine_on": engine_on,
            "on_job": on_job,
            "job_delivered": job_delivered,
            "job_cancelled": job_cancelled,
            "fined": fined,
            "near_destination": is_near_dest,
        }

        # 推送所有触发的警报
        for alert_msg in alerts:
            self.push_message(
                source="scs_telemetry",
                message_type="text",
                description="SCS 状态警报",
                priority=2,
                content=alert_msg,
            )

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
        """获取当前完整遥测数据（直接返回缓存，无阻塞）"""
        if not self.telemetry_reader:
            return Err(SdkError("遥测读取器未初始化，游戏可能未运行"))
        data = self._cached_data
        if data:
            return Ok({"data": data})
        else:
            return Err(SdkError("未获取到遥测数据（SDK 未激活或游戏暂停）"))

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
        """获取车辆关键状态摘要（直接返回缓存）"""
        if not self.telemetry_reader:
            return Err(SdkError("遥测读取器未初始化，游戏可能未运行"))
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
        """获取导航信息（直接返回缓存）"""
        if not self.telemetry_reader:
            return Err(SdkError("遥测读取器未初始化，游戏可能未运行"))
        data = self._cached_data
        if not data:
            return Err(SdkError("未获取到导航数据"))

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
