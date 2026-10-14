package main

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"log"
	"net"
	"strings"
	"sync"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/events"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/client"
)

type ContainerInfo struct {
	ID     string
	Name   string
	Image  string
	Status string
}

type DockerWatcher struct {
	socketPath    string
	cli           *client.Client
	mu            sync.RWMutex
	containers    map[string]ContainerInfo
	restartCounts map[string]int
	lastLogCheck  map[string]int64
}

func NewDockerWatcher(socketPath string) (*DockerWatcher, error) {
	cli, err := client.NewClientWithOpts(
		client.WithHost("unix://"+socketPath),
		client.WithAPIVersionNegotiation(),
	)
	if err != nil {
		return nil, err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if _, err := cli.Ping(ctx); err != nil {
		return nil, fmt.Errorf("docker connection failed: %w", err)
	}

	return &DockerWatcher{
		socketPath:    socketPath,
		cli:           cli,
		containers:    map[string]ContainerInfo{},
		restartCounts: map[string]int{},
		lastLogCheck:  map[string]int64{},
	}, nil
}

func (w *DockerWatcher) ContainerCount() int {
	w.mu.RLock()
	defer w.mu.RUnlock()
	return len(w.containers)
}

func (w *DockerWatcher) WatchContainers() {
	log.Println("[Watcher] Starting")

	w.refreshContainerList()

	ctx := context.Background()

	f := filters.NewArgs()
	f.Add("type", "container")

	eventsOpts := types.EventsOptions{Filters: f}
	msgCh, errCh := w.cli.Events(ctx, eventsOpts)

	for {
		select {
		case msg, ok := <-msgCh:
			if !ok {
				time.Sleep(3 * time.Second)
				msgCh, errCh = w.cli.Events(ctx, eventsOpts)
				continue
			}
			w.handleEvent(msg)

		case err, ok := <-errCh:
			if ok && err != nil && err != io.EOF {
				log.Printf("[Watcher] reconnect: %v", err)
				time.Sleep(5 * time.Second)
				msgCh, errCh = w.cli.Events(ctx, eventsOpts)
			}
		}
	}
}

func (w *DockerWatcher) refreshContainerList() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	list, err := w.cli.ContainerList(ctx, container.ListOptions{All: true})
	if err != nil {
		log.Printf("container list failed: %v", err)
		return
	}

	w.mu.Lock()
	defer w.mu.Unlock()

	w.containers = map[string]ContainerInfo{}

	for _, c := range list {
		name := ""
		if len(c.Names) > 0 {
			name = strings.TrimPrefix(c.Names[0], "/")
		}

		id := c.ID
		if len(id) > 12 {
			id = id[:12]
		}

		w.containers[c.ID] = ContainerInfo{
			ID:     id,
			Name:   name,
			Image:  c.Image,
			Status: c.Status,
		}
	}
}

func (w *DockerWatcher) handleEvent(msg events.Message) {
	id := msg.Actor.ID
	if len(id) > 12 {
		id = id[:12]
	}

	switch msg.Action {
	case "start":
		w.mu.Lock()
		w.containers[msg.Actor.ID] = ContainerInfo{
			ID:     id,
			Name:   msg.Actor.Attributes["name"],
			Image:  msg.Actor.Attributes["image"],
			Status: "running",
		}
		w.mu.Unlock()

	case "die", "stop", "kill":
		w.mu.Lock()
		if c, ok := w.containers[msg.Actor.ID]; ok {
			c.Status = "stopped"
			w.containers[msg.Actor.ID] = c
			if msg.Action == "die" {
				w.restartCounts[msg.Actor.ID]++
			}
		}
		w.mu.Unlock()

	case "destroy":
		w.mu.Lock()
		delete(w.containers, msg.Actor.ID)
		delete(w.restartCounts, msg.Actor.ID)
		delete(w.lastLogCheck, msg.Actor.ID)
		w.mu.Unlock()
	}
}

func (w *DockerWatcher) GetLogs(containerID string, tail int) (string, error) {
	return w.GetNewLogs(containerID, 0, tail)
}

func (w *DockerWatcher) GetNewLogs(containerID string, since int64, tail int) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	opts := container.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Timestamps: false,
	}
	if tail > 0 {
		opts.Tail = fmt.Sprintf("%d", tail)
	}
	if since > 0 {
		opts.Since = fmt.Sprintf("%d", since)
	}

	rc, err := w.cli.ContainerLogs(ctx, containerID, opts)
	if err != nil {
		return "", err
	}
	defer rc.Close()

	var out strings.Builder
	scanner := bufio.NewScanner(rc)
	for scanner.Scan() {
		line := scanner.Text()
		if len(line) > 8 {
			line = line[8:]
		}
		out.WriteString(line + "\n")
	}
	return out.String(), nil
}

func hasSuspiciousLogs(logs string) bool {
	lower := strings.ToLower(logs)
	keywords := []string{
		"error", "fatal", "exception", "panic", "traceback",
		"failed", "crash", "oom", "killed", "refused", "critical", "warn",
	}
	for _, kw := range keywords {
		if strings.Contains(lower, kw) {
			return true
		}
	}
	return false
}

func (w *DockerWatcher) StartLogForwarder(ctx context.Context, mc *MasterClient, cfg Config) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			w.forwardLogs(ctx, mc)
		}
	}
}

func (w *DockerWatcher) forwardLogs(ctx context.Context, mc *MasterClient) {
	w.mu.RLock()
	items := make([]ContainerInfo, 0, len(w.containers))
	for _, c := range w.containers {
		items = append(items, c)
	}
	w.mu.RUnlock()

	now := time.Now().Unix()

	for _, c := range items {
		if c.Status != "running" {
			continue
		}
		// Skip self/dockermind internal containers to prevent infinite log loops
		if strings.HasPrefix(c.Name, "dockermind-") {
			continue
		}

		w.mu.Lock()
		since := w.lastLogCheck[c.ID]
		w.lastLogCheck[c.ID] = now
		w.mu.Unlock()

		if since == 0 {
			since = now - 60
		}

		logs, err := w.GetNewLogs(c.ID, since, 100)
		if err != nil || strings.TrimSpace(logs) == "" {
			continue
		}

		// Only forward if logs contain errors/warnings or anomalies to avoid overloading LLM
		if hasSuspiciousLogs(logs) {
			log.Printf("[Watcher] Forwarding suspicious logs for container %s (%d bytes)", c.Name, len(logs))
			_ = mc.PushLogs(ctx, c.ID, c.Name, logs)
		}
	}
}

func net_dial() (string, error) {
	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err != nil {
		return "0.0.0.0", err
	}
	defer conn.Close()
	return conn.LocalAddr().(*net.UDPAddr).IP.String(), nil
}
