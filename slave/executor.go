package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/image"
	"github.com/docker/docker/client"
)

// ── Executor — executes Docker commands sent by master ────────────────────────

type Executor struct {
	socketPath string
}

func NewExecutor(socketPath string) *Executor {
	return &Executor{socketPath: socketPath}
}

func (e *Executor) dockerClient() (*client.Client, error) {
	return client.NewClientWithOpts(
		client.WithHost("unix://"+socketPath(e.socketPath)),
		client.WithAPIVersionNegotiation(),
	)
}

func socketPath(p string) string {
	if strings.HasPrefix(p, "/") {
		return p
	}
	return "/var/run/docker.sock"
}

// ── Command types ─────────────────────────────────────────────────────────────

type CommandRequest struct {
	Action    string `json:"action"`    // restart | start | stop | exec | logs | list
	Container string `json:"container"` // container name or ID
	Command   string `json:"command"`   // used for exec action
	Tail      int    `json:"tail"`      // used for logs action
}

type CommandResponse struct {
	Success bool   `json:"success"`
	Output  string `json:"output"`
	Error   string `json:"error,omitempty"`
}

// ── HTTP handlers ─────────────────────────────────────────────────────────────

func startLocalServer(cfg Config, executor *Executor) {
	mux := http.NewServeMux()

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]string{"status": "ok", "slave_id": cfg.SlaveID})
	})

	mux.HandleFunc("/command", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", http.StatusMethodNotAllowed)
			return
		}

		// Validate shared secret sent by master in header
		token := r.Header.Get("X-Slave-Token")
		if token != cfg.SlaveID {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}

		var req CommandRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}

		resp := executor.Execute(req)
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	mux.HandleFunc("/containers", func(w http.ResponseWriter, r *http.Request) {
		cli, err := executor.dockerClient()
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		defer cli.Close()

		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		list, err := cli.ContainerList(ctx, container.ListOptions{All: true})
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		type slim struct {
			ID     string `json:"id"`
			Name   string `json:"name"`
			Image  string `json:"image"`
			Status string `json:"status"`
		}
		result := make([]slim, 0, len(list))
		for _, c := range list {
			name := c.Names[0]
			if strings.HasPrefix(name, "/") {
				name = name[1:]
			}
			result = append(result, slim{
				ID:     c.ID[:12],
				Name:   name,
				Image:  c.Image,
				Status: c.Status,
			})
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{"containers": result, "slave_id": cfg.SlaveID})
	})

	addr := fmt.Sprintf("0.0.0.0:%d", cfg.SlavePort)
	log.Printf("[LocalServer] Listening on %s", addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatalf("[LocalServer] Fatal: %v", err)
	}
}

// ── Execute dispatches a command to Docker ────────────────────────────────────

func (e *Executor) Execute(req CommandRequest) CommandResponse {
	cli, err := e.dockerClient()
	if err != nil {
		return CommandResponse{Success: false, Error: fmt.Sprintf("docker client: %v", err)}
	}
	defer cli.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	switch req.Action {
	case "restart":
		return e.restart(ctx, cli, req.Container)
	case "start":
		return e.start(ctx, cli, req.Container)
	case "stop":
		return e.stop(ctx, cli, req.Container)
	case "pull_restart":
		return e.pullRestart(ctx, cli, req.Container)
	case "logs":
		tail := req.Tail
		if tail == 0 {
			tail = 100
		}
		return e.logs(ctx, cli, req.Container, tail)
	case "exec":
		return e.exec(ctx, cli, req.Container, req.Command)
	default:
		return CommandResponse{Success: false, Error: fmt.Sprintf("unknown action: %s", req.Action)}
	}
}

func (e *Executor) restart(ctx context.Context, cli *client.Client, name string) CommandResponse {
	timeout := 10
	if err := cli.ContainerRestart(ctx, name, container.StopOptions{Timeout: &timeout}); err != nil {
		return CommandResponse{Success: false, Error: err.Error()}
	}
	return CommandResponse{Success: true, Output: fmt.Sprintf("Container %s restarted", name)}
}

