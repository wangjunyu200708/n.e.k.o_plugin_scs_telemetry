import ctypes
import struct
from typing import Optional, Dict, Any

# ── Windows API 常量 ──
FILE_MAP_READ = 0x0004

# ── SCS SDK 常量 ──
STRINGSIZE = 64
WHEEL_SIZE = 14
SUBSTANCE_SIZE = 25
SCS_PLUGIN_MMF_SIZE = 32 * 1024  # 32768 bytes


# ═══════════════════════════════════════════════════════════════
#  ctypes 结构体定义 —— 对应 scs-telemetry-common.hpp
#  按偏移量 Zone 分块，用 padding 对齐
# ═══════════════════════════════════════════════════════════════

class _TrailerConstantsBools(ctypes.Structure):
    _fields_ = [
        ("wheelSteerable", ctypes.c_bool * 16),
        ("wheelSimulated", ctypes.c_bool * 16),
        ("wheelPowered",   ctypes.c_bool * 16),
        ("wheelLiftable",  ctypes.c_bool * 16),
    ]

class _TrailerCommonBools(ctypes.Structure):
    _fields_ = [
        ("wheelOnGround", ctypes.c_bool * 16),
        ("attached",      ctypes.c_bool),
    ]

class _TrailerCommonUI(ctypes.Structure):
    _fields_ = [
        ("wheelSubstance", ctypes.c_uint * 16),
    ]

class _TrailerConfigUI(ctypes.Structure):
    _fields_ = [
        ("wheelCount", ctypes.c_uint),
    ]

class _TrailerCommonFloats(ctypes.Structure):
    _fields_ = [
        ("cargoDamage",        ctypes.c_float),
        ("wearChassis",        ctypes.c_float),
        ("wearWheels",         ctypes.c_float),
        ("wearBody",           ctypes.c_float),
        ("wheelSuspDeflection", ctypes.c_float * 16),
        ("wheelVelocity",      ctypes.c_float * 16),
        ("wheelSteering",      ctypes.c_float * 16),
        ("wheelRotation",      ctypes.c_float * 16),
        ("wheelLift",          ctypes.c_float * 16),
        ("wheelLiftOffset",    ctypes.c_float * 16),
    ]

class _TrailerConfigFloats(ctypes.Structure):
    _fields_ = [
        ("wheelRadius", ctypes.c_float * 16),
    ]

class _TrailerCommonFV(ctypes.Structure):
    _fields_ = [
        ("linearVelocityX",  ctypes.c_float),
        ("linearVelocityY",  ctypes.c_float),
        ("linearVelocityZ",  ctypes.c_float),
        ("angularVelocityX", ctypes.c_float),
        ("angularVelocityY", ctypes.c_float),
        ("angularVelocityZ", ctypes.c_float),
        ("linearAccelerationX", ctypes.c_float),
        ("linearAccelerationY", ctypes.c_float),
        ("linearAccelerationZ", ctypes.c_float),
        ("angularAccelerationX", ctypes.c_float),
        ("angularAccelerationY", ctypes.c_float),
        ("angularAccelerationZ", ctypes.c_float),
    ]

class _TrailerConfigFV(ctypes.Structure):
    _fields_ = [
        ("hookPositionX",   ctypes.c_float),
        ("hookPositionY",   ctypes.c_float),
        ("hookPositionZ",   ctypes.c_float),
        ("wheelPositionX",  ctypes.c_float * 16),
        ("wheelPositionY",  ctypes.c_float * 16),
        ("wheelPositionZ",  ctypes.c_float * 16),
    ]

class _TrailerCommonDP(ctypes.Structure):
    _fields_ = [
        ("worldX",     ctypes.c_double),
        ("worldY",     ctypes.c_double),
        ("worldZ",     ctypes.c_double),
        ("rotationX",  ctypes.c_double),
        ("rotationY",  ctypes.c_double),
        ("rotationZ",  ctypes.c_double),
    ]

