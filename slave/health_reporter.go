package main

import (
	"bufio"
	"os"
	"strconv"
	"syscall"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"strings"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/events"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/client"
)

type ContainerStats struct {
	Name       string  `json:"name"`
	CPUPct     float64 `json:"cpu_pct"`
	MemUsedMB  float64 `json:"mem_used_mb"`
	MemLimitMB float64 `json:"mem_limit_mb"`
	MemPct     float64 `json:"mem_pct"`
}

type HostStats struct {
	CPUPct      float64 `json:"cpu_pct"`
	MemUsedGB   float64 `json:"mem_used_gb"`
	MemTotalGB  float64 `json:"mem_total_gb"`
	MemPct      float64 `json:"mem_pct"`
	DiskUsedGB  float64 `json:"disk_used_gb"`
	DiskTotalGB float64 `json:"disk_total_gb"`
	DiskPct     float64 `json:"disk_pct"`
}

type HealthReporter struct {
	cli             *client.Client
	masterClient    *MasterClient
	cfg             Config
	memThresholdPct float64
	streamer        *EventStreamer
	prevCPUTotal    float64
	prevCPUIdle     float64
}

func NewHealthReporter(cli *client.Client, mc *MasterClient, cfg Config, streamer *EventStreamer) *HealthReporter {
	return &HealthReporter{
		cli:             cli,
		masterClient:    mc,
		cfg:             cfg,
		memThresholdPct: 90.0,
		streamer:        streamer,
	}
}

func (h *HealthReporter) Run(ctx context.Context) {
	log.Println("[HealthReporter] Starting")
	go h.watchEvents(ctx)
	go h.pollStats(ctx)
}

func (h *HealthReporter) watchEvents(ctx context.Context) {
	f := filters.NewArgs()
	f.Add("type", "container")

	opts := types.EventsOptions{Filters: f}
	msgCh, errCh := h.cli.Events(ctx, opts)

	for {
		select {
		case <-ctx.Done():
			return
		case err := <-errCh:
			if err != nil && err != io.EOF {
				log.Printf("[HealthReporter] Event stream error: %v — retrying in 5s", err)
				time.Sleep(5 * time.Second)
				msgCh, errCh = h.cli.Events(ctx, opts)
			}
		case msg := <-msgCh:
			h.handleEvent(ctx, msg)
		}
	}
}

func (h *HealthReporter) handleEvent(ctx context.Context, msg events.Message) {
	name := msg.Actor.Attributes["name"]
	action := string(msg.Action)
	cid := msg.Actor.ID

	// Ignore internal dockermind containers (control plane components)
	if strings.HasPrefix(name, "dockermind-") || name == "" {
		return
	}

	switch action {
	case "die":
		exitCode := 0
		if ec, ok := msg.Actor.Attributes["exitCode"]; ok {
			fmt.Sscanf(ec, "%d", &exitCode)
		}
		detail := exitCodeDetail(exitCode)
		log.Printf("[HealthReporter] die: %s (id=%s) exit=%d (%s)", name, cid, exitCode, detail)
		
		if h.streamer != nil {
			h.streamer.Push("die", name, cid, detail, exitCode)
		} else {
			_ = h.masterClient.PushEvent(ctx, "die", name, cid, exitCode, detail)
		}

		// Stream recent logs of dead container to master LLM pipeline immediately
		go func(containerID, containerName string) {
			if strings.HasPrefix(containerName, "dockermind-") {
				return
			}
			lCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			rc, err := h.cli.ContainerLogs(lCtx, containerID, container.LogsOptions{
				ShowStdout: true,
				ShowStderr: true,
				Tail:       "60",
			})
			if err != nil {
				return
			}
			defer rc.Close()
			var out strings.Builder
			sc := bufio.NewScanner(rc)
			for sc.Scan() {
				line := sc.Text()
				if len(line) > 8 {
					line = line[8:]
				}
				out.WriteString(line + "\n")
			}
			logs := out.String()
			if strings.TrimSpace(logs) != "" {
				_ = h.masterClient.PushLogs(lCtx, containerID, containerName, logs)
			}
		}(cid, name)

	case "oom":
		log.Printf("[HealthReporter] OOM kill: %s (id=%s)", name, cid)
		if h.streamer != nil {
			h.streamer.Push("oom", name, cid, "OOM kill — memory limit exceeded", 137)
		} else {
			_ = h.masterClient.PushEvent(ctx, "oom", name, cid, 137, "OOM kill — memory limit exceeded")
		}

	case "start":
		if h.streamer != nil {
			h.streamer.Push("start", name, cid, "", 0)
		} else {
			_ = h.masterClient.PushEvent(ctx, "start", name, cid, 0, "")
		}

	case "stop", "kill":
		if h.streamer != nil {
			h.streamer.Push(action, name, cid, "", 0)
		} else {
			_ = h.masterClient.PushEvent(ctx, action, name, cid, 0, "")
		}
	}
}

