package main

import (
	"bytes"
	"context"
	"encoding/json"
	"log"
	"net/http"
	"time"
)

// EventStreamer queues events and pushes them to master with retry.
// Separate from HealthReporter so event delivery is never blocked by stats polling.

type Event struct {
	SlaveID       string `json:"slave_id"`
	EventType     string `json:"event_type"`
	ContainerName string `json:"container_name"`
	ContainerID   string `json:"container_id"`
	ExitCode      int    `json:"exit_code"`
	Detail        string `json:"detail"`
	Ts            int64  `json:"ts"`
}

type EventStreamer struct {
	queue      chan Event
	httpClient *http.Client
	masterURL  string
	slaveID    string
}

func NewEventStreamer(httpClient *http.Client, masterURL, slaveID string) *EventStreamer {
	return &EventStreamer{
		queue:      make(chan Event, 100),
		httpClient: httpClient,
		masterURL:  masterURL,
		slaveID:    slaveID,
	}
}

// Push adds an event to the queue (non-blocking).
func (es *EventStreamer) Push(eventType, containerName, containerID, detail string, exitCode int) {
	ev := Event{
		SlaveID:       es.slaveID,
		EventType:     eventType,
		ContainerName: containerName,
		ContainerID:   containerID,
		ExitCode:      exitCode,
		Detail:        detail,
		Ts:            time.Now().Unix(),
	}
	select {
	case es.queue <- ev:
	default:
		log.Printf("[EventStreamer] Queue full — dropping event: %s/%s", eventType, containerName)
	}
}

// Run consumes the queue and sends events to master with up to 3 retries.
func (es *EventStreamer) Run(ctx context.Context) {
	log.Println("[EventStreamer] Started")
	for {
		select {
		case <-ctx.Done():
			return
		case ev := <-es.queue:
			es.sendWithRetry(ctx, ev)
		}
	}
}

func (es *EventStreamer) sendWithRetry(ctx context.Context, ev Event) {
	body, _ := json.Marshal(ev)
	url := es.masterURL + "/slaves/events"

	for attempt := 1; attempt <= 3; attempt++ {
		reqCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
		req, err := http.NewRequestWithContext(reqCtx, "POST", url, bytes.NewReader(body))
		if err != nil {
			cancel()
			return
		}
		req.Header.Set("Content-Type", "application/json")

		resp, err := es.httpClient.Do(req)
		cancel()

		if err == nil && resp.StatusCode < 400 {
			resp.Body.Close()
			return
		}
		if resp != nil {
			resp.Body.Close()
		}
		if attempt < 3 {
			time.Sleep(time.Duration(attempt*2) * time.Second)
		}
	}
	log.Printf("[EventStreamer] Failed to deliver event %s/%s after 3 attempts", ev.EventType, ev.ContainerName)
}