from __future__ import annotations

import math
import threading
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, DefaultDict, Dict, Iterable, List, Optional, Tuple

import psutil
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget


@dataclass
class _Sample:
    timestamp: datetime
    cpu_percent: float
    memory_bytes: int
    memory_percent: float
    gpu_bytes: Optional[int] = None
    gpu_percent: Optional[float] = None


@dataclass
class _EventRecord:
    timestamp: datetime
    duration: float


class _GPUHelper:
    def __init__(self, pid: int):
        self._pid = pid
        self._nvml = None
        self._available = False
        self._init_nvml()

    def _init_nvml(self) -> None:
        try:
            import pynvml  # type: ignore
        except Exception:
            return

        try:
            pynvml.nvmlInit()
        except Exception:
            return

        self._nvml = pynvml
        self._available = True

    def is_available(self) -> bool:
        return self._available and self._nvml is not None

    def sample(self) -> Tuple[Optional[int], Optional[float]]:
        if not self.is_available():
            return None, None

        assert self._nvml is not None
        pynvml = self._nvml
        try:
            device_count = pynvml.nvmlDeviceGetCount()
        except Exception:
            return None, None

        total_gpu_bytes = 0
        used_gpu_bytes = 0

        for idx in range(device_count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
            except Exception:
                continue

            try:
                processes = pynvml.nvmlDeviceGetGraphicsRunningProcesses_v2(handle)
            except Exception:
                processes = []

            proc_usage = 0
            for proc in processes:
                if getattr(proc, "pid", None) == self._pid:
                    proc_usage += getattr(proc, "usedGpuMemory", 0)

            used_gpu_bytes += proc_usage

            try:
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            except Exception:
                continue

            total_gpu_bytes += getattr(mem_info, "total", 0)

        if total_gpu_bytes <= 0:
            percent = None
        else:
            percent = (used_gpu_bytes / float(total_gpu_bytes)) * 100.0

        return used_gpu_bytes or None, percent

    def shutdown(self) -> None:
        if not self.is_available():
            return

        assert self._nvml is not None
        try:
            self._nvml.nvmlShutdown()
        except Exception:
            pass
        finally:
            self._available = False
            self._nvml = None


class ResourceMonitor(QObject):
    """Track application resource usage and operational timings."""

    stats_updated = Signal(str)

    def __init__(
        self,
        parent: Optional[QObject] = None,
        sample_interval_ms: int = 1000,
        prompt_on_exit: bool = True,
    ) -> None:
        super().__init__(parent)
        self._process = psutil.Process()
        self._pid = self._process.pid
        self._samples: List[_Sample] = []
        self._events: DefaultDict[str, List[_EventRecord]] = defaultdict(list)
        self._counts: DefaultDict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._timer = QTimer(self)
        self._timer.setInterval(sample_interval_ms)
        self._timer.timeout.connect(self._collect_sample)
        self._latest_summary: str = ""
        self._start_time = datetime.now()
        self._report_saved = False
        self._prompt_on_exit = prompt_on_exit
        self._gpu_helper = _GPUHelper(self._pid)
        # Prime CPU measurement to avoid the first 0.0 reading.
        try:
            self._process.cpu_percent(None)
        except Exception:
            pass

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def shutdown(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self._gpu_helper.shutdown()

    def prepare_shutdown(
        self,
        parent: Optional[QObject] = None,
        *,
        on_disable: Optional[Callable[[bool], None]] = None,
    ) -> bool:
        """Ask the user about saving the report before shutdown."""

        if self._report_saved:
            return True

        if not self._prompt_on_exit:
            self.shutdown()
            self._report_saved = True
            return True

        default_name = f"SlipSnap-usage-{datetime.now():%Y%m%d-%H%M%S}.txt"
        default_path = Path.home() / default_name
        widget_parent = parent if isinstance(parent, QWidget) else None

        message_box = QMessageBox(widget_parent)
        message_box.setWindowTitle("SlipSnap")
        message_box.setIcon(QMessageBox.Question)
        message_box.setText("Сохранить отчёт о работе SlipSnap?")
        _save_button = message_box.addButton("Сохранить…", QMessageBox.AcceptRole)
        skip_button = message_box.addButton("Пропустить", QMessageBox.DestructiveRole)
        disable_button = message_box.addButton(
            "Больше не спрашивать",
            QMessageBox.RejectRole,
        )
        cancel_button = message_box.addButton(QMessageBox.Cancel)
        message_box.exec()

        clicked = message_box.clickedButton()
        if clicked == cancel_button:
            return False

        if clicked == disable_button:
            self._prompt_on_exit = False
            self._report_saved = True
            self.shutdown()
            if on_disable is not None:
                on_disable(True)
            return True

        if clicked == skip_button:
            self.shutdown()
            self._report_saved = True
            return True

        path, _ = QFileDialog.getSaveFileName(
            widget_parent,
            "Сохранить отчёт о работе SlipSnap",
            str(default_path),
            "Text files (*.txt);;All files (*)",
        )

        if not path:
            return False

        was_active = self._timer.isActive()
        if was_active:
            self._timer.stop()
        report = self.generate_report()
        try:
            Path(path).write_text(report, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(widget_parent, "SlipSnap", f"Не удалось сохранить отчёт: {exc}")
            # Resume monitoring so the user can try again later.
            if was_active:
                self._timer.start()
            return False

        self.shutdown()
        self._report_saved = True
        return True

    def increment_counter(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counts[name] += amount

    def record_event_duration(self, name: str, duration: float) -> None:
        with self._lock:
            self._events[name].append(_EventRecord(datetime.now(), duration))

    @contextmanager
    def measure(self, name: str) -> Iterable[None]:
        start = datetime.now()
        try:
            yield
        finally:
            duration = (datetime.now() - start).total_seconds()
            self.record_event_duration(name, duration)

    @property
    def latest_summary(self) -> str:
        return self._latest_summary

    def _collect_sample(self) -> None:
        timestamp = datetime.now()
        try:
            cpu = self._process.cpu_percent(None)
        except Exception:
            cpu = 0.0

        try:
            mem_info = self._process.memory_info()
            mem_percent = self._process.memory_percent()
            rss = getattr(mem_info, "rss", 0)
        except Exception:
            mem_percent = 0.0
            rss = 0

        gpu_bytes: Optional[int]
        gpu_percent: Optional[float]
        gpu_bytes, gpu_percent = self._gpu_helper.sample()

        sample = _Sample(
            timestamp=timestamp,
            cpu_percent=cpu,
            memory_bytes=rss,
            memory_percent=mem_percent,
            gpu_bytes=gpu_bytes,
            gpu_percent=gpu_percent,
        )

        with self._lock:
            self._samples.append(sample)
            if len(self._samples) > 3600 * 24:
                self._samples = self._samples[-3600 * 24 :]

        self._latest_summary = self._format_short_summary(sample)
        self.stats_updated.emit(self._latest_summary)

    def _format_short_summary(self, sample: _Sample) -> str:
        parts = [f"CPU: {sample.cpu_percent:.1f}%", f"RAM: {self._format_bytes(sample.memory_bytes)}"]
        if sample.gpu_bytes is not None:
            parts.append(f"GPU: {self._format_bytes(sample.gpu_bytes)}")
        return " • ".join(parts)

    def generate_report(self) -> str:
        with self._lock:
            samples = list(self._samples)
            events = {k: list(v) for k, v in self._events.items()}
            counts = dict(self._counts)

        lines: List[str] = []
        now = datetime.now()
        uptime = now - self._start_time
        lines.append("SlipSnap — отчёт о ресурсах")
        lines.append(f"Сгенерировано: {now:%Y-%m-%d %H:%M:%S}")
        lines.append(f"Время работы: {self._format_timedelta(uptime)}")
        lines.append("")

        if samples:
            lines.extend(self._build_resource_section(samples))
        else:
            lines.append("Нет собранных данных об использовании ресурсов.")
            lines.append("")

        if events:
            lines.extend(self._build_event_section(events))
        else:
            lines.append("Нет зарегистрированных событий производительности.")
            lines.append("")

        if counts:
            lines.extend(self._build_counter_section(counts))
        else:
            lines.append("Нет зарегистрированных счетчиков действий.")

        return "\n".join(lines).strip() + "\n"

    def _build_resource_section(self, samples: List[_Sample]) -> List[str]:
        lines = ["Использование ресурсов:"]
        cpu_values = [
            (s.cpu_percent, s.timestamp, s.cpu_percent)
            for s in samples
        ]
        mem_values = [(s.memory_bytes, s.timestamp, s.memory_percent) for s in samples]
        gpu_values = [
            (s.gpu_bytes, s.timestamp, s.gpu_percent)
            for s in samples
            if s.gpu_bytes is not None
        ]

        lines.append(
            self._describe_series(
                "CPU",
                cpu_values,
                unit="%",
                percent_index=2,
            )
        )
        lines.append(
            self._describe_series(
                "RAM",
                mem_values,
                unit="байт",
                formatter=lambda v: self._format_bytes(int(v)),
                percent_index=2,
            )
        )

        if gpu_values:
            lines.append(
                self._describe_series(
                    "GPU память",
                    gpu_values,
                    unit="байт",
                    formatter=lambda v: self._format_bytes(int(v)),
                    percent_index=2,
                )
            )
        else:
            lines.append("GPU память: данные недоступны")

        lines.append("")
        return lines

    def _describe_series(
        self,
        label: str,
        values: Iterable[Tuple[float, datetime, Optional[float]]],
        unit: str,
        formatter: Optional[Callable[[float], str]] = None,
        percent_index: int = 1,
    ) -> str:
        data = list(values)
        numeric_values = [v for v, *_ in data if v is not None]
        if not numeric_values:
            return f"{label}: данные недоступны"

        formatter = formatter or (lambda v: f"{v:.2f}{unit}")
        avg = sum(numeric_values) / len(numeric_values)
        min_val = min(data, key=lambda x: x[0])
        max_val = max(data, key=lambda x: x[0])

        parts = [
            f"{label}: среднее {formatter(avg)}",
            f"минимум {formatter(min_val[0])} в {min_val[1]:%H:%M:%S}",
            f"максимум {formatter(max_val[0])} в {max_val[1]:%H:%M:%S}",
        ]

        percent_values: List[float] = []
        for value in data:
            if len(value) > percent_index and value[percent_index] is not None:
                percent_values.append(float(value[percent_index]))

        if percent_values:
            avg_percent = sum(percent_values) / len(percent_values)
            max_percent = max(percent_values)
            parts.append(f"средняя загрузка {avg_percent:.1f}%, пик {max_percent:.1f}%")

        return "; ".join(parts)

    def _build_event_section(self, events: Dict[str, List[_EventRecord]]) -> List[str]:
        lines = ["События производительности:"]
        for name in sorted(events):
            records = events[name]
            durations = [rec.duration for rec in records]
            avg = sum(durations) / len(durations)
            fastest = min(records, key=lambda r: r.duration)
            slowest = max(records, key=lambda r: r.duration)
            lines.append(
                f"- {name}: {len(records)} раз, среднее {avg:.3f}s, "
                f"минимум {fastest.duration:.3f}s ({fastest.timestamp:%H:%M:%S}), "
                f"максимум {slowest.duration:.3f}s ({slowest.timestamp:%H:%M:%S})"
            )
        lines.append("")
        return lines

    def _build_counter_section(self, counts: Dict[str, int]) -> List[str]:
        lines = ["Счетчики действий:"]
        for name in sorted(counts):
            lines.append(f"- {name}: {counts[name]}")
        return lines

    @staticmethod
    def _format_bytes(value: int) -> str:
        if value <= 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        order = min(len(units) - 1, int(math.log(value, 1024)))
        scaled = value / (1024 ** order)
        return f"{scaled:.1f} {units[order]}"

    @staticmethod
    def _format_timedelta(delta: timedelta) -> str:
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if hours:
            parts.append(f"{hours} ч")
        if minutes:
            parts.append(f"{minutes} мин")
        parts.append(f"{seconds} с")
        return " ".join(parts)
