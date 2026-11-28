"""Best-effort reading of GPU and CPU temperatures and loads (never raises).

GPU: NVIDIA first via `nvidia-smi` (the NVML command line tool), then the
AMD/Intel path via Windows performance counters and WMI CIM (video adapter
names).

CPU: `psutil` sensors when they are exposed; otherwise (Windows, where
psutil returns nothing) the sources in order: WMI LibreHardwareMonitor /
OpenHardwareMonitor, the Thermal Zone performance counters and the
`MSAcpi_ThermalZoneTemperature` WMI class.

Anything that is not available returns `None` instead of raising.
"""

from __future__ import annotations

import ctypes
import json
import logging
import math
import os
import shutil
import struct
import subprocess
import unicodedata
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import psutil

LOG = logging.getLogger(__name__)

_CREATE_NO_WINDOW = 0x08000000

# PowerShell script that reads GPU temperature/load counters. Only counters
# that actually exist are reported (everything else is silently skipped).
_GPU_COUNTER_SCRIPT = """
$out = @()
foreach ($c in @("\\GPU Core Temperature", "\\GPU Temperature")) {
    $s = Get-Counter -ErrorAction SilentlyContinue -Counter $c
    if ($s -and $s.CounterSamples) {
        $v = $s.CounterSamples[0].CookedValue
        if ($v -is [double] -or $v -is [int]) { $out += "TEMP=$v" }
    }
}
foreach ($c in @("\\GPU Core Usage", "\\GPU Usage")) {
    $s = Get-Counter -ErrorAction SilentlyContinue -Counter $c
    if ($s -and $s.CounterSamples) {
        $v = $s.CounterSamples[0].CookedValue
        if ($v -is [double] -or $v -is [int]) { $out += "LOAD=$v" }
    }
}
if ($out.Count -gt 0) { $out } else { Write-Output "" }
"""

_GPU_WMI_CIM_SCRIPT = """
try {
    Get-CimInstance -ClassName Win32_VideoController | ForEach-Object { $_.Name }
} catch { }
"""


@dataclass(frozen=True)
class GpuStats:
    """Snapshot of one GPU reading; fields are None when not available."""

    temp_c: float | None = None
    load_percent: float | None = None
    name: str | None = None


@dataclass(frozen=True)
class CpuStats:
    """Snapshot of one CPU reading; fields are None when not available."""

    temp_c: float | None = None
    load_percent: float | None = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _to_float(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _run_command(args: Sequence[str], *, timeout: float) -> str | None:
    """Runs a command quietly; returns stdout text, or None on any failure."""
    if not args:
        return None
    try:
        if os.path.isabs(str(args[0])):
            # An absolute path (cached tool location) is used as-is.
            if not os.path.isfile(str(args[0])):
                return None
        elif shutil.which(str(args[0])) is None:
            return None
    except OSError:
        return None
    creationflags = _CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        result = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout or ""


def _run_powershell(script: str, *, timeout: float) -> str | None:
    return _run_command(("powershell", "-NoProfile", "-NonInteractive", "-Command", script), timeout=timeout)


# ---------------------------------------------------------------------------
# GPU: NVIDIA via nvidia-smi
# ---------------------------------------------------------------------------


def parse_nvidia_smi_output(text: str) -> GpuStats | None:
    """Parses `nvidia-smi --query-gpu=temperature.gpu,utilization.gpu` output."""
    for line in (part.strip() for part in text.splitlines()):
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",")]
        temp = _to_float(parts[0]) if parts else None
        load = _to_float(parts[1]) if len(parts) > 1 else None
        if temp is None and load is None:
            continue
        return GpuStats(temp_c=temp, load_percent=load)
    return None


# Candidate locations of nvidia-smi.dll's executable (driver installs and the
# standalone NVSMI package). The first existing path is cached for the run.
_NVDIA_SMI_CANDIDATES = (
    r"C:\Windows\System32\nvidia-smi.exe",
    r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
)

# nvidia-smi path: False = not probed yet, None = probed and unavailable, path = usable.
_nvidia_smi_path: bool | str | None = False


def _locate_nvidia_smi() -> str | None:
    """Locate nvidia-smi once and cache the result for the run (None if not found)."""
    global _nvidia_smi_path
    if _nvidia_smi_path is False:
        path = None
        # Prefer the candidates shipped with the driver, then the first hit on PATH.
        for candidate in _NVDIA_SMI_CANDIDATES:
            try:
                if os.path.isfile(candidate):
                    path = candidate
                    break
            except OSError:
                continue
        if path is None:
            try:
                path = shutil.which("nvidia-smi")
            except OSError:
                path = None
        _nvidia_smi_path = path
    if _nvidia_smi_path is None or _nvidia_smi_path is False:
        return None
    return _nvidia_smi_path


