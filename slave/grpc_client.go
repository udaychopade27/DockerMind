package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"
)

// ── MasterClient — secure HTTP/2 client to talk to master API ─────────────────
// Phase 1 uses HTTPS REST over mTLS.
// Phase 2 will upgrade this to full gRPC streaming.

type MasterClient struct {
	baseURL     string
	slaveID     string
	slaveSecret string
	httpClient  *http.Client
}

// NewMasterClient creates a mTLS-secured client pointing at the master.
func NewMasterClient(cfg Config) (*MasterClient, error) {
	httpClient, err := buildMTLSClient(cfg)
	if err != nil {
		return nil, fmt.Errorf("cannot build mTLS client: %w", err)
	}
	return &MasterClient{
		baseURL:     cfg.MasterURL,
		slaveID:     cfg.SlaveID,
		slaveSecret: cfg.SlaveSecret,
		httpClient:  httpClient,
	}, nil
}

// buildMTLSClient returns an *http.Client with mutual TLS configured.
// Falls back to plain HTTP if cert files are missing (dev mode).
func buildMTLSClient(cfg Config) (*http.Client, error) {
	// Dev mode: no certs present
	if _, err := os.Stat(cfg.CACert); os.IsNotExist(err) {
		log.Println("[gRPC/TLS] CA cert not found — using plain HTTP (dev mode)")
		return &http.Client{Timeout: 15 * time.Second}, nil
	}

	// Load CA cert
	caPEM, err := os.ReadFile(cfg.CACert)
	if err != nil {
		return nil, fmt.Errorf("read CA cert: %w", err)
	}
	caPool := x509.NewCertPool()
	if !caPool.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("failed to parse CA cert")
	}

	tlsCfg := &tls.Config{
		RootCAs:    caPool,
		MinVersion: tls.VersionTLS12,
		// Only allow strong cipher suites
		CipherSuites: []uint16{
			tls.TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,
			tls.TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,
			tls.TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305,
			tls.TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305,
		},
	}

	// Load slave client cert for mutual TLS
	if _, err := os.Stat(cfg.SlaveCert); err == nil {
		cert, err := tls.LoadX509KeyPair(cfg.SlaveCert, cfg.SlaveKey)
		if err != nil {
			return nil, fmt.Errorf("load slave keypair: %w", err)
		}
		tlsCfg.Certificates = []tls.Certificate{cert}
		log.Println("[gRPC/TLS] Mutual TLS enabled — client certificate loaded")
	} else {
		log.Println("[gRPC/TLS] No slave cert found — using server-only TLS")
	}

	transport := &http.Transport{
		TLSClientConfig:     tlsCfg,
		MaxIdleConns:        10,
		IdleConnTimeout:     90 * time.Second,
		TLSHandshakeTimeout: 10 * time.Second,
	}

	return &http.Client{
		Timeout:   30 * time.Second,
		Transport: transport,
	}, nil
}

// ── Master API call helpers ───────────────────────────────────────────────────

func (mc *MasterClient) post(ctx context.Context, path string, payload any) ([]byte, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		mc.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if mc.slaveSecret != "" {
		req.Header.Set("X-Slave-Token", mc.slaveSecret)
	}

	resp, err := mc.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("master %s returned %d: %s", path, resp.StatusCode, string(respBody))
	}
	return respBody, nil
}

func (mc *MasterClient) get(ctx context.Context, path string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, mc.baseURL+path, nil)
	if err != nil {
		return nil, err
	}
	resp, err := mc.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("master %s returned %d: %s", path, resp.StatusCode, string(body))
	}
	return body, nil
}

// ── Slave → Master calls ──────────────────────────────────────────────────────

// Register sends slave registration payload to master.
func (mc *MasterClient) Register(ctx context.Context, hostname, ip string, port int, tags []string) error {
	_, err := mc.post(ctx, "/slaves/register", map[string]any{
		"slave_id": mc.slaveID,
		"hostname": hostname,
		"ip":       ip,
		"port":     port,
		"tags":     tags,
	})
	return err
}

// Heartbeat notifies master the slave is still alive.
func (mc *MasterClient) Heartbeat(ctx context.Context, containerCount int) error {
	_, err := mc.post(ctx, "/slaves/heartbeat", map[string]any{
		"slave_id":        mc.slaveID,
		"container_count": containerCount,
	})
	return err
}

// PushLogs forwards container log batch to master for LLM analysis.
func (mc *MasterClient) PushLogs(ctx context.Context, containerID, containerName, logs string) error {
	_, err := mc.post(ctx, "/slaves/logs", map[string]any{
		"slave_id":       mc.slaveID,
		"container_id":   containerID,
		"container_name": containerName,
		"logs":           logs,
		"ts":             time.Now().Unix(),
	})
	return err
}

// PushEvent sends a container lifecycle event (start/stop/die/oom/health_fail) to master with exit code and container ID.
func (mc *MasterClient) PushEvent(ctx context.Context, eventType, containerName, containerID string, exitCode int, detail string) error {
	_, err := mc.post(ctx, "/slaves/events", map[string]any{
		"slave_id":       mc.slaveID,
		"event_type":     eventType,
		"container_name": containerName,
		"container_id":   containerID,
		"exit_code":      exitCode,
		"detail":         detail,
		"ts":             time.Now().Unix(),
	})
	return err
}

// ── Reconnect loop ────────────────────────────────────────────────────────────
// RunHeartbeatLoop sends heartbeats and reconnects to master if connection is lost.

func (mc *MasterClient) RunHeartbeatLoop(ctx context.Context, watcher *DockerWatcher, intervalSecs int) {
	ticker := time.NewTicker(time.Duration(intervalSecs) * time.Second)
	defer ticker.Stop()

	consecutiveFails := 0

	for {
		select {
		case <-ctx.Done():
			log.Println("[MasterClient] Context cancelled — stopping heartbeat loop")
			return
		case <-ticker.C:
			count := 0
			if watcher != nil {
				count = watcher.ContainerCount()
			}
			err := mc.Heartbeat(ctx, count)
			if err != nil {
				consecutiveFails++
				log.Printf("[MasterClient] Heartbeat failed (%d consecutive): %v", consecutiveFails, err)
				hostname, _ := os.Hostname()
				outboundIP := getOutboundIP()
				if regErr := mc.Register(ctx, hostname, outboundIP, 8080, []string{"phase2"}); regErr == nil {
					log.Printf("[MasterClient] Re-registered with master after heartbeat failure")
					consecutiveFails = 0
				}
			} else {
				if consecutiveFails > 0 {
					log.Println("[MasterClient] Reconnected to master")
				}
				consecutiveFails = 0
			}
		}
	}
}

// Ping checks if master is reachable. Returns nil if healthy.
func (mc *MasterClient) Ping(ctx context.Context) error {
	_, err := mc.get(ctx, "/health")
	return err
}

// postRaw sends a pre-marshalled JSON body — used by health_reporter for stats push.
func (mc *MasterClient) postRaw(ctx context.Context, path string, body []byte) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, mc.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if mc.slaveSecret != "" {
		req.Header.Set("X-Slave-Token", mc.slaveSecret)
	}
	resp, err := mc.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return fmt.Errorf("master returned %d", resp.StatusCode)
	}
	return nil
}