class _TrailerConfigStrings(ctypes.Structure):
    _fields_ = [
        ("id",                     ctypes.c_char * STRINGSIZE),
        ("cargoAccessoryId",       ctypes.c_char * STRINGSIZE),
        ("bodyType",               ctypes.c_char * STRINGSIZE),
        ("brandId",                ctypes.c_char * STRINGSIZE),
        ("brand",                  ctypes.c_char * STRINGSIZE),
        ("name",                   ctypes.c_char * STRINGSIZE),
        ("chainType",              ctypes.c_char * STRINGSIZE),
        ("licensePlate",           ctypes.c_char * STRINGSIZE),
        ("licensePlateCountry",    ctypes.c_char * STRINGSIZE),
        ("licensePlateCountryId",  ctypes.c_char * STRINGSIZE),
    ]


class scsTrailer_t(ctypes.Structure):
    """拖车结构体 (1560 bytes)"""
    _fields_ = [
        ("con_b",   _TrailerConstantsBools),   # offset 0
        ("com_b",   _TrailerCommonBools),       # +65
        ("buffer_b", ctypes.c_char * 3),        # +83 → 84 对齐
        ("com_ui",  _TrailerCommonUI),          # offset 84
        ("con_ui",  _TrailerConfigUI),          # +148
        # padding to 152
        ("com_f",   _TrailerCommonFloats),      # offset 152
        ("con_f",   _TrailerConfigFloats),      # offset 616
        ("com_fv",  _TrailerCommonFV),          # offset 872
        ("con_fv",  _TrailerConfigFV),          # +920
        ("buffer_fv", ctypes.c_char * 4),
        ("com_dp",  _TrailerCommonDP),          # offset 920+
        ("con_s",   _TrailerConfigStrings),     # offset 920+96+
    ]


# ── 主遥测结构体 ──

class _ScsValues(ctypes.Structure):
    _fields_ = [
        ("telemetry_plugin_revision", ctypes.c_uint),
        ("version_major",             ctypes.c_uint),
        ("version_minor",             ctypes.c_uint),
        ("game",                      ctypes.c_uint),
        ("telemetry_version_game_major", ctypes.c_uint),
        ("telemetry_version_game_minor", ctypes.c_uint),
    ]

class _CommonUI(ctypes.Structure):
    _fields_ = [("time_abs", ctypes.c_uint)]

class _ConfigUI(ctypes.Structure):
    _fields_ = [
        ("gears",              ctypes.c_uint),
        ("gears_reverse",      ctypes.c_uint),
        ("retarderStepCount",  ctypes.c_uint),
        ("truckWheelCount",    ctypes.c_uint),
        ("selectorCount",      ctypes.c_uint),
        ("time_abs_delivery",  ctypes.c_uint),
        ("maxTrailerCount",    ctypes.c_uint),
        ("unitCount",          ctypes.c_uint),
        ("plannedDistanceKm",  ctypes.c_uint),
    ]

class _TruckUI(ctypes.Structure):
    _fields_ = [
        ("shifterSlot",       ctypes.c_uint),
        ("retarderBrake",     ctypes.c_uint),
        ("lightsAuxFront",    ctypes.c_uint),
        ("lightsAuxRoof",     ctypes.c_uint),
        ("truck_wheelSubstance", ctypes.c_uint * 16),
        ("hshifterPosition",  ctypes.c_uint * 32),
        ("hshifterBitmask",   ctypes.c_uint * 32),
    ]

class _GameplayUI(ctypes.Structure):
    _fields_ = [
        ("jobDeliveredDeliveryTime", ctypes.c_uint),
        ("jobStartingTime",          ctypes.c_uint),
        ("jobFinishedTime",          ctypes.c_uint),
    ]

class _CommonI(ctypes.Structure):
    _fields_ = [("restStop", ctypes.c_int)]

class _TruckI(ctypes.Structure):
    _fields_ = [
        ("gear",               ctypes.c_int),
        ("gearDashboard",      ctypes.c_int),
        ("hshifterResulting",  ctypes.c_int * 32),
    ]

class _GameplayI(ctypes.Structure):
    _fields_ = [("jobDeliveredEarnedXp", ctypes.c_int)]

