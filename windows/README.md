# c-ebot — Windows Standalone

c-ebot runs directly on Windows. This is the only supported installation method.

## Requirements

- Windows 10 or Windows 11
- Python 3.12 or newer
- Internet access during initial installation
- A normal Windows user account with permission to run Python

c-ebot does not require any virtualization platform or virtual machine. It runs directly on Windows with a local Python virtual environment.

## Install

From PowerShell in the c-ebot repository folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\install-standalone.ps1
```

The installer creates the local Python environment, installs dependencies, creates the local data directory and starts c-ebot.

Open the dashboard at:

```text
http://localhost:8080
```

## Start c-ebot later

After installation, use:

```text
windows\standalone\start-c-ebot.cmd
```

## Setup

Open **Setup** from the dashboard and enter the required service credentials.

### Chaster

- Chaster developer/access token
- Chaster Lock ID
- For normal add-time operations, the token needs the `locks` scope and the lock must allow the account to **Add time**.
- If c-ebot needs to remove Chaster time as a keyholder, configure the separate Chaster keyholder access token. That account needs the appropriate `keyholder` scope and the lock must allow **Remove time**.

### EmlaLock

- EmlaLock User ID
- EmlaLock API key
- EmlaLock Keyholder API key for subtract-time operations

### Discord

Discord is optional. Enter the bot/application/server/channel settings only if Discord alerts and commands are wanted.

Once the required credentials are saved, c-ebot starts syncing automatically.

## Backup and Restore

Use **Setup** to create a portable encrypted backup before reinstalling or moving c-ebot.

The backup is protected by a password you choose. The password is not stored by c-ebot.

To restore:

1. Install c-ebot on Windows.
2. Open **Setup**.
3. Select the encrypted backup.
4. Enter the backup password.
5. Import the backup.

## Factory Reset

Factory Reset clears the local c-ebot configuration and encrypted credential vault. It requires the exact confirmation:

```text
FACTORY RESET
```

It does not modify your Chaster or EmlaLock accounts or locks.

## Troubleshooting

### Dashboard does not open

Make sure c-ebot is running and open:

```text
http://localhost:8080
```

### API permission errors

Check the Chaster token scopes and the permissions on the specific lock. Add-time requires **Add time** permission. Chaster removal requires **Remove time** permission and, when acting as keyholder, the appropriate keyholder access token.

Never paste real API keys or tokens into support requests or screenshots.
