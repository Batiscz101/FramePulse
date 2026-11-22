from __future__ import annotations

import unittest
from unittest import mock

from framepulse_agent import sensors
from framepulse_agent.sensors import (
    CpuStats,
    GpuStats,
    TelemetryCollector,
    cpu_temp_from_sensors,
    parse_nvidia_smi_output,
    parse_perf_counter_output,
)


class _Shim:
    """Stand-in for a psutil sensor (`current` attribute)."""

    def __init__(self, value: float | None) -> None:
        self.current = value


class ParseNvidiaSmiOutputTests(unittest.TestCase):
    def test_temp_and_load(self) -> None:
        stats = parse_nvidia_smi_output("45, 23\n")
        self.assertIsNotNone(stats)
        self.assertEqual(stats.temp_c, 45.0)
        self.assertEqual(stats.load_percent, 23.0)

    def test_temp_only(self) -> None:
        stats = parse_nvidia_smi_output("45\n")
        self.assertIsNotNone(stats)
        self.assertEqual(stats.temp_c, 45.0)
        self.assertIsNone(stats.load_percent)

    def test_ignores_garbage(self) -> None:
        self.assertIsNone(parse_nvidia_smi_output(""))
        self.assertIsNone(parse_nvidia_smi_output("# header\n"))
        self.assertIsNone(parse_nvidia_smi_output("not, a, number"))


class ParsePerfCounterOutputTests(unittest.TestCase):
    def test_parses_temp_and_load(self) -> None:
        stats = parse_perf_counter_output("TEMP=50\nLOAD=12\n")
        self.assertIsNotNone(stats)
        self.assertEqual(stats.temp_c, 50.0)
        self.assertEqual(stats.load_percent, 12.0)

    def test_ignores_empty_and_unknown(self) -> None:
        self.assertIsNone(parse_perf_counter_output(""))
        self.assertIsNone(parse_perf_counter_output("SOMETHING=5\n"))


class CpuTempFromSensorsTests(unittest.TestCase):
    def test_prefers_package_entry(self) -> None:
        raw = {
            "Package Id 0": [_Shim(58.5)],
            "Core 0": [_Shim(41.0)],
            "Core 1": [_Shim(43.0)],
        }
        self.assertEqual(cpu_temp_from_sensors(raw), 58.5)

    def test_falls_back_to_max_of_all(self) -> None:
        raw = {"Core 0": [_Shim(41.0)], "GPU": [_Shim(30.0)]}
        self.assertEqual(cpu_temp_from_sensors(raw), 41.0)

    def test_empty_or_missing_values(self) -> None:
        self.assertIsNone(cpu_temp_from_sensors({}))
        self.assertIsNone(cpu_temp_from_sensors(None))
        self.assertIsNone(cpu_temp_from_sensors({"Core 0": []}))
        self.assertIsNone(cpu_temp_from_sensors({"Core 0": [_Shim(None)]}))

    def test_ignores_non_list_values(self) -> None:
        self.assertIsNone(cpu_temp_from_sensors({"Core 0": _Shim(41.0)}))


class ReadGpuStatsTests(unittest.TestCase):
    def test_nvidia_smi_used_first(self) -> None:
        with mock.patch.object(
            sensors, "_read_gpu_nvidia_smi", return_value=GpuStats(temp_c=50.0, load_percent=10.0)
        ):
            stats = sensors.read_gpu_stats()
        self.assertEqual((stats.temp_c, stats.load_percent), (50.0, 10.0))

    def test_wmi_fallback_when_nvidia_smi_missing(self) -> None:
        with mock.patch.object(sensors, "_read_gpu_nvidia_smi", return_value=None), \
                mock.patch.object(
                    sensors, "_read_gpu_wmi", return_value=GpuStats(name="AMD Radeon", temp_c=60.0)
                ):
            stats = sensors.read_gpu_stats()
        self.assertEqual((stats.name, stats.temp_c), ("AMD Radeon", 60.0))

    def test_none_when_nothing_available(self) -> None:
        with mock.patch.object(sensors, "_read_gpu_nvidia_smi", return_value=None), \
                mock.patch.object(sensors, "_read_gpu_wmi", return_value=None):
            self.assertIsNone(sensors.read_gpu_stats())

    def test_does_not_raise_in_this_environment(self) -> None:
        stats = sensors.read_gpu_stats()
        self.assertTrue(stats is None or isinstance(stats, GpuStats))


class ReadCpuStatsTests(unittest.TestCase):
    def test_read_cpu_temp_with_sensors(self) -> None:
        with mock.patch.object(
            sensors.psutil, "sensors_temperatures", create=True, return_value={"Package Id 0": [_Shim(58.5)]}
        ):
            self.assertEqual(sensors.read_cpu_temp(), 58.5)

    def test_read_cpu_temp_without_sensors(self) -> None:
        with mock.patch.object(sensors.psutil, "sensors_temperatures", create=True, side_effect=AttributeError):
            self.assertIsNone(sensors.read_cpu_temp())

    def test_read_cpu_load(self) -> None:
        with mock.patch.object(sensors.psutil, "cpu_percent", return_value=42.0):
            self.assertEqual(sensors.read_cpu_load(), 42.0)

    def test_read_cpu_stats_uses_psutil(self) -> None:
        with mock.patch.object(sensors, "read_cpu_temp", return_value=60.0), \
                mock.patch.object(sensors, "read_cpu_load", return_value=33.0):
            stats = sensors.read_cpu_stats()
        self.assertEqual((stats.temp_c, stats.load_percent), (60.0, 33.0))

    def test_read_cpu_stats_none_when_unavailable(self) -> None:
        with mock.patch.object(sensors, "read_cpu_temp", return_value=None), \
                mock.patch.object(sensors, "read_cpu_load", return_value=None):
            self.assertIsNone(sensors.read_cpu_stats())


class TelemetryCollectorTests(unittest.TestCase):
    def test_summary_averages_and_maxima(self) -> None:
        collector = TelemetryCollector()
        collector.record(GpuStats(temp_c=50.0, load_percent=10.0), CpuStats(temp_c=60.0, load_percent=20.0))
        collector.record(GpuStats(temp_c=70.0, load_percent=30.0), CpuStats(temp_c=80.0, load_percent=40.0))
        summary = collector.summary()
        self.assertEqual(summary["gpu_temp_avg"], 60.0)
        self.assertEqual(summary["gpu_temp_max"], 70.0)
        self.assertEqual(summary["gpu_load_avg"], 20.0)
        self.assertEqual(summary["cpu_temp_avg"], 70.0)
        self.assertEqual(summary["cpu_load_avg"], 30.0)

    def test_summary_ignores_none_values(self) -> None:
        collector = TelemetryCollector()
        collector.record(GpuStats(), CpuStats())
        summary = collector.summary()
        for value in summary.values():
            self.assertIsNone(value)

    def test_summary_empty(self) -> None:
        summary = TelemetryCollector().summary()
        for value in summary.values():
            self.assertIsNone(value)


if __name__ == "__main__":
    unittest.main()
