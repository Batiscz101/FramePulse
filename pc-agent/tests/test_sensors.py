from __future__ import annotations

import unittest
from unittest import mock

from framepulse_agent import sensors
from framepulse_agent.sensors import (
    CpuStats,
    GpuStats,
    TelemetryCollector,
    _cpu_temp_from_perf_counters,
    _cpu_temp_from_wmi_acpi,
    _cpu_temp_from_wmi_sensors,
    _is_cpu_name,
    _normalize_wmi_temperature,
    cpu_temp_from_sensors,
    parse_msacpi_temperatures,
    parse_nvidia_smi_output,
    parse_perf_counter_output,
    parse_perf_counter_temperatures,
    parse_wmi_temperatures,
)


class ReadGpuStatsPerformanceTests(unittest.TestCase):
    def test_nvidia_smi_path_used_when_cached(self) -> None:
        with mock.patch.object(sensors, "_locate_nvidia_smi", return_value=r"C:\Windows\System32\nvidia-smi.exe"), \
                mock.patch.object(
                    sensors, "_run_command", return_value="50, 10\n"
                ) as run_command:
            stats = sensors._read_gpu_nvidia_smi()
        self.assertIsNotNone(stats)
        run_command.assert_called_once()
        args = run_command.call_args[0][0]
        self.assertEqual(args[0], r"C:\Windows\System32\nvidia-smi.exe")

    def test_nvidia_smi_missing_returns_none(self) -> None:
        with mock.patch.object(sensors, "_locate_nvidia_smi", return_value=None):
            self.assertIsNone(sensors._read_gpu_nvidia_smi())


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
        with mock.patch.object(
            sensors.psutil, "sensors_temperatures", create=True, side_effect=AttributeError
        ), mock.patch.object(sensors.os, "name", "nt"), mock.patch.object(
            sensors, "_read_cpu_temp_windows_wmi", return_value=None
        ), mock.patch.object(
            sensors, "_read_cpu_temp_from_perf_counters", return_value=None
        ), mock.patch.object(
            sensors, "_read_cpu_temp_wmi_acpi", return_value=None
        ):
            self.assertIsNone(sensors.read_cpu_temp())

    def test_read_cpu_temp_falls_back_to_windows_wmi(self) -> None:
        with mock.patch.object(
            sensors.psutil, "sensors_temperatures", create=True, side_effect=AttributeError
        ), mock.patch.object(sensors.os, "name", "nt"), mock.patch.object(
            sensors, "_cpu_windows_sensors_available",
            {"wmi": None, "perf": None, "acpi": None},
        ), mock.patch.object(
            sensors, "_read_cpu_temp_windows_wmi", return_value=58.5
        ):
            self.assertEqual(sensors.read_cpu_temp(), 58.5)

    def test_read_cpu_temp_falls_back_to_perf_counters(self) -> None:
        with mock.patch.object(
            sensors.psutil, "sensors_temperatures", create=True, side_effect=AttributeError
        ), mock.patch.object(sensors.os, "name", "nt"), mock.patch.object(
            sensors, "_cpu_windows_sensors_available",
            {"wmi": None, "perf": None, "acpi": None},
        ), mock.patch.object(
            sensors, "_read_cpu_temp_windows_wmi", return_value=None
        ), mock.patch.object(
            sensors, "_read_cpu_temp_from_perf_counters", return_value=43.0
        ):
            self.assertEqual(sensors.read_cpu_temp(), 43.0)

    def test_read_cpu_temp_falls_back_to_acpi(self) -> None:
        with mock.patch.object(
            sensors.psutil, "sensors_temperatures", create=True, side_effect=AttributeError
        ), mock.patch.object(sensors.os, "name", "nt"), mock.patch.object(
            sensors, "_cpu_windows_sensors_available",
            {"wmi": None, "perf": None, "acpi": None},
        ), mock.patch.object(
            sensors, "_read_cpu_temp_windows_wmi", return_value=None
        ), mock.patch.object(
            sensors, "_read_cpu_temp_from_perf_counters", return_value=None
        ), mock.patch.object(
            sensors, "_read_cpu_temp_wmi_acpi", return_value=44.5
        ):
            self.assertEqual(sensors.read_cpu_temp(), 44.5)

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


