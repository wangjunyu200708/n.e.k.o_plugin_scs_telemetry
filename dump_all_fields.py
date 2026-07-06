"""
全字段遥测数据 Dump 测试
读取 SCSTelemetry 共享内存的每一个字段并打印

用法: python dump_all_fields.py
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(__file__))
from scs_telemetry import SCSTelemetryReader


def fmt(val, max_len=60):
    """格式化值为可读字符串"""
    if val is None:
        return "None"
    if isinstance(val, float):
        return f"{val:.4f}"
    if isinstance(val, bool):
        return "true" if val else "false"
    s = str(val)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def dump_section(name, data, indent=0):
    """递归打印数据字段"""
    pad = "  " * indent
    if isinstance(data, dict):
        print(f"{pad}{name}:")
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                dump_section(k, v, indent + 1)
            else:
                print(f"  {pad}  {k}: {fmt(v)}")
    elif isinstance(data, list):
        print(f"{pad}{name}: [")
        for i, item in enumerate(data):
            if isinstance(item, (dict, list)):
                dump_section(f"[{i}]", item, indent + 1)
            else:
                print(f"  {pad}  [{i}]: {fmt(item)}")
        print(f"{pad}]")
    else:
        print(f"{pad}{name}: {fmt(data)}")


def main():
    print("=" * 70)
    print("  SCS Telemetry 全字段数据 Dump")
    print("=" * 70)

    reader = SCSTelemetryReader()
    print(f"\n[+] 共享内存连接成功: view={hex(reader._map_view)}")

    data = reader.read_data()
    if data is None:
        print("\n[-] read_data() 返回 None (sdk_active=False)")
        print("   请确认已进入驾驶模式")
        reader.close()
        return

    print(f"\n[+] 共 {_count_keys(data)} 个字段\n")

    # 按分组打印
    dump_section("version", data.get("version", {}))
    print()

    common = data.get("common", {})
    dump_section("common", common)
    print()

    truck = data.get("truck", {})
    dump_section("truck.dashboard", truck.get("dashboard", {}))
    dump_section("truck.gears", truck.get("gears", {}))
    dump_section("truck.engine", truck.get("engine", {}))
    dump_section("truck.brakes", truck.get("brakes", {}))
    dump_section("truck.lights", truck.get("lights", {}))
    print(f"  truck.wipers: {fmt(truck.get('wipers'))}")
    print(f"  truck.cruise_control: {fmt(truck.get('cruise_control'))}")
    dump_section("truck.damage", truck.get("damage", {}))
    dump_section("truck.identity", truck.get("identity", {}))
    dump_section("truck.position", truck.get("position", {}))
    dump_section("truck.wheels", truck.get("wheels", {}))
    print()

    dump_section("navigation", data.get("navigation", {}))
    print()
    dump_section("controls", data.get("controls", {}))
    print()
    dump_section("special_events", data.get("special_events", {}))
    print()
    dump_section("job", data.get("job", {}))
    print()

    # 原始bytes统计
    print("-" * 70)
    print(f"  字段总数: {_count_keys(data)}")
    print(f"  SDK Active: {data.get('sdk_active')}")

    reader.close()
    print("=" * 70)
    print("  Dump 完成")
    print("=" * 70)


def _count_keys(d):
    """递归统计字典中的叶子节点数"""
    count = 0
    for v in d.values():
        if isinstance(v, dict):
            count += _count_keys(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    count += _count_keys(item)
                else:
                    count += 1
        else:
            count += 1
    return count


if __name__ == "__main__":
    main()