def _read_gpu_nvidia_smi() -> GpuStats | None:
    path = _locate_nvidia_smi()
    if path is None:
        return None
    text = _run_command(
        [path, "--query-gpu=temperature.gpu,utilization.gpu", "--format=csv,noheader,nounits"],
        timeout=5.0,
    )
    if text is None:
        return None
    return parse_nvidia_smi_output(text)


# ---------------------------------------------------------------------------
# GPU: AMD/Intel via performance counters and WMI CIM
# ---------------------------------------------------------------------------


def parse_perf_counter_output(text: str) -> GpuStats | None:
    """Parses PowerShell performance counter output (lines like `TEMP=50`)."""
    temp: float | None = None
    load: float | None = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("TEMP="):
            value = _to_float(line[5:])
            if value is not None:
                temp = value
        elif line.startswith("LOAD="):
            value = _to_float(line[5:])
            if value is not None:
                load = value
    if temp is None and load is None:
        return None
    return GpuStats(temp_c=temp, load_percent=load)


def _gpu_via_perf_counters() -> GpuStats | None:
    text = _run_powershell(_GPU_COUNTER_SCRIPT, timeout=8.0)
    if text is None:
        return None
    return parse_perf_counter_output(text)


def _gpu_adapter_name_via_wmi() -> str | None:
    text = _run_powershell(_GPU_WMI_CIM_SCRIPT, timeout=8.0)
    if not text or text.strip() in ("", "null", "[]"):
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return None
    for item in data:
        name = str((item or {}).get("Name") or "").strip()
        if name:
            return name
    return None


def _read_gpu_wmi() -> GpuStats | None:
    """AMD/Intel fallback: performance counters first, then WMI CIM names."""
    stats = _gpu_via_perf_counters()
    name = _gpu_adapter_name_via_wmi()
    if name and stats is None:
        return GpuStats(name=name)
    if name and stats is not None and stats.name is None:
        return GpuStats(temp_c=stats.temp_c, load_percent=stats.load_percent, name=name)
    return stats


def read_gpu_stats() -> GpuStats | None:
    """Best-effort GPU reading; None when no GPU information is available."""
    stats = _read_gpu_nvidia_smi()
    if stats is None:
        stats = _read_gpu_wmi()
    return stats


# ---------------------------------------------------------------------------
# CPU: psutil + Windows sensors
# ---------------------------------------------------------------------------


def _sensor_value(shim: Any) -> float | None:
    value = getattr(shim, "current", None)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def cpu_temp_from_sensors(raw: Mapping[str, Any] | None) -> float | None:
    """Picks the CPU temperature from psutil sensor data (package entry first)."""
    if not isinstance(raw, Mapping) or not raw:
        return None
    preferred: list[float] = []
    others: list[float] = []
    for name, shims in raw.items():
        lowered = str(name).lower()
        if not isinstance(shims, (list, tuple)):
            continue
        for shim in shims:
            value = _sensor_value(shim)
            if value is None:
                continue
            if any(key in lowered for key in ("package", "cpu", "acpi")):
                preferred.append(value)
            else:
                others.append(value)
    values = preferred or others
    if not values:
        return None
    return max(values)


def _read_cpu_temp_psutil() -> float | None:
    """CPU temperature via psutil sensors, or None when unavailable."""
    sensors_fn = getattr(psutil, "sensors_temperatures", None)
    if sensors_fn is None:
        return None
    try:
        raw = sensors_fn()
    except Exception:
        return None
    return cpu_temp_from_sensors(raw)


def read_cpu_temp() -> float | None:
    """CPU temperature: psutil sensors, then Windows sources when they are known to work."""
    temp = _read_cpu_temp_psutil()
    if temp is not None:
        return temp
    if os.name == "nt":
        # Fast in-process shared-memory readers (HWiNFO64 / Core Temp): no subprocess
        # overhead and picked up automatically even if started after the agent.
        for fast_reader in (_read_cpu_temp_hwinfo, _read_cpu_temp_coretemp):
            try:
                temp = fast_reader()
            except Exception:
                temp = None
            if temp is not None:
                return temp

        availability = _cpu_windows_sensors_available
        for key, reader in (
            ("wmi", _read_cpu_temp_windows_wmi),
            ("perf", _read_cpu_temp_from_perf_counters),
            ("acpi", _read_cpu_temp_wmi_acpi),
        ):
            # Once the startup probe found no sensor (or a reader has just
            # missed), skip the expensive PowerShell calls for the rest of
            # the run – fast readers still run above.
            if availability.get(key) is False:
                continue
            try:
                temp = reader()
            except Exception:
                temp = None
            if temp is not None:
                return temp
            if availability.get(key) is None:
                availability[key] = False
    return None


