# Copyright 2025 The WheelOS Team. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Created Date: 2025-02-15
# Author: daohu527


import unittest
from unittest.mock import patch, MagicMock

from src.utils.shell_runner import CommandResult
from src.execution.interface import Status, Severity
from src.probe.software.system_probe import SystemProbe


def _probe(extra_cfg=None):
    config = {
        "infrastructure": {
            "expected_cpu_cores": 2,
            "storage": {"data_path": "/tmp", "min_free_gb": 1},
        },
        "thresholds": {
            "cpu_temp_c": 90,
            "dmesg_lines": 500,
            "journal_since": "1 hour ago",
            "boot_time_warn_s": 60,
            "boot_time_fail_s": 120,
        },
    }
    if extra_cfg:
        config.update(extra_cfg)
    return SystemProbe(config)


# ─── CPU ────────────────────────────────────────────────────────────────────


class CpuCoreTests(unittest.TestCase):
    def test_pass_when_cores_sufficient(self):
        probe = _probe({"infrastructure": {"expected_cpu_cores": 1}})
        with patch("src.probe.software.system_probe.os.cpu_count", return_value=4), patch(
            "src.probe.software.system_probe.glob.glob", return_value=[]
        ):
            results = probe._check_cpu()
        core_result = next(r for r in results if r.item_name == "CPU Core Count")
        self.assertEqual(core_result.status, Status.PASS)

    def test_warn_when_cores_insufficient(self):
        probe = _probe()
        with patch("src.probe.software.system_probe.os.cpu_count", return_value=1), patch(
            "src.probe.software.system_probe.glob.glob", return_value=[]
        ):
            results = probe._check_cpu()
        core_result = next(r for r in results if r.item_name == "CPU Core Count")
        self.assertEqual(core_result.status, Status.WARN)
        self.assertEqual(core_result.error_code, "INFRA_CPU_CORE_MISMATCH")


class CpuTemperatureTests(unittest.TestCase):
    def test_pass_when_temp_normal(self):
        probe = _probe()
        fake_hwmon = "/sys/class/hwmon/hwmon0/"

        def fake_read_sysfs(path):
            if path.endswith("/name"):
                return "coretemp"
            if "temp" in path and "_input" in path:
                return "60000"  # 60°C
            return None

        with patch(
            "src.probe.software.system_probe.glob.glob",
            side_effect=lambda p: (
                [fake_hwmon] if "hwmon*/" in p else [fake_hwmon + "temp1_input"]
            ),
        ), patch("src.probe.software.system_probe.read_sysfs", side_effect=fake_read_sysfs):
            results = probe._check_cpu_temperature()

        self.assertTrue(any(r.item_name == "CPU Temperature" for r in results))
        temp_result = next(r for r in results if r.item_name == "CPU Temperature")
        self.assertEqual(temp_result.status, Status.PASS)

    def test_fail_when_temp_critical(self):
        probe = _probe()
        fake_hwmon = "/sys/class/hwmon/hwmon0/"

        def fake_read_sysfs(path):
            if path.endswith("/name"):
                return "coretemp"
            if "temp" in path and "_input" in path:
                return "105000"  # 105°C > 90+10
            return None

        with patch(
            "src.probe.software.system_probe.glob.glob",
            side_effect=lambda p: (
                [fake_hwmon] if "hwmon*/" in p else [fake_hwmon + "temp1_input"]
            ),
        ), patch("src.probe.software.system_probe.read_sysfs", side_effect=fake_read_sysfs):
            results = probe._check_cpu_temperature()

        temp_result = next(r for r in results if r.item_name == "CPU Temperature")
        self.assertEqual(temp_result.status, Status.FAIL)
        self.assertEqual(temp_result.error_code, "INFRA_CPU_OVERTEMP")


class CpuGovernorTests(unittest.TestCase):
    def test_pass_all_performance(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.glob.glob",
            return_value=["/sys/devices/system/cpu/cpufreq/policy0/"],
        ), patch(
            "src.probe.software.system_probe.read_sysfs", return_value="performance"
        ):
            results = probe._check_cpu_frequency()
        self.assertEqual(results[0].status, Status.PASS)

    def test_warn_non_performance_governor(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.glob.glob",
            return_value=["/sys/devices/system/cpu/cpufreq/policy0/"],
        ), patch(
            "src.probe.software.system_probe.read_sysfs", return_value="powersave"
        ):
            results = probe._check_cpu_frequency()
        self.assertEqual(results[0].status, Status.WARN)
        self.assertEqual(results[0].error_code, "INFRA_CPU_GOV_NOT_PERF")


# ─── Memory ─────────────────────────────────────────────────────────────────