class _ConfigFloats(ctypes.Structure):
    _fields_ = [
        ("fuelCapacity",          ctypes.c_float),
        ("fuelWarningFactor",     ctypes.c_float),
        ("adblueCapacity",        ctypes.c_float),
        ("adblueWarningFactor",   ctypes.c_float),
        ("airPressureWarning",    ctypes.c_float),
        ("airPressurEmergency",   ctypes.c_float),
        ("oilPressureWarning",    ctypes.c_float),
        ("waterTemperatureWarning", ctypes.c_float),
        ("batteryVoltageWarning", ctypes.c_float),
        ("engineRpmMax",          ctypes.c_float),
        ("gearDifferential",      ctypes.c_float),
        ("cargoMass",             ctypes.c_float),
        ("truckWheelRadius",      ctypes.c_float * 16),
        ("gearRatiosForward",     ctypes.c_float * 24),
        ("gearRatiosReverse",     ctypes.c_float * 8),
        ("unitMass",              ctypes.c_float),
    ]

class _TruckFloats(ctypes.Structure):
    _fields_ = [
        ("speed",                  ctypes.c_float),
        ("engineRpm",              ctypes.c_float),
        ("userSteer",              ctypes.c_float),
        ("userThrottle",           ctypes.c_float),
        ("userBrake",              ctypes.c_float),
        ("userClutch",             ctypes.c_float),
        ("gameSteer",              ctypes.c_float),
        ("gameThrottle",           ctypes.c_float),
        ("gameBrake",              ctypes.c_float),
        ("gameClutch",             ctypes.c_float),
        ("cruiseControlSpeed",     ctypes.c_float),
        ("airPressure",            ctypes.c_float),
        ("brakeTemperature",       ctypes.c_float),
        ("fuel",                   ctypes.c_float),
        ("fuelAvgConsumption",     ctypes.c_float),
        ("fuelRange",              ctypes.c_float),
        ("adblue",                 ctypes.c_float),
        ("oilPressure",            ctypes.c_float),
        ("oilTemperature",         ctypes.c_float),
        ("waterTemperature",       ctypes.c_float),
        ("batteryVoltage",         ctypes.c_float),
        ("lightsDashboard",        ctypes.c_float),
        ("wearEngine",             ctypes.c_float),
        ("wearTransmission",       ctypes.c_float),
        ("wearCabin",              ctypes.c_float),
        ("wearChassis",            ctypes.c_float),
        ("wearWheels",             ctypes.c_float),
        ("truckOdometer",          ctypes.c_float),
        ("routeDistance",           ctypes.c_float),
        ("routeTime",              ctypes.c_float),
        ("speedLimit",             ctypes.c_float),
        ("truck_wheelSuspDeflection", ctypes.c_float * 16),
        ("truck_wheelVelocity",    ctypes.c_float * 16),
        ("truck_wheelSteering",    ctypes.c_float * 16),
        ("truck_wheelRotation",    ctypes.c_float * 16),
        ("truck_wheelLift",        ctypes.c_float * 16),
        ("truck_wheelLiftOffset",  ctypes.c_float * 16),
    ]

class _GameplayFloats(ctypes.Structure):
    _fields_ = [
        ("jobDeliveredCargoDamage", ctypes.c_float),
        ("jobDeliveredDistanceKm",  ctypes.c_float),
        ("refuelAmount",            ctypes.c_float),
    ]

class _JobFloats(ctypes.Structure):
    _fields_ = [("cargoDamage", ctypes.c_float)]

class _ConfigBools(ctypes.Structure):
    _fields_ = [
        ("truckWheelSteerable",  ctypes.c_bool * 16),
        ("truckWheelSimulated",  ctypes.c_bool * 16),
        ("truckWheelPowered",    ctypes.c_bool * 16),
        ("truckWheelLiftable",   ctypes.c_bool * 16),
        ("isCargoLoaded",        ctypes.c_bool),
        ("specialJob",           ctypes.c_bool),
    ]