# Which Windows CPU-temperature sources respond, probed once at agent start:
# {"wmi": ..., "perf": ..., "acpi": ...}. Values are True/False when the probe
# ran; None means "not probed" (readers are tried, and a miss is remembered).
# False sources are skipped while playing to avoid spawning PowerShell.
_cpu_windows_sensors_available: dict[str, bool | None] = {"wmi": None, "perf": None, "acpi": None}


def _probe_windows_cpu_sensors() -> dict[str, bool]:
    """Checks once which Windows CPU-temperature sources return a value."""
    availability: dict[str, bool] = {"wmi": False, "perf": False, "acpi": False}
    for key, reader in (
        ("wmi", _read_cpu_temp_windows_wmi),
        ("perf", _read_cpu_temp_from_perf_counters),
        ("acpi", _read_cpu_temp_wmi_acpi),
    ):
        try:
            availability[key] = reader() is not None
        except Exception:
            availability[key] = False
    return availability


_startup_probed = False


def probe_startup_sensors() -> None:
    """Runs the sensor-availability checks once when the agent starts."""
    global _cpu_windows_sensors_available, _startup_probed
    if _startup_probed:
        return
    _startup_probed = True
    try:
        _locate_nvidia_smi()
    except Exception:
        pass
    if os.name == "nt":
        _cpu_windows_sensors_available = _probe_windows_cpu_sensors()


# ---------------------------------------------------------------------------
# CPU: Windows fallbacks (psutil has no sensors on Windows)
# ---------------------------------------------------------------------------

# Name fragments of the CPU temperature sensors we accept from WMI / HWiNFO.
# Matched against accent-folded lowercase labels so Czech HWiNFO64 names
# ("Balíček CPU", "Jádro CPU", "Teplota CPU") work alongside English ones.
# GPU sensors such as "GPU Core Temperature" must not be mistaken for CPU ones.
_CPU_SENSOR_NAME_KEYS = (
    "cpu package",
    "balicek cpu",
    "cpu balicek",
    "pouzdro cpu",
    "cpu pouzdro",
    "teplota balicku",
    "teplota pouzdra",
    "teplota cpu",
    "teploty cpu",
    "jadro cpu",
    "cpu jadro",
    "teplota jadra",
    "teploty jader",
    "max. jadra",
    "maximum jader",
    "prumer jader",
    "tctl/tdie",
    "tdie",
    "tctl",
    "cpu",
    "procesor",
    "core max",
    "core average",
    "core",
    "jadro",
    "ccd",
)

_CPU_HARDWARE_SENSOR_KEYS = (
    "cpu",
    "procesor",
    "ryzen",
    "threadripper",
    "epyc",
    "intel core",
    "core i",
    "core ultra",
    "xeon",
    "pentium",
    "celeron",
)

_NON_CPU_SENSOR_KEYS = (
    "gpu",
    "igpu",
    "grafi",
    "vram",
    "hot spot",
    "hotspot",
    "vrm",
    "mos",
    "ssd",
    "nvme",
    "pch",
    "chipset",
    "cipset",
    "coolant",
    "water",
    "pump",
)

_CPU_WMI_SCRIPT = r"""
$out = @()
function readprop($o, $n) {
    try { $v = $o.$n } catch { $v = $null }
    if ($null -eq $v) { return "" }
    try { return [System.Convert]::ToString($v, [System.Globalization.CultureInfo]::InvariantCulture) } catch { return "" }
}
foreach ($ns in @("root\LibreHardwareMonitor", "root\OpenHardwareMonitor")) {
    foreach ($cn in @("Sensor", "Temperature")) {
        $items = @()
        try { $items = @(Get-CimInstance -Namespace $ns -ClassName $cn -ErrorAction Stop) } catch { $items = @() }
        foreach ($s in $items) {
            if ($null -eq $s) { continue }
            $type = (readprop $s "Type") + " " + (readprop $s "SensorType")
            if (-not $type.ToLower().Contains("temperature")) { continue }
            $name = readprop $s "Name"
            $parent = (readprop $s "Parent") + " " + (readprop $s "Identifier")
            if ($parent -match "amdcpu|intelcpu" -and $name -and -not ($name -match "cpu|tctl|tdie|core|ccd")) {
                $name = "CPU " + $name
            }
            $value = readprop $s "Value"
            if (-not $value) { $value = readprop $s "CurrentTemperature" }
            if ($name -and $value) { $out += ($name + "`t" + $value) }
        }
        if ($out.Count -gt 0) { break }
    }
    if ($out.Count -gt 0) { break }
}
if ($out.Count -gt 0) { $out }
"""