class MemoryTests(unittest.TestCase):
    def _meminfo(self, total_kb, available_kb):
        return f"MemTotal: {total_kb} kB\nMemAvailable: {available_kb} kB\n"

    def test_pass_when_usage_low(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.read_sysfs",
            return_value=self._meminfo(16 * 1024 * 1024, 12 * 1024 * 1024),
        ):
            results = probe._check_memory()
        self.assertEqual(results[0].status, Status.PASS)

    def test_warn_at_high_usage(self):
        probe = _probe()
        total = 16 * 1024 * 1024  # 16 GB in kB
        available = int(total * 0.15)  # 85% used
        with patch(
            "src.probe.software.system_probe.read_sysfs",
            return_value=self._meminfo(total, available),
        ):
            results = probe._check_memory()
        self.assertEqual(results[0].status, Status.WARN)
        self.assertEqual(results[0].error_code, "INFRA_MEM_HIGH")

    def test_fail_at_critical_usage(self):
        probe = _probe()
        total = 16 * 1024 * 1024
        available = int(total * 0.05)  # 95% used
        with patch(
            "src.probe.software.system_probe.read_sysfs",
            return_value=self._meminfo(total, available),
        ):
            results = probe._check_memory()
        self.assertEqual(results[0].status, Status.FAIL)
        self.assertEqual(results[0].error_code, "INFRA_MEM_CRITICAL")


# ─── Disk ────────────────────────────────────────────────────────────────────


class DiskTests(unittest.TestCase):
    def test_pass_when_enough_free(self):
        probe = _probe()
        fake_stat = MagicMock()
        # 200 GB free: f_bavail * f_frsize = 200 * 1024^3
        fake_stat.f_frsize = 4096
        fake_stat.f_bavail = 200 * 1024 * 1024 * 1024 // 4096  # 200 GB in blocks
        fake_stat.f_blocks = 500 * 1024 * 1024 * 1024 // 4096  # 500 GB total
        with patch("src.probe.software.system_probe.os.statvfs", return_value=fake_stat), patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(1, "", ""),
        ):
            results = probe._check_disk()
        disk_result = next(r for r in results if "Disk Space" in r.item_name)
        self.assertEqual(disk_result.status, Status.PASS)

    def test_fail_when_low_disk(self):
        probe = _probe()
        fake_stat = MagicMock()
        fake_stat.f_frsize = 4096
        fake_stat.f_bavail = 0  # 0 GB free
        fake_stat.f_blocks = 500 * 1024 * 1024 * 1024 // 4096  # 500 GB total
        with patch("src.probe.software.system_probe.os.statvfs", return_value=fake_stat), patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(1, "", ""),
        ):
            results = probe._check_disk()
        disk_result = next(r for r in results if "Disk Space" in r.item_name)
        self.assertEqual(disk_result.status, Status.FAIL)
        self.assertEqual(disk_result.error_code, "INFRA_DISK_LOW")


# ─── PCIe ────────────────────────────────────────────────────────────────────


class PCIeTests(unittest.TestCase):
    _LSPCI_DEGRADED = (
        "01:00.0 VGA compatible controller: NVIDIA Corporation\n"
        "        LnkCap: Speed 16GT/s, Width x16\n"
        "        LnkSta: Speed 16GT/s, Width x8\n"
    )
    _LSPCI_CLEAN = (
        "01:00.0 VGA compatible controller: NVIDIA Corporation\n"
        "        LnkCap: Speed 16GT/s, Width x16\n"
        "        LnkSta: Speed 16GT/s, Width x16\n"
    )

    def test_detects_pcie_degradation(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(0, self._LSPCI_DEGRADED, ""),
        ):
            results = probe._check_pcie()
        self.assertTrue(any(r.error_code == "INFRA_PCIE_DEGRADED" for r in results))

    def test_pass_when_no_degradation(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(0, self._LSPCI_CLEAN, ""),
        ):
            results = probe._check_pcie()
        self.assertTrue(all(r.status == Status.PASS for r in results))


# ─── dmesg anomaly detection ─────────────────────────────────────────────────


class DmesgTests(unittest.TestCase):
    def test_detects_kernel_panic(self):
        probe = _probe()
        dmesg_output = "[123.456] kernel panic - not syncing: VFS: Unable to mount root fs"
        with patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(0, dmesg_output, ""),
        ):
            results = probe._check_dmesg()
        error_codes = {r.error_code for r in results}
        self.assertIn("INFRA_KERNEL_PANIC", error_codes)

    def test_detects_oom_kill(self):
        probe = _probe()
        dmesg_output = "[200.000] Out of memory: Kill process 1234 (myapp) score 900"
        with patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(0, dmesg_output, ""),
        ):
            results = probe._check_dmesg()
        error_codes = {r.error_code for r in results}
        self.assertIn("INFRA_OOM_KILL", error_codes)

    def test_detects_hardware_error(self):
        probe = _probe()
        dmesg_output = "[300.000] EDAC MC0: 1 UE on memory controller 0 (DIMM 0)"
        with patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(0, dmesg_output, ""),
        ):
            results = probe._check_dmesg()
        error_codes = {r.error_code for r in results}
        self.assertIn("INFRA_HW_ERROR", error_codes)

    def test_pass_when_no_anomalies(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(0, "Everything is fine.", ""),
        ):
            results = probe._check_dmesg()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, Status.PASS)
        self.assertEqual(results[0].item_name, "dmesg Anomalies")

    def test_skips_gracefully_when_dmesg_unavailable(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(1, "", "permission denied"),
        ):
            results = probe._check_dmesg()
        self.assertEqual(results, [])