func (h *HealthReporter) pollStats(ctx context.Context) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			h.checkAllStats(ctx)
		}
	}
}

func (h *HealthReporter) checkAllStats(ctx context.Context) {
	listCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	containers, err := h.cli.ContainerList(listCtx, container.ListOptions{})
	if err != nil {
		log.Printf("[HealthReporter] ContainerList: %v", err)
		return
	}

	allStats := make([]ContainerStats, 0, len(containers))
	for _, c := range containers {
		name := strings.TrimPrefix(c.Names[0], "/")
		s, err := h.sampleStats(ctx, c.ID, name)
		if err != nil {
			continue
		}
		allStats = append(allStats, s)
		if s.MemPct > h.memThresholdPct {
			detail := fmt.Sprintf("High memory usage: %.1f%% (%.0fMB / %.0fMB) exceeds %.0f%% threshold",
				s.MemPct, s.MemUsedMB, s.MemLimitMB, h.memThresholdPct)
			log.Printf("[HealthReporter] HIGH MEM: %s — %s", name, detail)
			if h.streamer != nil {
				h.streamer.Push("health_fail", name, c.ID, detail, 0)
			} else {
				_ = h.masterClient.PushEvent(ctx, "health_fail", name, c.ID, 0, detail)
			}
		}
	}

	if len(allStats) == 0 {
		return
	}
	hostStats := h.sampleHostStats()
	payload, _ := json.Marshal(map[string]any{
		"slave_id":   h.cfg.SlaveID,
		"stats":      allStats,
		"host_stats": hostStats,
		"ts":         time.Now().Unix(),
	})
	_ = h.masterClient.postRaw(ctx, "/slaves/stats", payload)
}

func (h *HealthReporter) sampleStats(ctx context.Context, id, name string) (ContainerStats, error) {
	sCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	resp, err := h.cli.ContainerStats(sCtx, id, false)
	if err != nil {
		return ContainerStats{}, err
	}
	defer resp.Body.Close()

	var raw types.StatsJSON
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		return ContainerStats{}, err
	}

	cpuDelta := float64(raw.CPUStats.CPUUsage.TotalUsage) - float64(raw.PreCPUStats.CPUUsage.TotalUsage)
	sysDelta := float64(raw.CPUStats.SystemUsage) - float64(raw.PreCPUStats.SystemUsage)
	ncpu := float64(raw.CPUStats.OnlineCPUs)
	if ncpu == 0 {
		ncpu = 1
	}
	cpuPct := 0.0
	if sysDelta > 0 {
		cpuPct = (cpuDelta / sysDelta) * ncpu * 100.0
	}
	usage := raw.MemoryStats.Usage
	// Linux cgroup memory accounting includes inactive page cache in Usage.
	// In cgroups v2, inactive cache is in Stats["inactive_file"].
	// In cgroups v1, it is in Stats["total_inactive_file"].
	// Subtracting this gives the actual RSS/active memory, matching docker stats.
	if raw.MemoryStats.Stats != nil {
		if inactive, ok := raw.MemoryStats.Stats["inactive_file"]; ok && inactive > 0 && usage > inactive {
			usage -= inactive
		} else if totalInactive, ok := raw.MemoryStats.Stats["total_inactive_file"]; ok && totalInactive > 0 && usage > totalInactive {
			usage -= totalInactive
		}
	}
	memUsed := float64(usage) / 1024 / 1024
	memLimit := float64(raw.MemoryStats.Limit) / 1024 / 1024
	memPct := 0.0
	if memLimit > 0 {
		memPct = (memUsed / memLimit) * 100.0
	}
	return ContainerStats{
		Name:       name,
		CPUPct:     r2(cpuPct),
		MemUsedMB:  r2(memUsed),
		MemLimitMB: r2(memLimit),
		MemPct:     r2(memPct),
	}, nil
}