# Language-independent CIM thermal zone query (works without admin on Windows 10/11)
# plus Get-Counter fallback. HighPrecisionTemperature is 0.1 K; Temperature is K.
_CPU_PERF_COUNTER_SCRIPT = r"""$out = @()
try {
    foreach ($z in (Get-CimInstance -Namespace root\cimv2 -ClassName Win32_PerfFormattedData_Counters_ThermalZoneInformation -ErrorAction Stop)) {
        if ($null -eq $z) { continue }
        $hp = $null
        try { $hp = $z.HighPrecisionTemperature } catch { $hp = $null }
        if ($null -ne $hp -and [double]$hp -gt 0) {
            $k = [double]$hp / 10.0
            $out += [System.Convert]::ToString($k, [System.Globalization.CultureInfo]::InvariantCulture)
            continue
        }
        $t = $null
        try { $t = $z.Temperature } catch { $t = $null }
        if ($null -ne $t -and [double]$t -gt 0) {
            $out += [System.Convert]::ToString([double]$t, [System.Globalization.CultureInfo]::InvariantCulture)
        }
    }
} catch { }
if ($out.Count -eq 0) {
    foreach ($c in @("\Thermal Zone Information(*)\High Precision Temperature", "\Thermal Zone Information(*)\Temperature")) {
        $s = Get-Counter -ErrorAction SilentlyContinue -Counter $c
        if ($s -and $s.CounterSamples) {
            foreach ($sample in $s.CounterSamples) {
                $v = $sample.CookedValue
                if ($v -is [double] -or $v -is [int]) {
                    $num = [double]$v
                    if ($c.Contains("High Precision") -and $num -gt 1000) { $num = $num / 10.0 }
                    $out += [System.Convert]::ToString($num, [System.Globalization.CultureInfo]::InvariantCulture)
                }
            }
        }
        if ($out.Count -gt 0) { break }
    }
}
if ($out.Count -gt 0) { $out }
"""

_CPU_WMI_ACPI_SCRIPT = r"""
$out = @()
try {
    foreach ($s in (Get-CimInstance -Namespace root\WMI -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop)) {
        if ($null -eq $s) { continue }
        try { $v = $s.CurrentTemperature } catch { $v = $null }
        if ($null -ne $v) {
            $out += [System.Convert]::ToString($v, [System.Globalization.CultureInfo]::InvariantCulture)
        }
    }
} catch { }
if ($out.Count -eq 0) {
    try {
        foreach ($p in (Get-CimInstance -Namespace root\cimv2 -ClassName Win32_TemperatureProbe -ErrorAction Stop)) {
            if ($null -eq $p) { continue }
            try { $v = $p.CurrentReading } catch { $v = $null }
            if ($null -ne $v -and [double]$v -gt 0) {
                # Win32_TemperatureProbe.CurrentReading is in tenths of degrees Celsius.
                $k10 = ([double]$v / 10.0 + 273.15) * 10.0
                $out += [System.Convert]::ToString($k10, [System.Globalization.CultureInfo]::InvariantCulture)
            }
        }
    } catch { }
}
if ($out.Count -gt 0) { $out }
"""


# ---------------------------------------------------------------------------
# Fast in-process Windows readers (HWiNFO / Core Temp shared memory, PDH)
# ---------------------------------------------------------------------------

_FILE_MAP_READ = 0x0004
_HWINFO_SIGNATURES = (b"HWiS", b"SiWH")
_HWINFO_SENSOR_TYPE_TEMP = 1
_HWINFO_HEADER_FMT = "<IIIqIIIIII"
_HWINFO_HEADER_SIZE = struct.calcsize(_HWINFO_HEADER_FMT)
_HWINFO_SENSOR_FMT = "<II128s128s"
_HWINFO_SENSOR_SIZE = struct.calcsize(_HWINFO_SENSOR_FMT)
_HWINFO_READING_FMT = "<III128s128s16sdddd"
_HWINFO_READING_SIZE = struct.calcsize(_HWINFO_READING_FMT)

_CORETEMP_MAPPING_NAMES = ("CoreTempMappingObject", r"Global\CoreTempMappingObject")
_HWINFO_MAPPING_NAMES = (r"Global\HWiNFO_SENS_SM2", "HWiNFO_SENS_SM2")
_CORETEMP_MIN_SIZE = 2686

_PDH_FMT_DOUBLE = 0x00000200
_PDH_MORE_DATA = 0x800007D2
_PDH_CSTATUS_VALID_DATA = 0x00000000
_PDH_CSTATUS_NEW_DATA = 0x00000001


