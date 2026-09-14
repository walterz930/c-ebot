# c-ebot

Time synchronization bot for Chaster + EmlaLock, with a web dashboard and Discord integration.

## Planned features

- Highest-time-wins synchronization between Chaster and EmlaLock
- Manual add/remove time applied to both services
- Post-change verification
- Pause + Discord alert on failed synchronization
- Web setup wizard and dashboard
- Encrypted credential storage
- Discord logging and admin commands
- Docker deployment
- Windows Standalone deployment for PCs without virtualization

## Current status

The repository is being bootstrapped. The EmlaLock API adapter will only be enabled once its exact endpoint/request contract is confirmed from the official API documentation; no API endpoints are guessed.

## Windows installation

There are two supported installation paths:

### Option 1 — Windows Standalone (no virtualization)

Use this if Docker Desktop reports **Virtualization support not detected** or your PC cannot use virtualization.

This mode runs directly on Windows and does not require Docker, WSL, Hyper-V, or CPU virtualization.

Open PowerShell in the repository folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\install-standalone.ps1
```

The installer creates a Python virtual environment, installs the application dependencies, creates local data storage, starts c-ebot, and opens the dashboard at `http://localhost:8080`.

### Option 2 — Docker

Docker is still available for PCs with virtualization support. See `docker-compose.yml` and `.env.example` for the Docker configuration.

## Quick start

Never commit API keys, Discord tokens, or other secrets to Git. Use the setup wizard to configure credentials locally.
