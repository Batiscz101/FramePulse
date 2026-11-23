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

import json
import logging
import os
import shutil
import subprocess
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
        if shutil.which(str(args[0])) is None:
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


def _read_gpu_nvidia_smi() -> GpuStats | None:
    text = _run_command(
        ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu", "--format=csv,noheader,nounits"],
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
    """CPU temperature: psutil sensors, then Windows sources when available."""
    temp = _read_cpu_temp_psutil()
    if temp is not None:
        return temp
    if os.name == "nt":
        for reader in (
            _read_cpu_temp_windows_wmi,
            _read_cpu_temp_from_perf_counters,
            _read_cpu_temp_wmi_acpi,
        ):
            temp = reader()
            if temp is not None:
                return temp
    return None


# ---------------------------------------------------------------------------
# CPU: Windows fallbacks (psutil has no sensors on Windows)
# ---------------------------------------------------------------------------

# Name fragments of the CPU temperature sensors we accept from WMI. GPU
# sensors such as "GPU Core Temperature" must not be mistaken for CPU ones.
_CPU_SENSOR_NAME_KEYS = ("cpu package", "cpu", "tctl", "core")

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

_CPU_PERF_COUNTER_SCRIPT = r"""$out = @()
$c = "\Thermal Zone Information(*)\Temperature"
$s = Get-Counter -ErrorAction SilentlyContinue -Counter $c
if ($s -and $s.CounterSamples) {
    foreach ($sample in $s.CounterSamples) {
        $v = $sample.CookedValue
        if ($v -is [double] -or $v -is [int]) {
            $out += [System.Convert]::ToString($v, [System.Globalization.CultureInfo]::InvariantCulture)
        }
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
if ($out.Count -gt 0) { $out }
"""


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
    """True for CPU sensor names like "CPU Package"/"Core 0"/"Tctl"."""
    lowered = name.lower()
    if not any(key in lowered for key in _CPU_SENSOR_NAME_KEYS):
        return False
    # GPU sensors such as "GPU Core Temperature" are not CPU sensors.
    return not ("gpu" in lowered and "cpu" not in lowered)


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
    for keyword in ("cpu package", "tctl", "cpu"):
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
    """Windows performance counter path (b): \\Thermal Zone Information(*)."""
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