def _fold_text(text: str) -> str:
    """Lowercases `text` and strips combining diacritics for locale-safe matching."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _decode_cstr(raw: bytes) -> str:
    head = raw.split(b"\x00", 1)[0]
    for encoding in ("utf-8", "cp1250", "latin-1"):
        try:
            return head.decode(encoding)
        except UnicodeDecodeError:
            continue
    return head.decode("latin-1", errors="replace")


def _read_shared_memory_bytes(names: Sequence[str], size_hint: int | None = None) -> bytes | None:
    """Opens an existing Windows shared-memory mapping read-only and returns bytes."""
    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.OpenFileMappingW.restype = wintypes.HANDLE
        kernel32.MapViewOfFile.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t
        ]
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        kernel32.UnmapViewOfFile.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        kernel32.VirtualQuery.restype = ctypes.c_size_t
    except Exception:
        return None

    for name in names:
        handle = None
        view = None
        try:
            handle = kernel32.OpenFileMappingW(_FILE_MAP_READ, False, name)
            if not handle:
                continue
            view = kernel32.MapViewOfFile(handle, _FILE_MAP_READ, 0, 0, size_hint or 0)
            if not view:
                continue
            region_size = size_hint or 0
            if region_size <= 0:
                class _MBI(ctypes.Structure):
                    _fields_ = [
                        ("BaseAddress", ctypes.c_void_p),
                        ("AllocationBase", ctypes.c_void_p),
                        ("AllocationProtect", wintypes.DWORD),
                        ("PartitionId", wintypes.WORD),
                        ("RegionSize", ctypes.c_size_t),
                        ("State", wintypes.DWORD),
                        ("Protect", wintypes.DWORD),
                        ("Type", wintypes.DWORD),
                    ]
                mbi = _MBI()
                if kernel32.VirtualQuery(view, ctypes.byref(mbi), ctypes.sizeof(mbi)):
                    region_size = min(int(mbi.RegionSize), 4 * 1024 * 1024)
            if region_size <= 0:
                continue
            return ctypes.string_at(view, region_size)
        except Exception:
            continue
        finally:
            if view:
                try:
                    kernel32.UnmapViewOfFile(view)
                except Exception:
                    pass
            if handle:
                try:
                    kernel32.CloseHandle(handle)
                except Exception:
                    pass
    return None


def parse_hwinfo_shared_memory(data: bytes) -> float | None:
    """Extracts the CPU temperature in °C from HWiNFO `HWiNFO_SENS_SM2` bytes."""
    if not data or len(data) < _HWINFO_HEADER_SIZE:
        return None
    if data[:4] not in _HWINFO_SIGNATURES:
        return None
    (
        _sig,
        _ver,
        _rev,
        _poll_time,
        sensor_offset,
        sensor_size,
        sensor_count,
        reading_offset,
        reading_size,
        reading_count,
    ) = struct.unpack_from(_HWINFO_HEADER_FMT, data, 0)

    if (
        reading_size < _HWINFO_READING_SIZE
        or reading_count == 0
        or reading_count > 4096
        or reading_offset + reading_size * reading_count > len(data)
    ):
        return None

    sensors_by_index: dict[int, tuple[str, str]] = {}
    if (
        sensor_size >= _HWINFO_SENSOR_SIZE
        and sensor_count <= 512
        and sensor_offset + sensor_size * sensor_count <= len(data)
    ):
        for idx in range(sensor_count):
            pos = sensor_offset + idx * sensor_size
            _sid, _sinst, orig_raw, user_raw = struct.unpack_from(_HWINFO_SENSOR_FMT, data, pos)
            s_user = _decode_cstr(user_raw).strip()
            s_orig = _decode_cstr(orig_raw).strip()
            sensors_by_index[idx] = (s_user or s_orig, s_orig or s_user)

    candidates: list[tuple[str, float]] = []
    for idx in range(reading_count):
        pos = reading_offset + idx * reading_size
        (
            reading_type,
            sensor_idx,
            _reading_id,
            label_orig_raw,
            label_user_raw,
            unit_raw,
            value,
            _vmin,
            _vmax,
            _vavg,
        ) = struct.unpack_from(_HWINFO_READING_FMT, data, pos)
        if reading_type != _HWINFO_SENSOR_TYPE_TEMP or not math.isfinite(value):
            continue
        unit = _fold_text(_decode_cstr(unit_raw).strip())
        if unit and not any(marker in unit for marker in ("c", "f", "k")):
            continue
        if unit.endswith("f"):
            temp_c = (value - 32.0) * 5.0 / 9.0
        elif unit == "k":
            temp_c = value - 273.15
        else:
            temp_c = value
        if not (15.0 <= temp_c <= 115.0):
            continue

        label_user = _decode_cstr(label_user_raw).strip()
        label_orig = _decode_cstr(label_orig_raw).strip()
        labels = [text for text in (label_user, label_orig) if text]
        sensor_primary, sensor_secondary = sensors_by_index.get(sensor_idx, ("", ""))
        sensor_names = [text for text in (sensor_primary, sensor_secondary) if text]

        combined_folded = _fold_text(" ".join([*sensor_names, *labels]))
        labels_folded = [_fold_text(text) for text in labels]
        sensors_folded = [_fold_text(text) for text in sensor_names]

        if any(bad in combined_folded for bad in ("gpu", "igpu", "grafi", "vram", "hot spot", "hotspot")) and not any(
            cpu_key in text for text in labels_folded for cpu_key in ("cpu", "procesor", "tctl", "tdie")
        ):
            continue
        if any(bad in text for text in labels_folded for bad in ("vrm", "mos", "ssd", "nvme", "pch", "chipset", "cipset")):
            continue

        is_cpu_label = any(_is_cpu_name(text) for text in labels)
        is_cpu_sensor = any(
            key in sensor_text for sensor_text in sensors_folded for key in _CPU_HARDWARE_SENSOR_KEYS
        )
        if is_cpu_label or (
            is_cpu_sensor and not any(bad in text for text in labels_folded for bad in _NON_CPU_SENSOR_KEYS)
        ):
            # Join both user and orig labels so priority matching works regardless of which one is localized.
            match_label = " ".join(dict.fromkeys([*labels, *sensor_names]))
            candidates.append((match_label, temp_c))

    for keyword in (
        "tctl/tdie",
        "cpu package",
        "balicek cpu",
        "cpu balicek",
        "pouzdro cpu",
        "cpu pouzdro",
        "teplota balicku",
        "teplota pouzdra",
        "package",
        "balicek",
        "pouzdro",
        "tdie",
        "tctl",
        "core max",
        "max. jadra",
        "maximum jader",
        "core average",
        "prumer jader",
        "teplota cpu",
        "cpu",
        "procesor",
        "jadro cpu",
        "jadro",
        "core",
    ):
        for label, temp_c in candidates:
            if keyword in _fold_text(label):
                return round(temp_c, 2)
    return round(max(val for _, val in candidates), 2) if candidates else None


def _read_cpu_temp_hwinfo() -> float | None:
    data = _read_shared_memory_bytes(_HWINFO_MAPPING_NAMES)
    if not data:
        return None
    return parse_hwinfo_shared_memory(data)


def parse_coretemp_shared_memory(data: bytes) -> float | None:
    """Extracts the hottest CPU core temperature in °C from Core Temp shared memory."""
    if not data or len(data) < _CORETEMP_MIN_SIZE:
        return None
    core_cnt, cpu_cnt = struct.unpack_from("<II", data, 1536)
    if not (1 <= core_cnt <= 256 and 1 <= cpu_cnt <= 128):
        return None
    tjmax = struct.unpack_from("<128I", data, 1024)
    temps_raw = struct.unpack_from(f"<{core_cnt}f", data, 1544)
    uc_fahrenheit, uc_delta = struct.unpack_from("<BB", data, 2684)

    valid: list[float] = []
    cores_per_cpu = max(1, core_cnt // cpu_cnt)
    for idx, raw_val in enumerate(temps_raw):
        if not math.isfinite(raw_val):
            continue
        val = float(raw_val)
        if uc_delta:
            cpu_idx = min(cpu_cnt - 1, idx // cores_per_cpu)
            tj = float(tjmax[cpu_idx])
            if tj <= 0:
                continue
            val = tj - val
        elif uc_fahrenheit:
            val = (val - 32.0) * 5.0 / 9.0
        if 20.0 <= val <= 115.0:
            valid.append(val)
    return round(max(valid), 2) if valid else None


def _read_cpu_temp_coretemp() -> float | None:
    data = _read_shared_memory_bytes(_CORETEMP_MAPPING_NAMES, size_hint=_CORETEMP_MIN_SIZE)
    if not data:
        return None
    return parse_coretemp_shared_memory(data)


class _PDH_FMT_COUNTERVALUE(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [
            ("longValue", ctypes.c_long),
            ("doubleValue", ctypes.c_double),
            ("largeValue", ctypes.c_longlong),
            ("AnsiStringValue", ctypes.c_char_p),
            ("WideStringValue", ctypes.c_wchar_p),
        ]

    _anonymous_ = ("_u",)
    _fields_ = [
        ("CStatus", wintypes.DWORD),
        ("_pad", wintypes.DWORD),
        ("_u", _U),
    ]


class _PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
    _fields_ = [
        ("szName", wintypes.LPWSTR),
        ("FmtValue", _PDH_FMT_COUNTERVALUE),
    ]


_pdh_thermal_available: bool | None = None


def _read_cpu_temp_pdh() -> float | None:
    """Locale-independent in-process Windows PDH reader for Thermal Zone counters."""
    global _pdh_thermal_available
    if os.name != "nt" or _pdh_thermal_available is False:
        return None
    try:
        pdh = ctypes.WinDLL("pdh", use_last_error=True)
        pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wintypes.HANDLE)]
        pdh.PdhOpenQueryW.restype = wintypes.LONG
        pdh.PdhAddEnglishCounterW.argtypes = [
            wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wintypes.HANDLE)
        ]
        pdh.PdhAddEnglishCounterW.restype = wintypes.LONG
        pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
        pdh.PdhCollectQueryData.restype = wintypes.LONG
        pdh.PdhGetFormattedCounterArrayW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        pdh.PdhGetFormattedCounterArrayW.restype = wintypes.LONG
        pdh.PdhCloseQuery.argtypes = [wintypes.HANDLE]
        pdh.PdhCloseQuery.restype = wintypes.LONG
    except Exception:
        _pdh_thermal_available = False
        return None

    for counter_path, scale in (
        (r"\Thermal Zone Information(*)\High Precision Temperature", 0.1),
        (r"\Thermal Zone Information(*)\Temperature", 1.0),
    ):
        query = wintypes.HANDLE()
        if pdh.PdhOpenQueryW(None, 0, ctypes.byref(query)) != 0:
            continue
        try:
            counter = wintypes.HANDLE()
            if pdh.PdhAddEnglishCounterW(query, counter_path, 0, ctypes.byref(counter)) != 0:
                continue
            if pdh.PdhCollectQueryData(query) != 0:
                continue
            buf_size = wintypes.DWORD(0)
            item_count = wintypes.DWORD(0)
            status = pdh.PdhGetFormattedCounterArrayW(
                counter, _PDH_FMT_DOUBLE, ctypes.byref(buf_size), ctypes.byref(item_count), None
            )
            if (status & 0xFFFFFFFF) != _PDH_MORE_DATA or buf_size.value == 0:
                continue
            buf = (ctypes.c_byte * buf_size.value)()
            if (
                pdh.PdhGetFormattedCounterArrayW(
                    counter, _PDH_FMT_DOUBLE, ctypes.byref(buf_size), ctypes.byref(item_count), buf
                )
                != 0
            ):
                continue
            items = ctypes.cast(buf, ctypes.POINTER(_PDH_FMT_COUNTERVALUE_ITEM_W))
            temps: list[float] = []
            for idx in range(int(item_count.value)):
                fmt_val = items[idx].FmtValue
                if fmt_val.CStatus not in (_PDH_CSTATUS_VALID_DATA, _PDH_CSTATUS_NEW_DATA):
                    continue
                raw = float(fmt_val.doubleValue)
                if not math.isfinite(raw) or raw <= 0:
                    continue
                temp_c = raw * scale - 273.15
                if 20.0 <= temp_c <= 115.0:
                    temps.append(temp_c)
            if temps:
                _pdh_thermal_available = True
                return round(max(temps), 2)
        except Exception:
            continue
        finally:
            try:
                pdh.PdhCloseQuery(query)
            except Exception:
                pass

    if _pdh_thermal_available is None:
        _pdh_thermal_available = False
    return None


def parse_wmi_temperatures(text: str) -> list[tuple[str, float]]:
    """Parses PowerShell WMI output: lines of `name<TAB>value` -> [(name, value)]."""
    result: list[tuple[str, float]] = []
    for line in text.splitlines():
        name, sep, raw = line.partition("\t")
        if not sep:
            continue
        value = _to_float(raw)
        if value is None:
            continue
        result.append((name.strip(), value))
    return result


def _is_cpu_name(name: str) -> bool:
    """True for CPU sensor names like "CPU Package"/"Balíček CPU"/"Jádro CPU"/"Tctl"."""
    lowered = _fold_text(name)
    if not any(key in lowered for key in _CPU_SENSOR_NAME_KEYS):
        return False
    # GPU/VRM/chipset sensors such as "GPU Core Temperature" or "Jádro GPU" are not CPU sensors.
    if any(bad in lowered for bad in ("gpu", "igpu", "grafi", "vram", "hot spot", "hotspot")) and not any(
        cpu_key in lowered for cpu_key in ("cpu", "procesor", "tctl", "tdie")
    ):
        return False
    return not any(bad in lowered for bad in ("vrm", "mos", "ssd", "nvme", "pch", "chipset", "cipset"))


def _normalize_wmi_temperature(value: float | None) -> float | None:
    """Accepts °C or Kelvin readings and returns °C in the valid range."""
    if value is None:
        return None
    for candidate in (value, value - 273.15):
        if 20.0 <= candidate <= 115.0:
            return candidate
    return None


def _cpu_temp_from_wmi_sensors(text: str) -> float | None:
    """CPU temperature from WMI LibreHardwareMonitor/OpenHardwareMonitor sensors."""
    candidates: list[tuple[str, float]] = []
    for name, raw in parse_wmi_temperatures(text):
        normalized = _normalize_wmi_temperature(raw)
        if normalized is not None:
            candidates.append((name, normalized))

    named = [candidate for candidate in candidates if _is_cpu_name(candidate[0])]
    for keyword in ("cpu package", "tctl/tdie", "tdie", "tctl", "cpu"):
        for name, value in named:
            if keyword in name.lower():
                return value
    if named:
        return max(value for _, value in named)

    # Sensors without a name: accept the hottest reading.
    unnamed = [value for name, value in candidates if not name]
    return max(unnamed) if unnamed else None


def _read_cpu_temp_windows_wmi() -> float | None:
    """WMI path (a): LibreHardwareMonitor/OpenHardwareMonitor temperature sensors."""
    text = _run_powershell(_CPU_WMI_SCRIPT, timeout=8.0)
    if not text or not text.strip():
        return None
    return _cpu_temp_from_wmi_sensors(text)


def parse_perf_counter_temperatures(text: str) -> list[float]:
    """Values of the Thermal Zone performance counters (Kelvin)."""
    result: list[float] = []
    for line in text.splitlines():
        value = _to_float(line.strip())
        if value is not None:
            result.append(value)
    return result


def _cpu_temp_from_perf_counters(text: str) -> float | None:
    """Hottest thermal zone in °C, or None (the counters report Kelvin)."""
    valid: list[float] = []
    for value in parse_perf_counter_temperatures(text):
        temp = value - 273.15
        if 20.0 <= temp <= 115.0:
            valid.append(temp)
    return max(valid) if valid else None


def _read_cpu_temp_from_perf_counters() -> float | None:
    """Windows performance counter path (b): in-process PDH English counters, then CIM/Get-Counter."""
    temp = _read_cpu_temp_pdh()
    if temp is not None:
        return temp
    text = _run_powershell(_CPU_PERF_COUNTER_SCRIPT, timeout=8.0)
    if not text or not text.strip():
        return None
    return _cpu_temp_from_perf_counters(text)


def parse_msacpi_temperatures(text: str) -> list[float]:
    """Values of `MSAcpi_ThermalZoneTemperature` (0.1 K units)."""
    result: list[float] = []
    for line in text.splitlines():
        value = _to_float(line.strip())
        if value is not None:
            result.append(value)
    return result


def _cpu_temp_from_wmi_acpi(text: str) -> float | None:
    """Hottest MSAcpi thermal zone in °C, or None (values are 0.1 K)."""
    valid: list[float] = []
    for value in parse_msacpi_temperatures(text):
        temp = value / 10.0 - 273.15
        if 20.0 <= temp <= 115.0:
            valid.append(temp)
    return max(valid) if valid else None


def _read_cpu_temp_wmi_acpi() -> float | None:
    """WMI path (c): `MSAcpi_ThermalZoneTemperature` from root\\WMI."""
    text = _run_powershell(_CPU_WMI_ACPI_SCRIPT, timeout=8.0)
    if not text or not text.strip():
        return None
    return _cpu_temp_from_wmi_acpi(text)


def read_cpu_load() -> float | None:
    """CPU load percentage from psutil, or None when unavailable."""
    try:
        return psutil.cpu_percent(interval=0.05)
    except Exception:
        return None


def read_cpu_stats() -> CpuStats | None:
    """Best-effort CPU reading (psutil + Windows sensors); None if unavailable."""
    temp = read_cpu_temp()
    load = read_cpu_load()
    if temp is None and load is None:
        return None
    return CpuStats(temp_c=temp, load_percent=load)


# ---------------------------------------------------------------------------
# session telemetry
# ---------------------------------------------------------------------------


class TelemetryCollector:
    """Accumulates GPU/CPU samples during a session and summarizes them."""

    def __init__(self) -> None:
        self._gpu: list[GpuStats] = []
        self._cpu: list[CpuStats] = []

    def record(self, gpu: GpuStats | None, cpu: CpuStats | None) -> None:
        """Stores one sample; readings that are None are simply not stored."""
        if gpu is not None:
            self._gpu.append(gpu)
        if cpu is not None:
            self._cpu.append(cpu)

    def summary(self) -> dict[str, float | None]:
        """Averages and maxima of the stored readings (None when absent)."""
        gpu_temps = [sample.temp_c for sample in self._gpu if sample.temp_c is not None]
        gpu_loads = [sample.load_percent for sample in self._gpu if sample.load_percent is not None]
        cpu_temps = [sample.temp_c for sample in self._cpu if sample.temp_c is not None]
        cpu_loads = [sample.load_percent for sample in self._cpu if sample.load_percent is not None]
        return {
            "gpu_temp_avg": _mean(gpu_temps),
            "gpu_temp_max": _maximum(gpu_temps),
            "gpu_load_avg": _mean(gpu_loads),
            "cpu_temp_avg": _mean(cpu_temps),
            "cpu_temp_max": _maximum(cpu_temps),
            "cpu_load_avg": _mean(cpu_loads),
        }


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _maximum(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(max(values), 2)