class _TruckBools(ctypes.Structure):
    _fields_ = [
        ("parkBrake",              ctypes.c_bool),
        ("motorBrake",             ctypes.c_bool),
        ("airPressureWarning",     ctypes.c_bool),
        ("airPressureEmergency",   ctypes.c_bool),
        ("fuelWarning",            ctypes.c_bool),
        ("adblueWarning",          ctypes.c_bool),
        ("oilPressureWarning",     ctypes.c_bool),
        ("waterTemperatureWarning", ctypes.c_bool),
        ("batteryVoltageWarning",  ctypes.c_bool),
        ("electricEnabled",        ctypes.c_bool),
        ("engineEnabled",          ctypes.c_bool),
        ("wipers",                 ctypes.c_bool),
        ("blinkerLeftActive",      ctypes.c_bool),
        ("blinkerRightActive",     ctypes.c_bool),
        ("blinkerLeftOn",          ctypes.c_bool),
        ("blinkerRightOn",         ctypes.c_bool),
        ("lightsParking",          ctypes.c_bool),
        ("lightsBeamLow",          ctypes.c_bool),
        ("lightsBeamHigh",         ctypes.c_bool),
        ("lightsBeacon",           ctypes.c_bool),
        ("lightsBrake",            ctypes.c_bool),
        ("lightsReverse",          ctypes.c_bool),
        ("lightsHazard",           ctypes.c_bool),
        ("cruiseControl",          ctypes.c_bool),
        ("truck_wheelOnGround",    ctypes.c_bool * 16),
        ("shifterToggle",          ctypes.c_bool * 2),
        ("differentialLock",       ctypes.c_bool),
        ("liftAxle",               ctypes.c_bool),
        ("liftAxleIndicator",      ctypes.c_bool),
        ("trailerLiftAxle",        ctypes.c_bool),
        ("trailerLiftAxleIndicator", ctypes.c_bool),
    ]

class _GameplayBools(ctypes.Structure):
    _fields_ = [
        ("jobDeliveredAutoparkUsed", ctypes.c_bool),
        ("jobDeliveredAutoloadUsed", ctypes.c_bool),
    ]

class _ConfigFV(ctypes.Structure):
    _fields_ = [
        ("cabinPositionX",  ctypes.c_float),
        ("cabinPositionY",  ctypes.c_float),
        ("cabinPositionZ",  ctypes.c_float),
        ("headPositionX",   ctypes.c_float),
        ("headPositionY",   ctypes.c_float),
        ("headPositionZ",   ctypes.c_float),
        ("truckHookPositionX", ctypes.c_float),
        ("truckHookPositionY", ctypes.c_float),
        ("truckHookPositionZ", ctypes.c_float),
        ("truckWheelPositionX", ctypes.c_float * 16),
        ("truckWheelPositionY", ctypes.c_float * 16),
        ("truckWheelPositionZ", ctypes.c_float * 16),
    ]

class _TruckFV(ctypes.Structure):
    _fields_ = [
        ("lv_accelerationX",  ctypes.c_float),
        ("lv_accelerationY",  ctypes.c_float),
        ("lv_accelerationZ",  ctypes.c_float),
        ("av_accelerationX",  ctypes.c_float),
        ("av_accelerationY",  ctypes.c_float),
        ("av_accelerationZ",  ctypes.c_float),
        ("accelerationX",     ctypes.c_float),
        ("accelerationY",     ctypes.c_float),
        ("accelerationZ",     ctypes.c_float),
        ("aa_accelerationX",  ctypes.c_float),
        ("aa_accelerationY",  ctypes.c_float),
        ("aa_accelerationZ",  ctypes.c_float),
        ("cabinAVX",          ctypes.c_float),
        ("cabinAVY",          ctypes.c_float),
        ("cabinAVZ",          ctypes.c_float),
        ("cabinAAX",          ctypes.c_float),
        ("cabinAAY",          ctypes.c_float),
        ("cabinAAZ",          ctypes.c_float),
    ]

class _TruckFP(ctypes.Structure):
    _fields_ = [
        ("cabinOffsetX",          ctypes.c_float),
        ("cabinOffsetY",          ctypes.c_float),
        ("cabinOffsetZ",          ctypes.c_float),
        ("cabinOffsetrotationX",  ctypes.c_float),
        ("cabinOffsetrotationY",  ctypes.c_float),
        ("cabinOffsetrotationZ",  ctypes.c_float),
        ("headOffsetX",           ctypes.c_float),
        ("headOffsetY",           ctypes.c_float),
        ("headOffsetZ",          ctypes.c_float),
        ("headOffsetrotationX",  ctypes.c_float),
        ("headOffsetrotationY",  ctypes.c_float),
        ("headOffsetrotationZ",  ctypes.c_float),
    ]

class _TruckDP(ctypes.Structure):
    _fields_ = [
        ("coordinateX", ctypes.c_double),
        ("coordinateY", ctypes.c_double),
        ("coordinateZ", ctypes.c_double),
        ("rotationX",   ctypes.c_double),
        ("rotationY",   ctypes.c_double),
        ("rotationZ",   ctypes.c_double),
    ]