class ParseWmiTemperaturesTests(unittest.TestCase):
    def test_parses_name_and_value_lines(self) -> None:
        text = "CPU Package\t58.5\nGPU Core Temperature\t55.0\nBad line\nNoTab\n\t3.5\n"
        self.assertEqual(
            parse_wmi_temperatures(text),
            [("CPU Package", 58.5), ("GPU Core Temperature", 55.0), ("", 3.5)],
        )

    def test_empty_output(self) -> None:
        self.assertEqual(parse_wmi_temperatures(""), [])
        self.assertEqual(parse_wmi_temperatures("nothing here"), [])


class IsCpuNameTests(unittest.TestCase):
    def test_accepts_cpu_names(self) -> None:
        for name in ("CPU Package", "CPU Core #1", "Core 0", "Tctl", "cpu total"):
            self.assertTrue(_is_cpu_name(name), name)

    def test_rejects_gpu_and_other_names(self) -> None:
        for name in (
            "GPU Core Temperature",
            "GPU Temperature",
            "Package Power",
            "SSD Temperature",
            "PCH Temperature",
        ):
            self.assertFalse(_is_cpu_name(name), name)


class NormalizeWmiTemperatureTests(unittest.TestCase):
    def test_celsius_in_range(self) -> None:
        self.assertEqual(_normalize_wmi_temperature(58.5), 58.5)

    def test_kelvin_in_range(self) -> None:
        self.assertAlmostEqual(_normalize_wmi_temperature(331.7), 58.55, places=5)

    def test_rejects_none_and_out_of_range(self) -> None:
        self.assertIsNone(_normalize_wmi_temperature(None))
        self.assertIsNone(_normalize_wmi_temperature(-10.0))
        self.assertIsNone(_normalize_wmi_temperature(200.0))


class CpuTempFromWmiSensorsTests(unittest.TestCase):
    def test_prefers_cpu_package(self) -> None:
        text = "GPU Core Temperature\t55.0\nCPU Package\t58.5\nCPU Core #2\t41.0\n"
        self.assertEqual(_cpu_temp_from_wmi_sensors(text), 58.5)

    def test_uses_tctl(self) -> None:
        self.assertEqual(_cpu_temp_from_wmi_sensors("Tctl\t72.4\n"), 72.4)

    def test_kelvin_readings_are_converted(self) -> None:
        self.assertAlmostEqual(_cpu_temp_from_wmi_sensors("CPU Package\t305.5\n"), 32.35, places=5)

    def test_none_when_no_cpu_named_sensors(self) -> None:
        self.assertIsNone(_cpu_temp_from_wmi_sensors("GPU Core Temperature\t55.0\n"))
        self.assertIsNone(_cpu_temp_from_wmi_sensors(""))


class PerfCounterTemperatureTests(unittest.TestCase):
    def test_parse_ignores_junk(self) -> None:
        self.assertEqual(parse_perf_counter_temperatures("312.5\njunk\n\n300\n"), [312.5, 300.0])

    def test_converts_kelvin_and_takes_the_hottest(self) -> None:
        self.assertAlmostEqual(_cpu_temp_from_perf_counters("312.5\n300.0\n"), 39.35, places=5)

    def test_rejects_out_of_range(self) -> None:
        self.assertIsNone(_cpu_temp_from_perf_counters("260.0\n"))
        self.assertIsNone(_cpu_temp_from_perf_counters(""))


class MsacpiTemperatureTests(unittest.TestCase):
    def test_parse(self) -> None:
        self.assertEqual(parse_msacpi_temperatures("3200\njunk\n"), [3200.0])

    def test_converts_tenths_of_kelvin(self) -> None:
        self.assertAlmostEqual(_cpu_temp_from_wmi_acpi("3200\n3150\n"), 46.85, places=5)

    def test_rejects_out_of_range(self) -> None:
        self.assertIsNone(_cpu_temp_from_wmi_acpi("2800\n"))  # 280.0 K - 273.15 = 6.85
        self.assertIsNone(_cpu_temp_from_wmi_acpi(""))


