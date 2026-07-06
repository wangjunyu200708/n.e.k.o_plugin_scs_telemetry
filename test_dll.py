"""
SCS SDK 共享内存连通性测试
依赖: scs_telemetry.py (SCSTelemetryReader)

使用方法:
  1. 启动 ETS2 并进入驾驶
  2. python test_dll.py
"""
import sys
import os

# 确保能找到 scs_telemetry.py
sys.path.insert(0, os.path.dirname(__file__))
from scs_telemetry import SCSTelemetryReader


def main():
    print("=" * 56)
    print("  SCS Telemetry 共享内存连通性测试")
    print("=" * 56)

    # 1. 尝试连接共享内存
    print("\n[1/3] 连接共享内存 Local\\SCSTelemetry ...")
    try:
        reader = SCSTelemetryReader()
        print("  ✅ 连接成功")
    except Exception as e:
        print(f"  ❌ 连接失败: {e}")
        print()
        print("  可能原因:")
        print("    a) ETS2 未运行")
        print("    b) bin/win_x64/plugins/scs-telemetry.dll 未安装")
        print("    c) DLL 与游戏版本 1.60 不兼容")
        print("    d) 游戏启动时 SDK 激活弹窗未点 OK")
        return False

    # 2. 尝试读取数据
    print("\n[2/3] 读取遥测数据 ...")
    try:
        data = reader.read_data()
    except Exception as e:
        print(f"  ❌ 读取失败: {e}")
        reader.close()
        return False

    if data is None:
        print("  ⚠️  read_data() 返回 None")
        print("  原因: sdk_active=False (未进入驾驶模式?)")
        reader.close()
        return False

    print("  ✅ 读取成功")

    # 3. 展示关键字段
    print("\n[3/3] 关键数据摘要:")
    print()

    ver = data.get("version", {})
    print(f"  Game:       {ver.get('game', '?')}  v{ver.get('game_major', '?')}.{ver.get('game_minor', '?')}")
    print(f"  SDK Rev:    {ver.get('plugin_revision', '?')}")

    truck = data.get("truck", {})
    dash = truck.get("dashboard", {})
    nav = data.get("navigation", {})
    job = data.get("job", {})

    speed_ms = dash.get("speed", 0)
    speed_kmh = speed_ms * 3.6
    limit_ms = nav.get("speed_limit", 0)
    limit_kmh = limit_ms * 3.6 if limit_ms > 0 else 0
    rpm = dash.get("rpm", 0)
    gear = truck.get("gears", {}).get("dashboard", 0)
    fuel = dash.get("fuel", {})
    fuel_pct = (fuel.get("amount", 0) / fuel.get("capacity", 1)) * 100 if fuel.get("capacity", 0) > 0 else 0

    # 速度
    print(f"\n  🏎️  车速:       {speed_kmh:.0f} km/h")
    print(f"  ⚙️  转速:       {rpm:.0f} RPM")
    print(f"  🔢 档位:       {gear}")
    if limit_kmh > 0:
        print(f"  🚦 限速:       {limit_kmh:.0f} km/h{' ⚠️ 超速!' if speed_kmh > limit_kmh else ''}")

    # 油量
    fuel_amount = fuel.get("amount", 0)
    fuel_cap = fuel.get("capacity", 0)
    fuel_range = fuel.get("range", 0)
    print(f"  ⛽ 油量:       {fuel_amount:.0f}/{fuel_cap:.0f} L ({fuel_pct:.0f}%)")
    print(f"  📏 续航:       {fuel_range:.0f} km")

    # 温度
    temp = dash.get("temperature", {})
    wt = temp.get("water", 0)
    ot = temp.get("oil", 0)
    print(f"  🌡️  水温:       {wt:.0f} °C")
    print(f"  🌡️  油温:       {ot:.0f} °C")

    # 导航
    route_dist_m = nav.get("route_distance", 0)
    route_time_s = nav.get("route_time", 0)
    if route_dist_m > 0:
        print(f"  🗺️  剩余路程:   {route_dist_m/1000:.0f} km")
        print(f"  ⏱️  预计时间:   {route_time_s/60:.0f} min")
        dst = job.get("destination", {}).get("city", "")
        if dst:
            print(f"  🎯 目的地:    {dst}")

    # 任务
    if job.get("on_job", False):
        cargo = job.get("cargo", {}).get("name", "?")
        dst_city = job.get("destination", {}).get("city", "?")
        inc = (job.get("income", 0) or 0) / 100
        print(f"  📦 货物:       {cargo} → {dst_city}")
        print(f"  💰 预计收入:   ¥{inc:,.0f}")

    # 发动机
    eng = truck.get("engine", {})
    print(f"  🔑 发动机:     {'运行中' if eng.get('enabled') else '已熄火'}")

    # 灯光摘要
    lights = truck.get("lights", {})
    light_on = [k for k, v in lights.items() if v and k not in ('dashboard_backlight', 'aux_front', 'aux_roof')]
    if light_on:
        print(f"  💡 灯光:       {', '.join(light_on)}")

    # 损坏
    dmg = truck.get("damage", {})
    dmg_items = {k: v for k, v in dmg.items() if v and v > 0}
    if dmg_items:
        print(f"  🔧 损坏:       {', '.join(f'{k}={v*100:.0f}%' for k, v in dmg_items.items())}")
    else:
        print(f"  ✅ 车况:       完好")

    print()
    print("=" * 56)
    print("  🎉 测试通过! 共享内存读写正常, DLL 工作良好")
    print("=" * 56)

    reader.close()
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