class _ConfigStrings(ctypes.Structure):
    _fields_ = [
        ("truckBrandId",              ctypes.c_char * STRINGSIZE),
        ("truckBrand",                ctypes.c_char * STRINGSIZE),
        ("truckId",                   ctypes.c_char * STRINGSIZE),
        ("truckName",                 ctypes.c_char * STRINGSIZE),
        ("cargoId",                   ctypes.c_char * STRINGSIZE),
        ("cargo",                     ctypes.c_char * STRINGSIZE),
        ("cityDstId",                 ctypes.c_char * STRINGSIZE),
        ("cityDst",                   ctypes.c_char * STRINGSIZE),
        ("compDstId",                 ctypes.c_char * STRINGSIZE),
        ("compDst",                   ctypes.c_char * STRINGSIZE),
        ("citySrcId",                 ctypes.c_char * STRINGSIZE),
        ("citySrc",                   ctypes.c_char * STRINGSIZE),
        ("compSrcId",                 ctypes.c_char * STRINGSIZE),
        ("compSrc",                   ctypes.c_char * STRINGSIZE),
        ("shifterType",               ctypes.c_char * 16),
        ("truckLicensePlate",         ctypes.c_char * STRINGSIZE),
        ("truckLicensePlateCountryId", ctypes.c_char * STRINGSIZE),
        ("truckLicensePlateCountry",  ctypes.c_char * STRINGSIZE),
        ("jobMarket",                 ctypes.c_char * 32),
    ]

class _GameplayStrings(ctypes.Structure):
    _fields_ = [
        ("fineOffence",      ctypes.c_char * 32),
        ("ferrySourceName",  ctypes.c_char * STRINGSIZE),
        ("ferryTargetName",  ctypes.c_char * STRINGSIZE),
        ("ferrySourceId",    ctypes.c_char * STRINGSIZE),
        ("ferryTargetId",    ctypes.c_char * STRINGSIZE),
        ("trainSourceName",  ctypes.c_char * STRINGSIZE),
        ("trainTargetName",  ctypes.c_char * STRINGSIZE),
        ("trainSourceId",    ctypes.c_char * STRINGSIZE),
        ("trainTargetId",    ctypes.c_char * STRINGSIZE),
    ]

class _ConfigULL(ctypes.Structure):
    _fields_ = [("jobIncome", ctypes.c_uint64)]

class _GameplayLL(ctypes.Structure):
    _fields_ = [
        ("jobCancelledPenalty",  ctypes.c_int64),
        ("jobDeliveredRevenue",  ctypes.c_int64),
        ("fineAmount",           ctypes.c_int64),
        ("tollgatePayAmount",    ctypes.c_int64),
        ("ferryPayAmount",       ctypes.c_int64),
        ("trainPayAmount",       ctypes.c_int64),
    ]

class _SpecialBools(ctypes.Structure):
    _fields_ = [
        ("onJob",       ctypes.c_bool),
        ("jobFinished", ctypes.c_bool),
        ("jobCancelled", ctypes.c_bool),
        ("jobDelivered", ctypes.c_bool),
        ("fined",       ctypes.c_bool),
        ("tollgate",    ctypes.c_bool),
        ("ferry",       ctypes.c_bool),
        ("train",       ctypes.c_bool),
        ("refuel",      ctypes.c_bool),
        ("refuelPayed", ctypes.c_bool),
    ]

class _Substances(ctypes.Structure):
    _fields_ = [
        ("substance", ctypes.c_char * (SUBSTANCE_SIZE * STRINGSIZE)),
    ]

class _Trailers(ctypes.Structure):
    _fields_ = [("trailer", scsTrailer_t * 10)]


# ── 主结构体：按 Zone 偏移量用 padding 对齐 ──

