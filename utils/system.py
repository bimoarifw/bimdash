import os
import platform
import subprocess
import threading
import time
from datetime import datetime

import psutil

from .cache import cached

def get_os_info():
    """Get OS name and version for Linux systems"""
    # Check if we're in a container and have host OS info
    host_etc = os.environ.get('HOST_ETC', '/host/etc')
    
    # Try lsb-release first (Ubuntu/Debian)
    lsb_file = os.path.join(host_etc, 'lsb-release')
    if os.path.exists(lsb_file):
        try:
            with open(lsb_file, 'r') as f:
                for line in f:
                    if line.startswith('DISTRIB_DESCRIPTION='):
                        os_name = line.split('=', 1)[1].strip().strip('"')
                        return os_name
        except (OSError, IOError):
            pass
    
    # Try os-release
    host_os_file = os.path.join(host_etc, 'os-release')
    if os.path.exists(host_os_file):
        try:
            with open(host_os_file, 'r') as f:
                for line in f:
                    if line.startswith('PRETTY_NAME='):
                        os_name = line.split('=', 1)[1].strip().strip('"')
                        return os_name
        except (OSError, IOError):
            pass
    
    # Read from container's /etc/os-release (fallback)
    try:
        with open('/etc/os-release', 'r') as f:
            for line in f:
                if line.startswith('PRETTY_NAME='):
                    os_name = line.split('=', 1)[1].strip().strip('"')
                    return os_name
    except (OSError, IOError):
        pass
    
    # Fallback
    return "Ubuntu Server"

def get_system_info():
    """Get basic system information"""
    # Try to get processor info from /proc/cpuinfo
    processor = platform.processor()
    if not processor:
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('model name'):
                        processor = line.split(':')[1].strip()
                        break
        except (OSError, IOError):
            processor = 'Unknown'

    # Try to get host hostname
    hostname = platform.node()
    try:
        # Try to get from host /etc/hostname
        host_etc = os.environ.get('HOST_ETC')
        if host_etc:
            hostname_file = os.path.join(host_etc, 'hostname')
            if os.path.exists(hostname_file):
                with open(hostname_file, 'r') as f:
                    hostname = f.read().strip()
    except:
        pass

    return {
        'hostname': hostname,
        'os': get_os_info(),
        'os_version': platform.version(),
        'architecture': platform.machine(),
        'processor': processor,
        'cpu_count': psutil.cpu_count(),
        'cpu_count_logical': psutil.cpu_count(logical=True)
    }

_cpu_prime_lock = threading.Lock()
_cpu_prime_done = False


def prime_cpu_percent() -> None:
    """Prime psutil CPU percentage calculations to avoid initial zero readings."""
    global _cpu_prime_done
    if _cpu_prime_done:
        return
    with _cpu_prime_lock:
        if _cpu_prime_done:
            return
        host_proc = os.environ.get('HOST_PROC')
        if host_proc:
            psutil.PROCFS_PATH = host_proc
        # First invocation primes psutil's internal counters without blocking
        psutil.cpu_percent(interval=None, percpu=True)
        _cpu_prime_done = True


def get_cpu_info():
    """Get detailed CPU information without blocking the request thread."""
    host_proc = os.environ.get('HOST_PROC')
    if host_proc:
        psutil.PROCFS_PATH = host_proc

    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    if not cpu_per_core:
        cpu_per_core = [0.0] * psutil.cpu_count() if psutil.cpu_count() else [0.0]

    overall_percent = sum(cpu_per_core) / len(cpu_per_core) if cpu_per_core else 0.0

    cpu_freq = psutil.cpu_freq()

    return {
        'overall_percent': round(overall_percent, 2),
        'per_core_percent': [round(value, 2) for value in cpu_per_core],
        'frequency_current': round(cpu_freq.current, 2) if cpu_freq else None,
        'frequency_min': round(cpu_freq.min, 2) if cpu_freq else None,
        'frequency_max': round(cpu_freq.max, 2) if cpu_freq else None
    }

def get_memory_info():
    """Get detailed memory information"""
    virtual_memory = psutil.virtual_memory()
    swap_memory = psutil.swap_memory()

    return {
        'virtual': {
            'total': virtual_memory.total,
            'available': virtual_memory.available,
            'used': virtual_memory.used,
            'percent': virtual_memory.percent,
            'total_gb': round(virtual_memory.total / (1024**3), 2),
            'used_gb': round(virtual_memory.used / (1024**3), 2),
            'available_gb': round(virtual_memory.available / (1024**3), 2)
        },
        'swap': {
            'total': swap_memory.total,
            'used': swap_memory.used,
            'free': swap_memory.free,
            'percent': swap_memory.percent,
            'total_gb': round(swap_memory.total / (1024**3), 2),
            'used_gb': round(swap_memory.used / (1024**3), 2)
        }
    }

