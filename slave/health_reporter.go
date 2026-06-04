package main

import (
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

// HealthReporter watches container stats + lifecycle events and forwards them to master.

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
}

func NewHealthReporter(cli *client.Client, mc *MasterClient, cfg Config) *HealthReporter {
	return &HealthReporter{
		cli:             cli,
		masterClient:    mc,
		cfg:             cfg,
		memThresholdPct: 90.0,
	}
}

func (h *HealthReporter) Run(ctx context.Context) {
	log.Println("[HealthReporter] Starting")
	go h.watchEvents(ctx)
	go h.pollStats(ctx)
}

// watchEvents listens to Docker event stream and pushes die/oom/start to master.
func (h *HealthReporter) watchEvents(ctx context.Context) {
	f := filters.NewArgs()
	f.Add("type", "container")
	msgCh, errCh := h.cli.Events(ctx, events.ListOptions{Filters: f})

	for {
		select {
		case <-ctx.Done():
			return
		case err := <-errCh:
			if err != nil && err != io.EOF {
				log.Printf("[HealthReporter] Event stream error: %v — retrying in 5s", err)
				time.Sleep(5 * time.Second)
				msgCh, errCh = h.cli.Events(ctx, events.ListOptions{Filters: f})
			}
		case msg := <-msgCh:
			h.handleEvent(ctx, msg)
		}
	}
}

func (h *HealthReporter) handleEvent(ctx context.Context, msg events.Message) {
	name := msg.Actor.Attributes["name"]
	switch msg.Action {
	case "die":
		exitCode := 0
		if ec, ok := msg.Actor.Attributes["exitCode"]; ok {
			fmt.Sscanf(ec, "%d", &exitCode)
		}
		detail := exitCodeDetail(exitCode)
		log.Printf("[HealthReporter] die: %s exit=%d", name, exitCode)
		_ = h.masterClient.PushEvent(ctx, "die", name, detail)

	case "oom":
		log.Printf("[HealthReporter] OOM kill: %s", name)
		_ = h.masterClient.PushEvent(ctx, "oom", name, "OOM kill — memory limit exceeded")

	case "start":
		_ = h.masterClient.PushEvent(ctx, "start", name, "")

	case "stop", "kill":
		_ = h.masterClient.PushEvent(ctx, msg.Action, name, "")
	}
}

// pollStats samples every container's CPU+mem every 30s and pushes to master.
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
			detail := fmt.Sprintf("Memory %.1f%% — %.0f/%.0f MB", s.MemPct, s.MemUsedMB, s.MemLimitMB)
			log.Printf("[HealthReporter] HIGH MEM: %s — %s", name, detail)
			_ = h.masterClient.PushEvent(ctx, "health_fail", name, detail)
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
	sysDelta  := float64(raw.CPUStats.SystemUsage)         - float64(raw.PreCPUStats.SystemUsage)
	ncpu := float64(raw.CPUStats.OnlineCPUs)
	if ncpu == 0 { ncpu = 1 }
	cpuPct := 0.0
	if sysDelta > 0 {
		cpuPct = (cpuDelta / sysDelta) * ncpu * 100.0
	}
	memUsed  := float64(raw.MemoryStats.Usage) / 1024 / 1024
	memLimit := float64(raw.MemoryStats.Limit) / 1024 / 1024
	memPct := 0.0
	if memLimit > 0 { memPct = (memUsed / memLimit) * 100.0 }

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
	case 0:   return "clean exit (0)"
	case 1:   return "application error (1)"
	case 137: return "OOM kill (137)"
	case 143: return "SIGTERM (143)"
	default:  return fmt.Sprintf("exit code %d", code)
	}
}