# ─── journalctl service failure detection ────────────────────────────────────


class JournalTests(unittest.TestCase):
    _JOURNAL_FAILED = (
        "Feb 23 10:00:01 myhost systemd[1]: myapp.service: Failed with result 'exit-code'.\n"
        "Feb 23 10:00:01 myhost systemd[1]: Failed to start myapp.service.\n"
    )

    def test_detects_failed_service(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(0, self._JOURNAL_FAILED, ""),
        ):
            results = probe._check_journal()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].error_code, "INFRA_SERVICE_FAILED")
        self.assertIn("myapp.service", results[0].message)

    def test_pass_when_no_failures(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(0, "", ""),
        ):
            results = probe._check_journal()
        self.assertEqual(results[0].status, Status.PASS)

    def test_skips_when_journalctl_unavailable(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(1, "", "not found"),
        ):
            results = probe._check_journal()
        self.assertEqual(results, [])


# ─── Boot time analysis ───────────────────────────────────────────────────────


class BootTests(unittest.TestCase):
    _ANALYZE_OK = (
        "Startup finished in 3.891s (kernel) + 12.345s (userspace) = 16.236s\n"
        "graphical.target reached after 12.123s in userspace\n"
    )
    _ANALYZE_SLOW = (
        "Startup finished in 3.891s (kernel) + 80s (userspace) = 83.891s\n"
    )
    _BLAME_OUTPUT = (
        "  45.123s NetworkManager-wait-online.service\n"
        "  12.456s snapd.service\n"
    )

    def _fake_run(self, ok_output, blame_output=""):
        call_count = [0]

        def side_effect(args, timeout=10.0, **kwargs):
            call_count[0] += 1
            if "blame" in args:
                return CommandResult(0, blame_output, "")
            return CommandResult(0, ok_output, "")

        return side_effect

    def test_pass_when_boot_fast(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.run_command",
            side_effect=self._fake_run(self._ANALYZE_OK, self._BLAME_OUTPUT),
        ):
            results = probe._check_boot()
        boot_result = next(r for r in results if r.item_name == "Boot Time")
        self.assertEqual(boot_result.status, Status.PASS)
        self.assertAlmostEqual(boot_result.metrics["boot_time_s"], 16.2, delta=0.2)

    def test_warn_when_boot_slow(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.run_command",
            side_effect=self._fake_run(self._ANALYZE_SLOW),
        ):
            results = probe._check_boot()
        boot_result = next(r for r in results if r.item_name == "Boot Time")
        self.assertEqual(boot_result.status, Status.WARN)
        self.assertEqual(boot_result.error_code, "INFRA_BOOT_SLOW")

    def test_skips_when_systemd_analyze_unavailable(self):
        probe = _probe()
        with patch(
            "src.probe.software.system_probe.run_command",
            return_value=CommandResult(1, "", "not found"),
        ):
            results = probe._check_boot()
        self.assertEqual(results, [])


# ─── Kernel crash dump detection ─────────────────────────────────────────────


class KernelCrashTests(unittest.TestCase):
    def test_pass_when_no_crash_dirs(self):
        probe = _probe()
        with patch("src.probe.software.system_probe.os.path.isdir", return_value=False):
            results = probe._check_kernel_crash()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, Status.PASS)

    def test_warn_when_crash_dumps_found(self):
        probe = _probe()
        fake_entry = MagicMock()
        fake_entry.path = "/var/crash/vmcore"
        fake_entry.is_file.return_value = True
        fake_entry.is_dir.return_value = False

        def fake_isdir(path):
            return path == "/var/crash"

        with patch(
            "src.probe.software.system_probe.os.path.isdir", side_effect=fake_isdir
        ), patch(
            "src.probe.software.system_probe.os.scandir", return_value=[fake_entry]
        ):
            results = probe._check_kernel_crash()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, Status.WARN)
        self.assertEqual(results[0].error_code, "INFRA_CRASH_DUMP_FOUND")
        self.assertIn("/var/crash/vmcore", results[0].message)


if __name__ == "__main__":
    unittest.main()