@cached(2)  # Cache disk info for 2 seconds
def get_disk_info():
    """Get disk information from host system"""
    host_proc = os.environ.get('HOST_PROC')
    host_sys = os.environ.get('HOST_SYS')
    if host_proc:
        psutil.PROCFS_PATH = host_proc

    # Get device models from /sys/block
    device_models = {}
    if host_sys:
        block_devices_path = os.path.join(host_sys, 'block')
        if os.path.exists(block_devices_path):
            for device_dir in os.listdir(block_devices_path):
                device_path = os.path.join(block_devices_path, device_dir)
                model_file = os.path.join(device_path, 'device', 'model')

                # Only check physical devices (not partitions like sda1, sdb1, etc.)
                if os.path.exists(model_file) and not any(char.isdigit() for char in device_dir):
                    try:
                        with open(model_file, 'r') as f:
                            model = f.read().strip()
                            device_models[f'/dev/{device_dir}'] = model
                    except (OSError, IOError):
                        pass

    # Also try lsblk as fallback for devices not found in /sys
    try:
        result = subprocess.run(['lsblk', '-do', 'NAME,MODEL', '-n'], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2 and not any(char.isdigit() for char in parts[0]):
                        device_name = f'/dev/{parts[0]}'
                        model = ' '.join(parts[1:])
                        device_models[device_name] = model
    except:
        pass

    partitions = []

    # Only add mounted partitions that we can get usage info for
    seen_devices = set()
    for part in psutil.disk_partitions():
        # Skip virtual filesystems, docker overlays, and irrelevant mountpoints
        if ('squashfs' in part.fstype or 'tmpfs' in part.fstype or 'devtmpfs' in part.fstype or
            'proc' in part.fstype or 'sysfs' in part.fstype or 'devpts' in part.fstype or
            'cgroup' in part.fstype or 'overlay' in part.fstype or 'efivarfs' in part.fstype or
            'fuse' in part.fstype or not part.mountpoint.startswith('/') or
            'docker' in part.mountpoint or 'containerd' in part.mountpoint):
            continue
        
        # Skip if we've already seen this device
        if part.device in seen_devices:
            continue

        try:
            usage = psutil.disk_usage(part.mountpoint)

            # Try to get disk model/label
            model = 'Unknown'
            device_to_check = part.device

            # For device mapper (LVM) or other virtual devices, find the underlying physical device
            if 'mapper' in part.device or 'dm-' in part.device:
                # Try to find physical device using various methods
                try:
                    # Method 1: Use lsblk to find parent
                    result = subprocess.run(['lsblk', '-no', 'PKNAME', part.device], capture_output=True, text=True)
                    if result.returncode == 0 and result.stdout.strip():
                        parent_device = f'/dev/{result.stdout.strip()}'
                        if parent_device in device_models:
                            model = device_models[parent_device]
                except:
                    pass

                # Method 2: Check if we can map common patterns
                if model == 'Unknown':
                    # For LVM logical volumes, try to find the physical volume
                    try:
                        # Get the VG name from LV name
                        if 'ubuntu--vg-ubuntu--lv' in part.device:
                            # Common Ubuntu LVM setup - try to find which physical device backs it
                            for phys_dev in ['/dev/sda', '/dev/sdb', '/dev/nvme0n1', '/dev/vda']:
                                if phys_dev in device_models:
                                    model = device_models[phys_dev]
                                    break
                    except:
                        pass
            else:
                # For regular partitions, find the parent physical device
                # Remove partition number (e.g., /dev/sda1 -> /dev/sda)
                parent_device = part.device.rstrip('0123456789')
                if parent_device in device_models:
                    model = device_models[parent_device]
                elif part.device in device_models:
                    model = device_models[part.device]

            partitions.append({
                'device': part.device,
                'model': model,
                'mountpoint': part.mountpoint,
                'fstype': part.fstype,
                'opts': part.opts,
                'total': usage.total,
                'used': usage.used,
                'free': usage.free,
                'percent': usage.percent,
                'total_gb': round(usage.total / (1024**3), 2),
                'used_gb': round(usage.used / (1024**3), 2),
                'free_gb': round(usage.free / (1024**3), 2)
            })
            seen_devices.add(part.device)
        except (PermissionError, OSError):
            continue

    # Sort by mountpoint for consistency (root first, then others)
    partitions.sort(key=lambda x: (x['mountpoint'] != '/', x['mountpoint']))

    return {
        'partitions': partitions,
    }

def get_network_stats():
    """Get network statistics from host system"""
    host_sys = os.environ.get('HOST_SYS')

    # Try to read from host /sys/class/net/*/statistics/ for accurate host statistics
    if host_sys:
        net_class_path = os.path.join(host_sys, 'class', 'net')
        if os.path.exists(net_class_path):
            try:
                total_bytes_recv = 0
                total_bytes_sent = 0
                total_packets_recv = 0
                total_packets_sent = 0
                total_errin = 0
                total_errout = 0
                total_dropin = 0
                total_dropout = 0

                for interface in os.listdir(net_class_path):
                    # Skip loopback, docker bridges, and virtual interfaces
                    if (interface.startswith('lo') or interface.startswith('docker') or
                        interface.startswith('veth') or interface.startswith('br-')):
                        continue

                    stats_path = os.path.join(net_class_path, interface, 'statistics')
                    if os.path.exists(stats_path):
                        try:
                            with open(os.path.join(stats_path, 'rx_bytes'), 'r') as f:
                                bytes_recv = int(f.read().strip())
                            with open(os.path.join(stats_path, 'tx_bytes'), 'r') as f:
                                bytes_sent = int(f.read().strip())
                            with open(os.path.join(stats_path, 'rx_packets'), 'r') as f:
                                packets_recv = int(f.read().strip())
                            with open(os.path.join(stats_path, 'tx_packets'), 'r') as f:
                                packets_sent = int(f.read().strip())
                            with open(os.path.join(stats_path, 'rx_errors'), 'r') as f:
                                errin = int(f.read().strip())
                            with open(os.path.join(stats_path, 'tx_errors'), 'r') as f:
                                errout = int(f.read().strip())
                            with open(os.path.join(stats_path, 'rx_dropped'), 'r') as f:
                                dropin = int(f.read().strip())
                            with open(os.path.join(stats_path, 'tx_dropped'), 'r') as f:
                                dropout = int(f.read().strip())

                            total_bytes_recv += bytes_recv
                            total_bytes_sent += bytes_sent
                            total_packets_recv += packets_recv
                            total_packets_sent += packets_sent
                            total_errin += errin
                            total_errout += errout
                            total_dropin += dropin
                            total_dropout += dropout
                        except (OSError, IOError, ValueError):
                            continue

                return {
                    'bytes_sent': total_bytes_sent,
                    'bytes_recv': total_bytes_recv,
                    'packets_sent': total_packets_sent,
                    'packets_recv': total_packets_recv,
                    'errin': total_errin,
                    'errout': total_errout,
                    'dropin': total_dropin,
                    'dropout': total_dropout
                }
            except (OSError, IOError):
                pass

    # Fallback to psutil (container stats)
    net_io = psutil.net_io_counters()
    return {
        'bytes_sent': net_io.bytes_sent,
        'bytes_recv': net_io.bytes_recv,
        'packets_sent': net_io.packets_sent,
        'packets_recv': net_io.packets_recv,
        'errin': net_io.errin,
        'errout': net_io.errout,
        'dropin': net_io.dropin,
        'dropout': net_io.dropout
    }

def get_processes(limit: int = 10):
    """Get list of running processes sorted by CPU usage."""
    host_proc = os.environ.get('HOST_PROC')
    if host_proc:
        psutil.PROCFS_PATH = host_proc

    # First pass: get all processes and sort by memory to find candidates
    candidates = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'memory_info', 'status']):
        try:
            memory_mb = proc.info['memory_info'].rss / 1024 / 1024 if proc.info['memory_info'] else 0
            candidates.append({
                'pid': proc.info['pid'],
                'name': proc.info['name'],
                'memory_percent': proc.info['memory_percent'],
                'memory_mb': memory_mb,
                'status': proc.info['status'],
                'proc': proc  # Keep process object for CPU calculation
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort by memory usage and take top 20 candidates
    candidates.sort(key=lambda x: x['memory_percent'], reverse=True)
    top_candidates = candidates[: max(limit * 2, limit + 5)]

    # Second pass: calculate CPU for top candidates only
    processes = []
    for candidate in top_candidates:
        try:
            # Calculate CPU percent without blocking the event loop
            cpu_percent = candidate['proc'].cpu_percent(interval=None)
            processes.append({
                'pid': candidate['pid'],
                'name': candidate['name'],
                'cpu_percent': cpu_percent,
                'memory_percent': candidate['memory_percent'],
                'memory_mb': candidate['memory_mb'],
                'status': candidate['status']
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort by CPU usage descending and return top 10
    processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
    return processes[:limit]

def get_system_uptime():
    """Get system uptime and load average"""
    host_proc = os.environ.get('HOST_PROC')
    if host_proc:
        psutil.PROCFS_PATH = host_proc
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time

    try:
        load_avg = psutil.getloadavg()
    except AttributeError:
        load_avg = None

    return {
        'boot_time': datetime.fromtimestamp(boot_time).strftime('%Y-%m-%d %H:%M:%S'),
        'uptime_seconds': uptime_seconds,
        'uptime_formatted': f"{int(uptime_seconds // 86400)}d {int((uptime_seconds % 86400) // 3600)}h {int((uptime_seconds % 3600) // 60)}m {int(uptime_seconds % 60)}s",
        'load_average': load_avg
    }