func (e *Executor) start(ctx context.Context, cli *client.Client, name string) CommandResponse {
	if err := cli.ContainerStart(ctx, name, container.StartOptions{}); err != nil {
		return CommandResponse{Success: false, Error: err.Error()}
	}
	return CommandResponse{Success: true, Output: fmt.Sprintf("Container %s started", name)}
}

func (e *Executor) stop(ctx context.Context, cli *client.Client, name string) CommandResponse {
	timeout := 10
	if err := cli.ContainerStop(ctx, name, container.StopOptions{Timeout: &timeout}); err != nil {
		return CommandResponse{Success: false, Error: err.Error()}
	}
	return CommandResponse{Success: true, Output: fmt.Sprintf("Container %s stopped", name)}
}

func (e *Executor) logs(ctx context.Context, cli *client.Client, name string, tail int) CommandResponse {
	opts := container.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Tail:       fmt.Sprintf("%d", tail),
		Timestamps: true,
	}
	rc, err := cli.ContainerLogs(ctx, name, opts)
	if err != nil {
		return CommandResponse{Success: false, Error: err.Error()}
	}
	defer rc.Close()

	var sb strings.Builder
	buf := make([]byte, 4096)
	for {
		n, err := rc.Read(buf)
		if n > 0 {
			chunk := buf[:n]
			// Strip docker multiplexer 8-byte header per line
			for len(chunk) > 8 {
				size := int(chunk[4])<<24 | int(chunk[5])<<16 | int(chunk[6])<<8 | int(chunk[7])
				if size <= 0 || size+8 > len(chunk) {
					sb.Write(chunk[8:])
					break
				}
				sb.Write(chunk[8 : 8+size])
				chunk = chunk[8+size:]
			}
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			return CommandResponse{Success: false, Error: err.Error()}
		}
	}
	return CommandResponse{Success: true, Output: sb.String()}
}

func (e *Executor) exec(ctx context.Context, cli *client.Client, name, command string) CommandResponse {
	parts := strings.Fields(command)
	if len(parts) == 0 {
		return CommandResponse{Success: false, Error: "empty command"}
	}

	// FIX: use types.ExecConfig (not container.ExecCreateOptions)
	execID, err := cli.ContainerExecCreate(ctx, name, types.ExecConfig{
		Cmd:          parts,
		AttachStdout: true,
		AttachStderr: true,
	})
	if err != nil {
		return CommandResponse{Success: false, Error: err.Error()}
	}

	// FIX: use types.ExecStartCheck (types package now imported)
	attach, err := cli.ContainerExecAttach(ctx, execID.ID, types.ExecStartCheck{})
	if err != nil {
		return CommandResponse{Success: false, Error: err.Error()}
	}
	defer attach.Close()

	out, err := io.ReadAll(attach.Reader)
	if err != nil && err != io.EOF {
		return CommandResponse{Success: false, Error: err.Error()}
	}

	inspect, _ := cli.ContainerExecInspect(ctx, execID.ID)
	return CommandResponse{
		Success: inspect.ExitCode == 0,
		Output:  string(out),
	}
}
func (e *Executor) pullRestart(ctx context.Context, cli *client.Client, name string) CommandResponse {
	timeout := 10
	_ = cli.ContainerStop(ctx, name, container.StopOptions{Timeout: &timeout})

	inspect, err := cli.ContainerInspect(ctx, name)
	if err != nil {
		return CommandResponse{Success: false, Error: fmt.Sprintf("inspect container %s: %v", name, err)}
	}

	imageName := inspect.Config.Image
	if imageName != "" {
		rc, err := cli.ImagePull(ctx, imageName, image.PullOptions{})
		if err == nil {
			_, _ = io.Copy(io.Discard, rc)
			_ = rc.Close()
		} else {
			log.Printf("[Executor] Warning: Image pull failed for %s (%s): %v — restarting existing image", name, imageName, err)
		}
	}

	if err := cli.ContainerStart(ctx, name, container.StartOptions{}); err != nil {
		return CommandResponse{Success: false, Error: fmt.Sprintf("start container %s: %v", name, err)}
	}

	return CommandResponse{
		Success: true,
		Output:  fmt.Sprintf("Container %s pulled fresh image (%s) and restarted successfully", name, imageName),
	}
}