class LocateNvidiaSmiTests(unittest.TestCase):
    """The nvidia-smi path is cached at startup; unavailable = disabled for the run."""

    def setUp(self) -> None:
        self._old_path = sensors._nvidia_smi_path
        sensors._nvidia_smi_path = False

    def tearDown(self) -> None:
        sensors._nvidia_smi_path = self._old_path

    def test_finds_system32_candidate_and_caches(self) -> None:
        with mock.patch.object(
            sensors.os.path,
            "isfile",
            side_effect=lambda p: p.endswith("nvidia-smi.exe") and "System32" in p,
        ), mock.patch.object(sensors.shutil, "which", return_value=None):
            path = sensors._locate_nvidia_smi()
        self.assertEqual(path, r"C:\Windows\System32\nvidia-smi.exe")
        self.assertIs(sensors._locate_nvidia_smi(), path)

    def test_falls_back_to_path_then_none_and_caches(self) -> None:
        with mock.patch.object(sensors.os.path, "isfile", return_value=False), \
                mock.patch.object(sensors.shutil, "which", return_value=r"C:\Tools\nvidia-smi.exe"):
            path = sensors._locate_nvidia_smi()
        self.assertEqual(path, r"C:\Tools\nvidia-smi.exe")

        sensors._nvidia_smi_path = False
        with mock.patch.object(sensors.os.path, "isfile", return_value=False), \
                mock.patch.object(sensors.shutil, "which", return_value=None):
            self.assertIsNone(sensors._locate_nvidia_smi())
            self.assertIsNone(sensors._locate_nvidia_smi())
            self.assertIsNone(sensors._nvidia_smi_path)


class WindowsCpuAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_probed = sensors._startup_probed
        self._old_available = dict(sensors._cpu_windows_sensors_available)
        sensors._startup_probed = False
        sensors._cpu_windows_sensors_available = {"wmi": None, "perf": None, "acpi": None}

    def tearDown(self) -> None:
        sensors._startup_probed = self._old_probed
        sensors._cpu_windows_sensors_available = self._old_available

    def test_probe_marks_sources_available_or_unavailable(self) -> None:
        with mock.patch.object(
            sensors, "_read_cpu_temp_windows_wmi", return_value=58.5
        ), mock.patch.object(sensors, "_read_cpu_temp_from_perf_counters", return_value=None), \
                mock.patch.object(sensors, "_read_cpu_temp_wmi_acpi", return_value=44.5):
            availability = sensors._probe_windows_cpu_sensors()
        self.assertEqual(availability, {"wmi": True, "perf": False, "acpi": True})

    def test_read_cpu_temp_skips_unavailable_readers(self) -> None:
        sensors._cpu_windows_sensors_available = {
            "wmi": False,
            "perf": True,
            "acpi": False,
        }
        with mock.patch.object(
            sensors.psutil, "sensors_temperatures", create=True, side_effect=AttributeError
        ), mock.patch.object(
            sensors, "_read_cpu_temp_windows_wmi",
            side_effect=AssertionError("must not be called when marked unavailable"),
        ), mock.patch.object(
            sensors, "_read_cpu_temp_from_perf_counters", return_value=43.0
        ), mock.patch.object(
            sensors, "_read_cpu_temp_wmi_acpi",
            side_effect=AssertionError("must not be called when marked unavailable"),
        ):
            self.assertEqual(sensors.read_cpu_temp(), 43.0)

    def test_read_cpu_temp_remembers_a_miss(self) -> None:
        with mock.patch.object(
            sensors.psutil, "sensors_temperatures", create=True, side_effect=AttributeError
        ), mock.patch.object(sensors.os, "name", "nt"), mock.patch.object(
            sensors, "_read_cpu_temp_windows_wmi", return_value=None
        ), mock.patch.object(
            sensors, "_read_cpu_temp_from_perf_counters", return_value=None
        ), mock.patch.object(
            sensors, "_read_cpu_temp_wmi_acpi", return_value=None
        ):
            self.assertIsNone(sensors.read_cpu_temp())
        self.assertEqual(
            sensors._cpu_windows_sensors_available,
            {"wmi": False, "perf": False, "acpi": False},
        )

    def test_probe_startup_sensors_fills_availability(self) -> None:
        with mock.patch.object(sensors, "_locate_nvidia_smi", return_value=None) as locate, \
                mock.patch.object(sensors.os, "name", "nt"), \
                mock.patch.object(sensors, "_read_cpu_temp_windows_wmi", return_value=58.5), \
                mock.patch.object(sensors, "_read_cpu_temp_from_perf_counters", return_value=None), \
                mock.patch.object(sensors, "_read_cpu_temp_wmi_acpi", return_value=None):
            sensors.probe_startup_sensors()
            sensors.probe_startup_sensors()  # second call must be a no-op

        self.assertTrue(sensors._startup_probed)
        locate.assert_called_once()
        self.assertEqual(
            sensors._cpu_windows_sensors_available,
            {"wmi": True, "perf": False, "acpi": False},
        )


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