class scsTelemetryMap_t(ctypes.Structure):
    """SCS 遥测共享内存完整结构体 (V1.12.1, ~21620 bytes)"""
    _fields_ = [
        # ── Zone 1: bool + timestamps (offset 0-39) ──
        ("sdkActive",    ctypes.c_bool),
        ("placeHolder",  ctypes.c_char * 3),
        ("paused",       ctypes.c_bool),
        ("placeHolder2", ctypes.c_char * 3),
        ("time",                ctypes.c_uint64),
        ("simulatedTime",       ctypes.c_uint64),
        ("renderTime",          ctypes.c_uint64),
        ("multiplayerTimeOffset", ctypes.c_int64),

        # ── Zone 2: unsigned int (offset 40-499) ──
        ("scs_values",    _ScsValues),
        ("common_ui",     _CommonUI),
        ("config_ui",     _ConfigUI),
        ("truck_ui",      _TruckUI),
        ("gameplay_ui",   _GameplayUI),
        ("buffer_ui",     ctypes.c_char * 48),

        # ── Zone 3: int (offset 500-699) ──
        ("common_i",      _CommonI),
        ("truck_i",       _TruckI),
        ("gameplay_i",    _GameplayI),
        ("buffer_i",      ctypes.c_char * 56),

        # ── Zone 4: float (offset 700-1499) ──
        ("common_f",      ctypes.c_float),       # scale
        ("config_f",      _ConfigFloats),
        ("truck_f",       _TruckFloats),
        ("gameplay_f",    _GameplayFloats),
        ("job_f",         _JobFloats),
        ("buffer_f",      ctypes.c_char * 28),

        # ── Zone 5: bool (offset 1500-1639) ──
        ("config_b",      _ConfigBools),
        ("truck_b",       _TruckBools),
        ("gameplay_b",    _GameplayBools),
        ("buffer_b",      ctypes.c_char * 25),

        # ── Zone 6: fvector (offset 1640-1999) ──
        ("config_fv",     _ConfigFV),
        ("truck_fv",      _TruckFV),
        ("buffer_fv",     ctypes.c_char * 60),

        # ── Zone 7: fplacement (offset 2000-2199) ──
        ("truck_fp",      _TruckFP),
        ("buffer_fp",     ctypes.c_char * 152),

        # ── Zone 8: dplacement (offset 2200-2299) ──
        ("truck_dp",      _TruckDP),
        ("buffer_dp",     ctypes.c_char * 52),

        # ── Zone 9: strings (offset 2300-3999) ──
        ("config_s",      _ConfigStrings),
        ("gameplay_s",    _GameplayStrings),
        ("buffer_s",      ctypes.c_char * 20),

        # ── Zone 10: unsigned long long (offset 4000-4199) ──
        ("config_ull",    _ConfigULL),
        ("buffer_ull",    ctypes.c_char * 192),

        # ── Zone 11: long long (offset 4200-4299) ──
        ("gameplay_ll",   _GameplayLL),
        ("buffer_ll",     ctypes.c_char * 52),

        # ── Zone 12: special events (offset 4300-4399) ──
        ("special_b",     _SpecialBools),
        ("buffer_special", ctypes.c_char * 90),

        # ── Zone 13: substances (offset 4400-5999) ──
        ("substances",    _Substances),

        # ── Zone 14: trailers (offset 6000-21619) ──
        ("trailer_zone",  _Trailers),
    ]


# ═══════════════════════════════════════════════════════════════
#  读取器
# ═══════════════════════════════════════════════════════════════

