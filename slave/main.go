package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"
)

// ── Config ────────────────────────────────────────────────────────────────────

type Config struct {
	SlaveID       string
	MasterURL     string
	SlavePort     int
	CACert        string
	SlaveCert     string
	SlaveKey      string
	HeartbeatSecs int
	DockerSocket  string
}

func loadConfig() Config {
	return Config{
		SlaveID:       getEnv("SLAVE_ID", generateSlaveID()),
		MasterURL:     getEnv("MASTER_URL", "http://master:8000"),
		SlavePort:     8080,
		CACert:        getEnv("CA_CERT", "/app/certs/ca.crt"),
		SlaveCert:     getEnv("SLAVE_CERT", "/app/certs/slave.crt"),
		SlaveKey:      getEnv("SLAVE_KEY", "/app/certs/slave.key"),
		HeartbeatSecs: 10,
		DockerSocket:  getEnv("DOCKER_SOCKET", "/var/run/docker.sock"),
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func generateSlaveID() string {
	hostname, _ := os.Hostname()
	return fmt.Sprintf("slave-%s", hostname)
}

// ── Main ──────────────────────────────────────────────────────────────────────

func main() {
	log.Println("=== DockerMind Slave Agent starting ===")

	cfg := loadConfig()
	log.Printf("[Config] SlaveID=%s  Master=%s", cfg.SlaveID, cfg.MasterURL)

	// mTLS master client
	masterClient, err := NewMasterClient(cfg)
	if err != nil {
		log.Fatalf("[Main] Cannot create master client: %v", err)
	}

	// Docker watcher (container map + log forwarding)
	watcher, err := NewDockerWatcher(cfg.DockerSocket)
	if err != nil {
		log.Printf("[Docker] Warning: %v — container monitoring disabled", err)
		watcher = nil
	} else {
		log.Println("[Docker] Connected to Docker socket")
		go watcher.WatchContainers()
	}

	// Event streamer (immediate event delivery with retry)
	streamer := NewEventStreamer(masterClient.httpClient, cfg.MasterURL, cfg.SlaveID)

	// Health reporter (stats polling + event detection)
	var reporter *HealthReporter
	if watcher != nil {
		reporter = NewHealthReporter(watcher.cli, masterClient, cfg)
	}

	// Local HTTP server (receives commands from master)
	executor := NewExecutor(cfg.DockerSocket)
	go startLocalServer(cfg, executor)

	// Register with master — retry until success
	hostname, _ := os.Hostname()
	outboundIP := getOutboundIP()
	for {
		if err := masterClient.Register(context.Background(), hostname, outboundIP, cfg.SlavePort, []string{"phase2"}); err == nil {
			log.Printf("[Main] Registered with master as %s (ip=%s)", cfg.SlaveID, outboundIP)
			break
		} else {
			log.Printf("[Main] Cannot reach master: %v — retrying in 5s", err)
			time.Sleep(5 * time.Second)
		}
	}

	// Context for clean shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start all background workers
	go streamer.Run(ctx)
	if watcher != nil {
		go watcher.StartLogForwarder(ctx, masterClient, cfg)
	}
	if reporter != nil {
		reporter.Run(ctx)
	}
	go masterClient.RunHeartbeatLoop(ctx, watcher, cfg.HeartbeatSecs)

	// Graceful shutdown on signal
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	sig := <-sigCh
	log.Printf("[Main] Signal received: %v — shutting down", sig)
}

// getOutboundIP returns this machine's outbound IP using a UDP trick (no packet sent).
func getOutboundIP() string {
	ip, err := net_dial()
	if err != nil {
		return "127.0.0.1"
	}
	return ip
}