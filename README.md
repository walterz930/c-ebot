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
- Docker-based deployment

## Current status

The repository is being bootstrapped. The EmlaLock API adapter will only be enabled once its exact endpoint/request contract is confirmed from the official API documentation; no API endpoints are guessed.

## Quick start

The first implementation will provide a Docker Compose setup and browser-based configuration wizard. Never commit API keys, Discord tokens, or other secrets to Git.