func sampleHostDisk() (usedGB, totalGB, pct float64) {
	var stat syscall.Statfs_t
	if err := syscall.Statfs("/", &stat); err != nil {
		return 0, 0, 0
	}
	totalBytes := float64(stat.Blocks) * float64(stat.Bsize)
	freeBytes := float64(stat.Bfree) * float64(stat.Bsize)
	usedBytes := totalBytes - freeBytes

	totalGB = r2(totalBytes / (1024 * 1024 * 1024))
	usedGB = r2(usedBytes / (1024 * 1024 * 1024))
	if totalGB > 0 {
		pct = r2((usedGB / totalGB) * 100)
	}
	return
}

func sampleHostMem() (usedGB, totalGB, pct float64) {
	file, err := os.Open("/proc/meminfo")
	if err != nil {
		return 0, 0, 0
	}
	defer file.Close()

	var memTotalKB, memAvailKB float64
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		parts := strings.Fields(line)
		if len(parts) >= 2 {
			if parts[0] == "MemTotal:" {
				memTotalKB, _ = strconv.ParseFloat(parts[1], 64)
			} else if parts[0] == "MemAvailable:" {
				memAvailKB, _ = strconv.ParseFloat(parts[1], 64)
			}
		}
	}
	if memTotalKB > 0 {
		memUsedKB := memTotalKB - memAvailKB
		totalGB = r2(memTotalKB / (1024 * 1024))
		usedGB = r2(memUsedKB / (1024 * 1024))
		pct = r2((usedGB / totalGB) * 100)
	}
	return
}

func (h *HealthReporter) sampleHostCPU() float64 {
	data, err := os.ReadFile("/proc/stat")
	if err != nil {
		return 0.0
	}
	lines := strings.Split(string(data), "\n")
	if len(lines) == 0 {
		return 0.0
	}
	fields := strings.Fields(lines[0])
	if len(fields) < 5 || fields[0] != "cpu" {
		return 0.0
	}
	var total, idle float64
	for i := 1; i < len(fields); i++ {
		val, _ := strconv.ParseFloat(fields[i], 64)
		total += val
		if i == 4 {
			idle = val
		}
	}
	if h.prevCPUTotal > 0 && total > h.prevCPUTotal {
		totalDelta := total - h.prevCPUTotal
		idleDelta := idle - h.prevCPUIdle
		cpuPct := (1.0 - (idleDelta / totalDelta)) * 100.0
		h.prevCPUTotal = total
		h.prevCPUIdle = idle
		return r2(cpuPct)
	}
	h.prevCPUTotal = total
	h.prevCPUIdle = idle
	return 0.0
}

func (h *HealthReporter) sampleHostStats() HostStats {
	memUsed, memTotal, memPct := sampleHostMem()
	diskUsed, diskTotal, diskPct := sampleHostDisk()
	cpuPct := h.sampleHostCPU()
	return HostStats{
		CPUPct:      cpuPct,
		MemUsedGB:   memUsed,
		MemTotalGB:  memTotal,
		MemPct:      memPct,
		DiskUsedGB:  diskUsed,
		DiskTotalGB: diskTotal,
		DiskPct:     diskPct,
	}
}

func r2(f float64) float64 { return float64(int(f*100)) / 100 }

func exitCodeDetail(code int) string {
	switch code {
	case 0:
		return "clean exit (0)"
	case 1:
		return "application error (1)"
	case 2:
		return "misuse of shell builtins or config error (2)"
	case 126:
		return "command invoked cannot execute (126)"
	case 127:
		return "command not found (127)"
	case 137:
		return "OOM kill or SIGKILL (137)"
	case 139:
		return "segmentation fault / SIGSEGV (139)"
	case 143:
		return "SIGTERM graceful termination (143)"
	default:
		return fmt.Sprintf("exit code %d", code)
	}
}
