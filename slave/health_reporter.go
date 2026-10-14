package main

import (
	"bufio"
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

type HealthReporter struct {
	cli             *client.Client
	masterClient    *MasterClient
	cfg             Config
	memThresholdPct float64
	streamer        *EventStreamer
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
	payload, _ := json.Marshal(map[string]any{
		"slave_id": h.cfg.SlaveID,
		"stats":    allStats,
		"ts":       time.Now().Unix(),
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
