# c-ebot

**Chaster + EmlaLock time synchronization bot** with a web dashboard and Discord integration.

c-ebot is designed to keep the remaining time on Chaster and EmlaLock synchronized. It uses the higher remaining time as the normal synchronization target, provides manual add/subtract controls, verifies changes after every operation, and can alert Discord and pause synchronization when a synchronized operation fails.

> **Development status:** c-ebot is still being built. The EmlaLock live API adapter is not enabled until its exact endpoint/request contract is confirmed from the official API documentation. No EmlaLock API endpoints are guessed.

---

## Features

- Highest-time-wins automatic synchronization
- Chaster + EmlaLock timers shown side by side
- Sync Now and Auto Sync controls
- Pause/resume synchronization
- Manual **Add Time** applied to both services
- Manual **Subtract Time** applied to both services
- Post-change timer verification
- Automatic pause + Discord alert after a failed synchronized change
- Web setup wizard
- Encrypted credential storage
- Credentials are masked after setup and are not displayed again
- Factory Reset for clearing the local credential vault
- Discord logging
- Admin Discord commands such as `/status`, `/sync`, `/addtime`, `/subtracttime`, and `/logs`
- Permission-controlled manual time changes
- Local audit/history log
- Windows Standalone mode for PCs that cannot use virtualization
- Docker mode for PCs that support virtualization

---

# Windows Setup

There are **two ways to run c-ebot on Windows**. Choose the one that matches your PC.

## Option A — Windows Standalone ⭐ No virtualization required

Use this option if Docker Desktop says:

> **Virtualization support not detected**

or if your computer cannot use CPU virtualization.

The standalone version runs directly on Windows and does **not** require:

- Docker Desktop
- WSL
- Hyper-V
- CPU virtualization

### Requirements

- Windows 10 or Windows 11
- Python 3.12 or newer
- Internet access during the initial installation

### Step 1 — Install Python

Install Python 3.12+ and make sure **Add Python to PATH** is enabled during installation.

### Step 2 — Download c-ebot

Download or clone this repository:

```powershell
git clone https://github.com/walterz930/c-ebot.git
cd c-ebot
```

If Git is not installed, you can use **Code → Download ZIP** on GitHub and extract the ZIP.

### Step 3 — Run the standalone installer

Open PowerShell in the c-ebot folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\install-standalone.ps1
```

The installer will:

1. Create the local Python environment.
2. Install the required packages.
3. Create the local data directory.
4. Create a local application secret.
5. Start c-ebot.
6. Open the dashboard in your browser.

The dashboard will be available at:

```text
http://localhost:8080
```

### Step 4 — Complete the setup wizard

Use the browser dashboard to configure:

- **Chaster developer token**
- **EmlaLock User ID**
- **EmlaLock API key**
- **EmlaLock Keyholder API key** for subtract-time operations
- **Discord settings**, including the log channel

Credentials are intended to be encrypted locally and masked after they are saved. Do not put API keys or Discord tokens into GitHub, screenshots, or support posts.

### Step 5 — Configure Discord

Connect/configure the Discord bot through the dashboard and select the channel where c-ebot should send logs and failure alerts.

Important events can include:

- Startup/shutdown
- Connection changes
- Synchronization results
- Time added
- Time removed
- Manual changes
- API errors
- Failed synchronization
- Configuration changes
- Permission changes

---

# Docker Setup

Use Docker if your Windows PC supports virtualization.

### 1. Install Docker Desktop

Install Docker Desktop and make sure it is running.

### 2. Download c-ebot

```powershell
git clone https://github.com/walterz930/c-ebot.git
cd c-ebot
```

### 3. Create the environment file

Copy the example configuration:

```powershell
Copy-Item .env.example .env
```

At minimum, set a strong `APP_SECRET` in `.env`.

### 4. Start c-ebot

```powershell
docker compose up -d --build
```

Then open:

```text
http://localhost:8080
```

### 5. Stop c-ebot

```powershell
docker compose down
```

To start it again:

```powershell
docker compose up -d
```

---

# First-Time Configuration

The setup wizard is intended to be the main configuration method. You should not need to manually edit application source code.

## Chaster

Enter your **Chaster developer token** in the setup wizard.

The normal synchronization logic is:

```text
Read Chaster remaining time
          ↓
Read EmlaLock remaining time
          ↓
Compare the two timers
          ↓
Higher time = synchronization target
          ↓
Extend the lower timer
          ↓
Read both timers again
          ↓
Verify they match
```

Normal automatic synchronization must **never shorten the higher timer**.

## EmlaLock

Enter the EmlaLock credentials requested by the setup wizard. The Keyholder API key is required for operations that remove time.

The live EmlaLock adapter will only be enabled once the exact official API request contract has been confirmed.

## Discord

Configure the Discord bot and log channel if Discord notifications and administrative commands are wanted.

---

# Time Controls

### Automatic sync

When Auto Sync is enabled, c-ebot periodically compares both services and brings the lower timer up to the higher timer.

### Add time

A manual add operation adds the same amount to both services.

Example:

```text
Chaster:   2h 00m
EmlaLock:  2h 00m

Add 30 minutes

Chaster:   2h 30m
EmlaLock:  2h 30m
```

### Subtract time

A manual subtract operation removes the same amount from both services. This is an explicit manual operation and is different from normal automatic synchronization.

After every modification, c-ebot re-reads both timers and verifies that they match.

### Failed synchronization

If one service is changed successfully but the corresponding change fails on the other service, c-ebot should:

1. Stop further automatic time changes.
2. Record the failure.
3. Send a Discord alert when Discord is configured.
4. Require the sync process to be resumed after the problem is addressed.

---

# Security

Never commit these to GitHub:

- Chaster tokens
- EmlaLock API keys
- Discord bot tokens
- Database files
- `.env` files containing secrets

The repository's `.gitignore` is configured to keep local secrets and application data out of Git.

The intended credential system encrypts credentials at rest and does not provide a dashboard function for revealing saved credentials. Replacing a credential replaces the stored value rather than displaying the old one.

### Factory Reset

Factory Reset is intended to clear the locally stored c-ebot configuration and encrypted credential vault. It should require an explicit confirmation such as:

```text
FACTORY RESET
```

Factory Reset does **not** delete or modify your Chaster or EmlaLock accounts or locks.

---

# Troubleshooting

## Docker says “Virtualization support not detected”

You do not need to enable virtualization just to use c-ebot.

Use the Windows Standalone installation instead:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\install-standalone.ps1
```

## Dashboard does not open

Make sure c-ebot is running and then manually open:

```text
http://localhost:8080
```

## Port 8080 is already in use

Stop the application using port 8080 or change the configured application port before starting c-ebot.

## API connection errors

Check the credentials in the setup wizard and review the dashboard/Discord logs. Do not paste your actual API keys into an issue or support request.

---

# Project Structure

```text
c-ebot/
├── app/                       # Application source
├── windows/
│   ├── install-standalone.ps1 # No-virtualization Windows installer
│   └── README.md
├── data/                      # Local runtime data (not committed)
├── .env.example               # Example environment settings
├── docker-compose.yml         # Docker deployment
├── Dockerfile                 # Docker image
└── requirements.txt           # Python dependencies
```

---

# Development

This repository is being actively built. Features described above may be present in different stages of implementation while the API integrations are completed and tested.

When contributing, never commit real credentials or private API information.

---

# License

See the repository for the current license information.
