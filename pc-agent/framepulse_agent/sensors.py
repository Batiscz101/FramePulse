"""Best-effort reading of GPU and CPU temperatures and loads (never raises).

GPU: NVIDIA first via `nvidia-smi` (the NVML command line tool), then the
AMD/Intel path via Windows performance counters and WMI CIM (video adapter
names). CPU: `psutil` plus Windows sensors when they are exposed – no
external drivers are needed.

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


def read_cpu_temp() -> float | None:
    """CPU temperature from psutil sensors, or None when unavailable."""
    sensors_fn = getattr(psutil, "sensors_temperatures", None)
    if sensors_fn is None:
        return None
    try:
        raw = sensors_fn()
    except Exception:
        return None
    return cpu_temp_from_sensors(raw)


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
