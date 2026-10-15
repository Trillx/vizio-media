# Security and public releases

This is a single-household LAN service. It accepts the configured TV, server address, and loopback, rejects forwarding-header impersonation, and restricts owner administration to a loopback peer and Host. Use the documented SSH tunnel for a remote VM. Run one worker because account transitions and login limits use process-local locks. Internet exposure and proxy deployment require a separate authentication and TLS design.

Owner passwords and profile PINs are salted PBKDF2 hashes. Application settings, OAuth tokens, and private device credentials are encrypted with a generated Fernet key. The key is generated at first startup inside the private data directory. Browser responses omit provider secrets, private device codes, and account download URLs. Personal home responses are uncached. Public metadata and artwork use bounded caches.

## Keep private

Never commit or upload:

- `.env` and local overrides;
- the runtime `data/` directory, SQLite databases and sidecar files, or backups;
- `vault.key`, pairing credentials, access/refresh tokens, app secrets, passwords, or PINs;
- diagnostic logs, screenshots with account details, or downloaded account files;
- local virtual environments or agent-tool configurations.

The repository starts with a source-only snapshot and no private development history. `.gitignore` protects runtime files, and `.dockerignore` permits only required application sources into the image context. These are guardrails, not a substitute for reviewing staged files before each publication. Test credentials in fixtures are deliberately fictional.

## Backups and migration

Preserve the database and matching `vault.key` together in a private backup. Losing the key makes encrypted records unreadable. Restoring only the database or generating a replacement key does not recover credentials. Stop the old instance before moving an account installation so refresh-token updates cannot diverge.

## Reporting

Do not include real tokens, databases, account URLs, or diagnostic exports in public issues. Use GitHub's private vulnerability reporting on the repository when enabled. Describe the affected version and provide a minimal reproduction with fictional accounts.
