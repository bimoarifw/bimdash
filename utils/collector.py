import copy
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .system import (
    get_cpu_info,
    get_disk_info,
    get_memory_info,
    get_network_stats,
    get_processes,
    get_system_info,
    get_system_uptime,
    prime_cpu_percent,
)
from .docker import get_docker_info


def _positive_float(env_key: str, default: float) -> float:
    """Return a positive float from env or fall back to default."""
    try:
        value = float(os.environ.get(env_key, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def _positive_int(env_key: str, default: int) -> int:
    """Return a positive integer from env or fall back to default."""
    try:
        value = int(os.environ.get(env_key, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


class SystemMetricsCollector:
    """Background collector that keeps fresh system metrics snapshots."""

    def __init__(self, interval: Optional[float] = None) -> None:
        self.interval = _positive_float('BIMDASH_METRICS_INTERVAL', interval or 1.0)
        self.disk_interval = _positive_float('BIMDASH_DISK_INTERVAL', max(self.interval, 5.0))
        self.docker_interval = _positive_float('BIMDASH_DOCKER_INTERVAL', max(self.interval, 5.0))
        self.idle_interval = _positive_float('BIMDASH_IDLE_INTERVAL', 30.0)
        self.idle_timeout = _positive_float('BIMDASH_IDLE_TIMEOUT', 5.0)
        self.process_limit = _positive_int('BIMDASH_PROCESS_LIMIT', 10)

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._wake = threading.Event()

        self._metrics: Dict[str, Any] = {}
        self._processes: List[Dict[str, Any]] = []
        self._system_info = get_system_info()
        self._cached_disk = get_disk_info()
        self._cached_docker = get_docker_info()
        self._last_disk_at = 0.0
        self._last_docker_at = 0.0
        self._last_activity = time.time()

        prime_cpu_percent()

        self._thread = threading.Thread(
            target=self._run,
            name='SystemMetricsCollector',
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the collector to stop."""
        self._stop.set()
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1)

    def metrics(self) -> Dict[str, Any]:
        """Return the latest cached metrics snapshot."""
        self._ready.wait()
        with self._lock:
            return copy.deepcopy(self._metrics)

    def processes(self) -> List[Dict[str, Any]]:
        """Return the latest cached process list."""
        self._ready.wait()
        with self._lock:
            return [proc.copy() for proc in self._processes]

    def mark_activity(self) -> None:
        """Record client activity and wake the collector if it is idling."""
        self._last_activity = time.time()
        self._wake.set()

    def _run(self) -> None:
        """Background loop that refreshes metrics on a fixed cadence."""
        while not self._stop.is_set():
            iteration_start = time.time()
            metrics, processes = self._collect_once()
            with self._lock:
                self._metrics = metrics
                self._processes = processes
                self._ready.set()

            elapsed = time.time() - iteration_start
            now = time.time()
            is_active = (now - self._last_activity) <= self.idle_timeout
            target_interval = self.interval if is_active else self.idle_interval
            sleep_duration = max(target_interval - elapsed, 0.05)

            woke_early = self._wake.wait(timeout=sleep_duration)
            if self._stop.is_set():
                break
            if woke_early:
                self._wake.clear()

    def _collect_once(self) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Collect a fresh metrics snapshot along with processes."""
        now = time.time()
        is_active = (now - self._last_activity) <= self.idle_timeout

        # Update disk and docker only when their intervals expire
        if now - self._last_disk_at >= self.disk_interval:
            self._cached_disk = get_disk_info()
            self._last_disk_at = now

        if now - self._last_docker_at >= self.docker_interval:
            self._cached_docker = get_docker_info()
            self._last_docker_at = now

        # When idle, skip expensive CPU/memory/network/process collection
        if not is_active:
            metrics = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'cpu': self._metrics.get('cpu', {}),
                'memory': self._metrics.get('memory', {}),
                'uptime': get_system_uptime(),
                'network': self._metrics.get('network', {}),
                'disk': self._cached_disk,
                'docker': self._cached_docker,
                'system': self._system_info,
            }
            processes = self._processes
            return metrics, processes

        # When active, collect all fresh metrics
        metrics = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'cpu': get_cpu_info(),
            'memory': get_memory_info(),
            'uptime': get_system_uptime(),
            'network': get_network_stats(),
            'disk': self._cached_disk,
            'docker': self._cached_docker,
            'system': self._system_info,
        }

        processes = get_processes(limit=self.process_limit)
        return metrics, processes

    def __del__(self) -> None:
        self.stop()
