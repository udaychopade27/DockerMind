import time
from fastapi import APIRouter, Response
from slave_registry import registry
from services.host_metrics import get_master_host_stats
from services.crash_detector import crash_detector
from services.heal_engine import heal_engine
from models.alerts import alert_store
import docker_ops

router = APIRouter(tags=["metrics"])


@router.get("/metrics", summary="Prometheus Metrics Exporter (Standard exposition format)")
async def prometheus_metrics():
    """
    Exposes real-time DockerMind cluster, container, and AI SRE metrics in
    standard Prometheus text exposition format (text/plain; version=0.0.4).
    Compatible with Prometheus, Grafana Agent, Datadog, and OpenTelemetry Collectors.
    """
    lines = []

    def add_line(text=""):
        lines.append(text)

    # 1. Platform Liveness
    add_line("# HELP dockermind_up Whether the DockerMind Master controller is running")
    add_line("# TYPE dockermind_up gauge")
    add_line("dockermind_up 1")
    add_line()

    # 2. Slaves & Cluster Fleet
    slave_counts = registry.count()
    add_line("# HELP dockermind_slaves_total Total number of registered edge slave nodes by status")
    add_line("# TYPE dockermind_slaves_total gauge")
    add_line(f'dockermind_slaves_total{{status="online"}} {slave_counts.get("online", 0)}')
    add_line(f'dockermind_slaves_total{{status="offline"}} {slave_counts.get("offline", 0)}')
    add_line()

    # 3. Node Host Health Metrics (CPU, Memory, Disk)
    add_line("# HELP dockermind_node_cpu_usage_pct Node CPU utilization percentage")
    add_line("# TYPE dockermind_node_cpu_usage_pct gauge")

    # Master node host stats
    master_stats = get_master_host_stats()
    master_cpu = master_stats.get("cpu_pct", 0.0)
    add_line(f'dockermind_node_cpu_usage_pct{{node="master"}} {master_cpu}')

    # Edge slaves host stats
    all_slaves = registry.all()
    for s in all_slaves:
        s_id = s.get("slave_id", "unknown")
        s_cpu = s.get("host_stats", {}).get("cpu_pct", 0.0)
        add_line(f'dockermind_node_cpu_usage_pct{{node="{s_id}"}} {s_cpu}')
    add_line()

    # Node Memory Used (Bytes)
    add_line("# HELP dockermind_node_memory_used_bytes Node physical RAM currently used in bytes")
    add_line("# TYPE dockermind_node_memory_used_bytes gauge")
    master_mem_used = int(master_stats.get("mem_used_gb", 0.0) * (1024**3))
    add_line(f'dockermind_node_memory_used_bytes{{node="master"}} {master_mem_used}')
    for s in all_slaves:
        s_id = s.get("slave_id", "unknown")
        s_mem_used = int(s.get("host_stats", {}).get("mem_used_gb", 0.0) * (1024**3))
        add_line(f'dockermind_node_memory_used_bytes{{node="{s_id}"}} {s_mem_used}')
    add_line()

    # Node Memory Total (Bytes)
    add_line("# HELP dockermind_node_memory_total_bytes Node physical RAM capacity in bytes")
    add_line("# TYPE dockermind_node_memory_total_bytes gauge")
    master_mem_total = int(master_stats.get("mem_total_gb", 0.0) * (1024**3))
    add_line(f'dockermind_node_memory_total_bytes{{node="master"}} {master_mem_total}')
    for s in all_slaves:
        s_id = s.get("slave_id", "unknown")
        s_mem_total = int(s.get("host_stats", {}).get("mem_total_gb", 0.0) * (1024**3))
        add_line(f'dockermind_node_memory_total_bytes{{node="{s_id}"}} {s_mem_total}')
    add_line()

    # Node Disk Used Pct
    add_line("# HELP dockermind_node_disk_used_pct Node disk space utilization percentage")
    add_line("# TYPE dockermind_node_disk_used_pct gauge")
    add_line(f'dockermind_node_disk_used_pct{{node="master"}} {master_stats.get("disk_pct", 0.0)}')
    for s in all_slaves:
        s_id = s.get("slave_id", "unknown")
        s_disk_pct = s.get("host_stats", {}).get("disk_pct", 0.0)
        add_line(f'dockermind_node_disk_used_pct{{node="{s_id}"}} {s_disk_pct}')
    add_line()

    # 4. Container Infrastructure (True RSS, CPU, Status, Restarts)
    add_line("# HELP dockermind_containers_total Number of monitored containers by node and state")
    add_line("# TYPE dockermind_containers_total gauge")

    running_count = 0
    exited_count = 0
    paused_count = 0

    containers = []
    try:
        containers = docker_ops.list_containers(all_containers=True, include_stats=True)
    except Exception:
        pass

    for c in containers:
        st = c.get("status", "unknown").lower()
        if st == "running":
            running_count += 1
        elif st in ("exited", "dead"):
            exited_count += 1
        elif st == "paused":
            paused_count += 1

    add_line(f'dockermind_containers_total{{node="master",status="running"}} {running_count}')
    add_line(f'dockermind_containers_total{{node="master",status="exited"}} {exited_count}')
    add_line(f'dockermind_containers_total{{node="master",status="paused"}} {paused_count}')

    for s in all_slaves:
        s_id = s.get("slave_id", "unknown")
        s_c_total = s.get("container_count", 0)
        add_line(f'dockermind_containers_total{{node="{s_id}",status="running"}} {s_c_total}')
    add_line()

    # Container Metrics (Per Container RSS & CPU)
    add_line("# HELP dockermind_container_memory_rss_bytes True RSS Memory consumed by container (inactive cache subtracted)")
    add_line("# TYPE dockermind_container_memory_rss_bytes gauge")
    for c in containers:
        c_name = c.get("name", "unknown")
        mem_mb = c.get("stats", {}).get("mem_used_mb", 0.0)
        mem_bytes = int(mem_mb * 1024 * 1024)
        add_line(f'dockermind_container_memory_rss_bytes{{node="master",container="{c_name}"}} {mem_bytes}')
    add_line()

    add_line("# HELP dockermind_container_cpu_usage_pct Real-time container CPU usage percentage")
    add_line("# TYPE dockermind_container_cpu_usage_pct gauge")
    for c in containers:
        c_name = c.get("name", "unknown")
        cpu_pct = c.get("stats", {}).get("cpu_pct", 0.0)
        add_line(f'dockermind_container_cpu_usage_pct{{node="master",container="{c_name}"}} {cpu_pct}')
    add_line()

    # 5. SRE Telemetry & Crash Loop Detectors
    add_line("# HELP dockermind_crashloop_active Indicator whether a container is in an active crash loop (1 = crashing, 0 = healthy)")
    add_line("# TYPE dockermind_crashloop_active gauge")
    crash_loops = {f"{cl['slave_id']}:{cl['container']}": cl for cl in crash_detector.summary()}

    for c in containers:
        c_name = c.get("name", "unknown")
        key = f"master:{c_name}"
        key_local = f"local:{c_name}"
        is_loop = 1 if (key in crash_loops or key_local in crash_loops) else 0
        add_line(f'dockermind_crashloop_active{{node="master",container="{c_name}"}} {is_loop}')
    add_line()

    # Circuit Breaker Status
    add_line("# HELP dockermind_circuit_breaker_active Indicator whether auto-restart circuit breaker is tripped (1 = tripped, 0 = active)")
    add_line("# TYPE dockermind_circuit_breaker_active gauge")
    for c in containers:
        c_name = c.get("name", "unknown")
        tripped = 1 if heal_engine.is_circuit_broken("master", c_name) or heal_engine.is_circuit_broken("local", c_name) else 0
        add_line(f'dockermind_circuit_breaker_active{{node="master",container="{c_name}"}} {tripped}')
    add_line()

    # 6. SRE Incident Alerts Summary
    add_line("# HELP dockermind_alerts_active_total Active alerts by severity tier")
    add_line("# TYPE dockermind_alerts_active_total gauge")
    alert_counts = alert_store.counts()
    add_line(f'dockermind_alerts_active_total{{severity="critical"}} {alert_counts.get("critical", 0)}')
    add_line(f'dockermind_alerts_active_total{{severity="error"}} {alert_counts.get("error", 0)}')
    add_line(f'dockermind_alerts_active_total{{severity="warn"}} {alert_counts.get("warn", 0)}')
    add_line(f'dockermind_alerts_active_total{{severity="ok"}} {alert_counts.get("ok", 0)}')
    add_line()

    add_line("# HELP dockermind_alerts_unhealed_total Total number of unresolved error and critical incidents")
    add_line("# TYPE dockermind_alerts_unhealed_total gauge")
    add_line(f'dockermind_alerts_unhealed_total {alert_counts.get("unhealed", 0)}')
    add_line()

    payload = "\n".join(lines) + "\n"
    return Response(content=payload, media_type="text/plain; version=0.0.4; charset=utf-8")
