# Stage 1 — build
FROM golang:1.26-alpine AS builder

WORKDIR /build

# Install build deps
RUN apk add --no-cache git ca-certificates

# Copy everything so go mod tidy can see all imports
COPY go.mod .
COPY *.go .

# Generate go.sum and download all dependencies
ENV GONOSUMDB=* GOFLAGS=-mod=mod
RUN go mod tidy && go mod download

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o dockermind-slave .

# Stage 2 — minimal final image (~15MB)
FROM alpine:3.19

RUN apk add --no-cache ca-certificates curl

WORKDIR /app

COPY --from=builder /build/dockermind-slave .

RUN mkdir -p /app/certs

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

CMD ["./dockermind-slave"]