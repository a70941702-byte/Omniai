# Security Review Checklist

## Completed hardening
- owner-token authentication remains isolated from the AI actor
- bearer sessions are stored as hashes
- session TTL and idle timeout are enforced
- per-device session caps are enforced
- failed login attempts are rate-limited
- kill-switch, approvals, audit chain, and emergency bundle flows are implemented
- metrics and device/session inspection endpoints exist for operational review

## Operational checks before production
1. Set `OMNI_OWNER_TOKEN` only through deployment secrets.
2. Put the backend behind HTTPS.
3. Restrict ingress by IP / VPN / reverse proxy where possible.
4. Rotate session tokens by logging out stale devices.
5. Review `GET /api/v1/auth/devices` periodically.
6. Replace default Grafana password if monitoring stack is enabled.
7. Mount persistent storage for DB/checkpoints/backups/state bundles.
8. Keep `internet_enabled` and `external_models_enabled` off unless intentionally needed.
9. Verify `domain_allowlist` before turning web access on.
10. Keep emergency-stop path documented and tested.

## Recommended next tightening
- add reverse-proxy rate limits
- add TLS termination and optional mTLS/VPN
- add secret rotation procedure
- add signed release/app distribution process