class SCSTelemetryReader:
    """SCS 遥测数据读取器（使用 ctypes + Win32 API 读取命名共享内存）"""

    def __init__(self):
        self.memory_map_name = "Local\\SCSTelemetry"
        self._map_handle = None
        self._map_view = None
        self._map_size = SCS_PLUGIN_MMF_SIZE
        self._open_memory_map()

    def _open_memory_map(self):
        """打开 Windows 命名共享内存"""
        kernel32 = ctypes.windll.kernel32

        handle = kernel32.OpenFileMappingW(
            FILE_MAP_READ,
            False,
            self.memory_map_name
        )
        if not handle:
            err = kernel32.GetLastError()
            raise Exception(
                f"无法打开内存映射文件 '{self.memory_map_name}'，"
                f"GetLastError={err}（游戏未运行或 scs-sdk-plugin 未加载？）"
            )

        view = kernel32.MapViewOfFile(handle, FILE_MAP_READ, 0, 0, self._map_size)
        if not view:
            err = kernel32.GetLastError()
            kernel32.CloseHandle(handle)
            raise Exception(f"MapViewOfFile 失败，GetLastError={err}")

        self._map_handle = handle
        self._map_view = view

    def _get_struct(self) -> scsTelemetryMap_t:
        """将共享内存映射为 scsTelemetryMap_t 结构体"""
        return scsTelemetryMap_t.from_address(self._map_view)

    @staticmethod
    def _decode_bytes(raw: bytes) -> str:
        """解码 c_char 字段，去掉尾部 \\x00"""
        return raw.split(b'\x00', 1)[0].decode('utf-8', errors='replace')

    def read_data(self) -> Optional[Dict[str, Any]]:
        """读取完整遥测数据，返回字典"""
        if not self._map_view:
            return None

        try:
            s = self._get_struct()

            # 检查 SDK 是否激活
            if not s.sdkActive:
                return None

            data = {
                "sdk_active": s.sdkActive,
                "paused": s.paused,
                "time": s.time,
                "simulated_time": s.simulatedTime,
                "render_time": s.renderTime,

                "version": {
                    "plugin_revision": s.scs_values.telemetry_plugin_revision,
                    "game_major": s.scs_values.version_major,
                    "game_minor": s.scs_values.version_minor,
                    "game_id": s.scs_values.game,
                    "game": "ETS2" if s.scs_values.game == 1 else "ATS" if s.scs_values.game == 2 else "Unknown",
                    "telemetry_major": s.scs_values.telemetry_version_game_major,
                    "telemetry_minor": s.scs_values.telemetry_version_game_minor,
                },

                "common": {
                    "scale": s.common_f,
                    "game_time_minutes": s.common_ui.time_abs,
                    "rest_stop": s.common_i.restStop,
                },

                "truck": {
                    "dashboard": {
                        "speed": s.truck_f.speed,
                        "rpm": s.truck_f.engineRpm,
                        "cruise_control_speed": s.truck_f.cruiseControlSpeed,
                        "odometer": s.truck_f.truckOdometer,
                        "fuel": {
                            "amount": s.truck_f.fuel,
                            "average_consumption": s.truck_f.fuelAvgConsumption,
                            "range": s.truck_f.fuelRange,
                            "capacity": s.config_f.fuelCapacity,
                            "warning_factor": s.config_f.fuelWarningFactor,
                        },
                        "adblue": {
                            "amount": s.truck_f.adblue,
                            "capacity": s.config_f.adblueCapacity,
                        },
                        "temperature": {
                            "water": s.truck_f.waterTemperature,
                            "oil": s.truck_f.oilTemperature,
                        },
                        "pressure": {
                            "oil": s.truck_f.oilPressure,
                            "air": s.truck_f.airPressure,
                            "brake_temperature": s.truck_f.brakeTemperature,
                        },
                        "battery_voltage": s.truck_f.batteryVoltage,
                    },
                    "gears": {
                        "current": s.truck_i.gear,
                        "dashboard": s.truck_i.gearDashboard,
                        "forward_count": s.config_ui.gears,
                        "reverse_count": s.config_ui.gears_reverse,
                        "retarder_steps": s.config_ui.rearderStepCount,
                        "shifter_slot": s.truck_ui.shifterSlot,
                        "retarder_brake": s.truck_ui.retarderBrake,
                    },
                    "engine": {
                        "enabled": s.truck_b.engineEnabled,
                        "electric": s.truck_b.electricEnabled,
                        "rpm_max": s.config_f.engineRpmMax,
                    },
                    "brakes": {
                        "parking": s.truck_b.parkBrake,
                        "motor_brake": s.truck_b.motorBrake,
                        "air_pressure_warning": s.truck_b.airPressureWarning,
                        "air_pressure_emergency": s.truck_b.airPressureEmergency,
                    },
                    "lights": {
                        "parking": s.truck_b.lightsParking,
                        "beam_low": s.truck_b.lightsBeamLow,
                        "beam_high": s.truck_b.lightsBeamHigh,
                        "beacon": s.truck_b.lightsBeacon,
                        "brake": s.truck_b.lightsBrake,
                        "reverse": s.truck_b.lightsReverse,
                        "hazard": s.truck_b.lightsHazard,
                        "blinker_left": s.truck_b.blinkerLeftOn,
                        "blinker_right": s.truck_b.blinkerRightOn,
                        "dashboard_backlight": s.truck_f.lightsDashboard,
                        "aux_front": s.truck_ui.lightsAuxFront,
                        "aux_roof": s.truck_ui.lightsAuxRoof,
                    },
                    "wipers": s.truck_b.wipers,
                    "cruise_control": s.truck_b.cruiseControl,
                    "damage": {
                        "engine": s.truck_f.wearEngine,
                        "transmission": s.truck_f.wearTransmission,
                        "cabin": s.truck_f.wearCabin,
                        "chassis": s.truck_f.wearChassis,
                        "wheels": s.truck_f.wearWheels,
                    },
                    "identity": {
                        "brand_id": self._decode_bytes(s.config_s.truckBrandId),
                        "brand": self._decode_bytes(s.config_s.truckBrand),
                        "id": self._decode_bytes(s.config_s.truckId),
                        "name": self._decode_bytes(s.config_s.truckName),
                        "license_plate": self._decode_bytes(s.config_s.truckLicensePlate),
                        "license_plate_country_id": self._decode_bytes(s.config_s.truckLicensePlateCountryId),
                        "license_plate_country": self._decode_bytes(s.config_s.truckLicensePlateCountry),
                    },
                    "wheels": {
                        "count": s.config_ui.truckWheelCount,
                    },
                    "position": {
                        "coordinate_x": s.truck_dp.coordinateX,
                        "coordinate_y": s.truck_dp.coordinateY,
                        "coordinate_z": s.truck_dp.coordinateZ,
                        "rotation_x": s.truck_dp.rotationX,
                        "rotation_y": s.truck_dp.rotationY,
                        "rotation_z": s.truck_dp.rotationZ,
                    },
                },

                "job": {
                    "on_job": s.special_b.onJob,
                    "job_finished": s.special_b.jobFinished,
                    "job_cancelled": s.special_b.jobCancelled,
                    "job_delivered": s.special_b.jobDelivered,
                    "cargo": {
                        "id": self._decode_bytes(s.config_s.cargoId),
                        "name": self._decode_bytes(s.config_s.cargo),
                        "mass": s.config_f.cargoMass,
                        "unit_count": s.config_ui.unitCount,
                        "unit_mass": s.config_f.unitMass,
                        "damage": s.job_f.cargoDamage,
                        "is_loaded": s.config_b.isCargoLoaded,
                        "special": s.config_b.specialJob,
                    },
                    "destination": {
                        "city_id": self._decode_bytes(s.config_s.cityDstId),
                        "city": self._decode_bytes(s.config_s.cityDst),
                        "company_id": self._decode_bytes(s.config_s.compDstId),
                        "company": self._decode_bytes(s.config_s.compDst),
                    },
                    "source": {
                        "city_id": self._decode_bytes(s.config_s.citySrcId),
                        "city": self._decode_bytes(s.config_s.citySrc),
                        "company_id": self._decode_bytes(s.config_s.compSrcId),
                        "company": self._decode_bytes(s.config_s.compSrc),
                    },
                    "income": s.config_ull.jobIncome,
                    "delivery_time": s.config_ui.time_abs_delivery,
                    "planned_distance_km": s.config_ui.plannedDistanceKm,
                    "market": self._decode_bytes(s.config_s.jobMarket),
                },

                "navigation": {
                    "route_distance": s.truck_f.routeDistance,
                    "route_time": s.truck_f.routeTime,
                    "speed_limit": s.truck_f.speedLimit,
                },

                "controls": {
                    "user_steer": s.truck_f.userSteer,
                    "user_throttle": s.truck_f.userThrottle,
                    "user_brake": s.truck_f.userBrake,
                    "user_clutch": s.truck_f.userClutch,
                    "game_steer": s.truck_f.gameSteer,
                    "game_throttle": s.truck_f.gameThrottle,
                    "game_brake": s.truck_f.gameBrake,
                    "game_clutch": s.truck_f.gameClutch,
                },

                "special_events": {
                    "fined": s.special_b.fined,
                    "tollgate": s.special_b.tollgate,
                    "ferry": s.special_b.ferry,
                    "train": s.special_b.train,
                    "refuel": s.special_b.refuel,
                    "refuel_payed": s.special_b.refuelPayed,
                },
            }

            return data

        except Exception:
            raise

    def close(self):
        """释放共享内存映射"""
        kernel32 = ctypes.windll.kernel32
        if self._map_view:
            kernel32.UnmapViewOfFile(self._map_view)
            self._map_view = None
        if self._map_handle:
            kernel32.CloseHandle(self._map_handle)
            self._map_handle = None
