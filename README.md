# c-ebot

**Chaster + EmlaLock time synchronization bot for Windows** with a local web dashboard and optional Discord integration.

c-ebot is a **Windows-only application**. It runs directly on Windows using Python and a local virtual environment.

---

## Features

- Highest-time-wins automatic synchronization
- Chaster + EmlaLock timers shown side by side
- Live browser countdown
- Sync Now and Auto Sync controls
- Pause/resume synchronization
- Manual Add Time applied to both services
- Manual Subtract Time applied to both services
- Post-change timer verification
- Automatic pause after a failed synchronized change
- Optional Discord logging and alerts
- Web setup wizard
- Encrypted credential storage
- Credentials are masked after setup and are not displayed again
- Portable encrypted credential backup for restoring after a redownload
- Factory Reset for clearing the local credential vault
- Local audit/history log
- Direct Windows standalone installation

---

# Windows Setup

c-ebot is designed to run directly on a normal Windows PC.

### Requirements

- Windows 10 or Windows 11
- Python 3.12 or newer
- Internet access during the initial installation

No virtualization platform or virtual machine is required. c-ebot runs directly on Windows with a local Python virtual environment.

### Step 1 — Install Python

Install Python 3.12+ and make sure **Add Python to PATH** is enabled during installation.

### Step 2 — Download c-ebot

Download this repository from GitHub using **Code → Download ZIP**, then extract it to a folder on your Windows PC.

### Step 3 — Run the installer

Open PowerShell in the extracted c-ebot folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\install-standalone.ps1
```

The installer will:

1. Create the local Python environment.
2. Install the required packages.
3. Create the local data directory.
4. Create the local application secret.
5. Start c-ebot.
6. Open the dashboard in your browser.

The dashboard will be available at:

```text
http://localhost:8080
```

You can also start it later with:

```text
windows\standalone\start-c-ebot.cmd
```

### Step 4 — Complete setup

Open the **Setup** button at the top of the dashboard and configure:

- **Chaster developer/access token**
- **Chaster Lock ID**
- **Chaster keyholder access token**, when c-ebot must remove Chaster time as the keyholder
- **EmlaLock User ID**
- **EmlaLock API key**
- **EmlaLock Keyholder API key** for subtract-time operations
- **Discord settings**, if Discord is wanted

### Chaster permissions

For Chaster add-time operations, the access token needs the `locks` scope and the account must have **Add time** permission on the specific lock.

For Chaster remove-time operations performed as the keyholder, use the separate keyholder access token. The keyholder account needs the appropriate `keyholder` scope and the lock must grant **Remove time** permission.

Once credentials are saved, c-ebot starts syncing automatically.

---

# Setup and Connections

The dashboard keeps configuration separate from the main timer screen.

Use the **Setup** button at the top to access:

- Service connections
- Credential setup/replacement
- Discord configuration
- Portable backup and restore
- Factory Reset

Credentials are encrypted locally and are not displayed again after saving.

---

# Portable Backup and Restore

c-ebot supports portable encrypted backups so users can completely redownload c-ebot and restore their configuration.

### Before an update or redownload

1. Open **Setup**.
2. Create an encrypted vault backup.
3. Choose a backup password.
4. Save the `.enc` file somewhere safe.

### After redownloading c-ebot

1. Install the new Windows version.
2. Open the dashboard.
3. Go to **Setup**.
4. Select the saved `.enc` backup.
5. Enter the backup password.
6. Import the backup.

The portable backup does **not** require the old installation's `APP_SECRET`.

The backup password is not stored by c-ebot, so it must be kept safe.

---

# Time Synchronization

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

Normal automatic synchronization does **not** shorten the higher timer.

### Add time

A manual add operation adds the same amount to both services.

### Subtract time

A manual subtract operation removes the same amount from both services. EmlaLock subtract operations require the Keyholder API key.

After every modification, c-ebot re-reads both timers and verifies the result.

### Failed synchronization

If one service is changed successfully but the corresponding change fails on the other service, c-ebot pauses automatic changes and records the failure. Discord alerts are sent when Discord is configured.

---

# Security

Never commit these to GitHub:

- Chaster tokens
- EmlaLock API keys
- Discord bot tokens
- Database files
- `.env` files containing secrets

The repository's `.gitignore` is configured to keep local secrets and application data out of Git.

### Factory Reset

Factory Reset clears the locally stored c-ebot configuration and encrypted credential vault. It requires the exact confirmation:

```text
FACTORY RESET
```

Factory Reset does **not** delete or modify your Chaster or EmlaLock accounts or locks.

---

# Troubleshooting

## Dashboard does not open

Make sure c-ebot is running and then open:

```text
http://localhost:8080
```

## Port 8080 is already in use

Stop the application using port 8080 before starting c-ebot.

## API connection errors

Open **Setup** and check the saved connections. Do not paste actual API keys into support requests or screenshots.

## Need to reinstall Windows/c-ebot

Use the portable `.enc` backup and its backup password to restore the configuration after reinstalling.

---

# Project Structure

```text
c-ebot/
├── app/                          # Application source
├── windows/
│   ├── install-standalone.ps1   # Windows installer
│   ├── README.md
│   └── standalone/               # Windows runtime files
├── data/                         # Local runtime data (not committed)
├── .env.example                  # Example environment settings
└── requirements.txt              # Python dependencies
```

---

# Development

c-ebot is a **Windows-only application**. The supported product runs directly on Windows using Python and a local virtual environment.
