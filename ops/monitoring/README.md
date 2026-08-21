# OmniAI Monitoring

## Files
- `prometheus.yml` — scrape configuration for the backend metrics endpoint
- `docker-compose.yml` — local Prometheus + Grafana stack
- `grafana-dashboard-omniai.json` — starter dashboard

## Usage
1. Obtain a valid owner session token from `POST /api/v1/auth/login`.
2. Replace `REPLACE_WITH_SESSION_TOKEN` in `prometheus.yml`.
3. Start the stack:
   ```bash
   cd ops/monitoring
   docker compose up -d
   ```
4. Open:
   - Prometheus: `http://localhost:9090`
   - Grafana: `http://localhost:3000`
5. In Grafana, add Prometheus as a data source pointing to `http://prometheus:9090`, then import `grafana-dashboard-omniai.json`.

## Metrics currently exported
- `omniai_http_requests_total`
- `omniai_http_latency_avg_seconds`
- `omniai_http_latency_p95_seconds`
- `omniai_http_latency_max_seconds`
- `omniai_active_sessions`
- `omniai_http_route_requests_total{method,path,status}`
