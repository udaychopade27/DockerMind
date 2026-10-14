import os
import shutil
import time

_prev_cpu_total = 0.0
_prev_cpu_idle = 0.0

def get_master_host_stats() -> dict:
    """
    Compute host-level CPU, Memory, and Disk usage metrics for Master node.
    Uses Linux /proc filesystem and standard libraries for 0ms overhead.
    """
    global _prev_cpu_total, _prev_cpu_idle

    # 1. Disk usage
    try:
        total, used, free = shutil.disk_usage('/')
        disk_total_gb = round(total / (1024**3), 1)
        disk_used_gb = round(used / (1024**3), 1)
        disk_pct = round((used / total) * 100, 1) if total > 0 else 0.0
    except Exception:
        disk_total_gb, disk_used_gb, disk_pct = 0.0, 0.0, 0.0

    # 2. Host Memory via /proc/meminfo
    mem_total_gb, mem_used_gb, mem_pct = 0.0, 0.0, 0.0
    try:
        mem_total_kb = 0.0
        mem_avail_kb = 0.0
        if os.path.exists('/proc/meminfo'):
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        if parts[0] == 'MemTotal:':
                            mem_total_kb = float(parts[1])
                        elif parts[0] == 'MemAvailable:':
                            mem_avail_kb = float(parts[1])
            if mem_total_kb > 0:
                mem_used_kb = mem_total_kb - mem_avail_kb
                mem_total_gb = round(mem_total_kb / (1024**2), 1)
                mem_used_gb = round(mem_used_kb / (1024**2), 1)
                mem_pct = round((mem_used_kb / mem_total_kb) * 100, 1)
    except Exception:
        pass

    # 3. Host CPU via /proc/stat delta
    cpu_pct = 0.0
    try:
        if os.path.exists('/proc/stat'):
            with open('/proc/stat', 'r') as f:
                first_line = f.readline()
                parts = first_line.split()
                if parts and parts[0] == 'cpu':
                    values = [float(v) for v in parts[1:]]
                    total = sum(values)
                    idle = values[3] if len(values) > 3 else 0.0
                    if _prev_cpu_total > 0 and total > _prev_cpu_total:
                        total_delta = total - _prev_cpu_total
                        idle_delta = idle - _prev_cpu_idle
                        cpu_pct = round((1.0 - (idle_delta / total_delta)) * 100, 1)
                    _prev_cpu_total = total
                    _prev_cpu_idle = idle
    except Exception:
        pass

    return {
        "cpu_pct": cpu_pct,
        "mem_used_gb": mem_used_gb,
        "mem_total_gb": mem_total_gb,
        "mem_pct": mem_pct,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "disk_pct": disk_pct,
    }
