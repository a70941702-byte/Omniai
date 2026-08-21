# Security

- Production Android cleartext traffic is disabled; cleartext is enabled only in the debug manifest.
- Owner login exchanges the long-lived owner secret for a short-lived random session token. Sessions are stored as SHA-256 hashes and can be revoked.
- Secrets for external providers are read from environment/secret injection, never source or SQLite plaintext.
- Internet is disabled by default and can only be used through the gateway with allow/block lists.
- HIGH/CRITICAL agent tools cannot self-approve.
- Audit entries are hash chained and there is no delete/clear API.
- Kill switch blocks new work and actively terminates sandbox processes.
- Production code changes require owner approval, patch validation, test execution and rollback on failure.
- The sandbox flattens supplied paths, rejects escapes, blocks network, limits CPU/memory/processes, caps output and kills timed-out processes.
