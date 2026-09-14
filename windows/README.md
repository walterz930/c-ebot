# Windows installation options

## Standalone (no virtualization)

Use `install-standalone.ps1` if Docker Desktop reports **Virtualization support not detected** or your PC cannot run virtualization.

This mode runs c-ebot directly on Windows. It does not use Docker, WSL, Hyper-V, or CPU virtualization.

Requirements:
- Windows 10/11
- Python 3.12 or newer
- A normal Windows user account with permission to run Python

From PowerShell in the repository folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\install-standalone.ps1
```

The installer creates a local virtual environment, installs dependencies, creates the local data directory and launches the dashboard at `http://localhost:8080`.

## Docker

Docker remains available for machines with virtualization support. See the main README for the Docker setup.
