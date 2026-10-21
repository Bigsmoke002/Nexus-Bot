# Nexus-Bot

> ⚠️ **Archived test project**
>
> This repository was a private test project (September 2025) and is provided here as an
> archive only. It is **not maintained** and there is **no support**.
> **No guarantee is given that anything works** – use at your own risk.

A self-written Discord bot framework in **Python (discord.py + Flask)** with a web
dashboard and plugins (cogs), plus a separate **Bot Control Tool** to start, stop and
manage bots from a web panel. Internally the bot class is called "Phoenix Bot".

> Note: the dashboards, bot replies, log messages and code comments are in **German**.

## Contents

```
Bot-Controll-Tool/            # web panel to manage bot processes (port 5000)
├── app/                      # Flask app: login, users, bots, live logs, file editor
├── run.py
└── managed_bots/
    └── Nexus-Bot/            # the Discord bot (dashboard on port 5001)
        ├── launcher.py       # start this – supervises run.py and restarts on crash
        ├── run.py            # starts bot + web dashboard
        ├── bot.py            # bot core, loads all cogs recursively
        ├── webapp.py         # Flask dashboard
        ├── cogs/             # plugins
        ├── templates/ static/ pages/
        └── config_handler.py / database.py
```

### Bot Control Tool

- Login with users and admin role (Flask-Login, hashed passwords)
- Admins create users and add bots (upload as ZIP or register an existing folder)
- Start/stop bots, live log output via Socket.IO
- File browser/editor limited to a bot's `cogs/` folder and `config.json`

### Nexus-Bot

- **Web dashboard**: status, system load (CPU/RAM), servers, channels, configuration,
  plugin overview, per-plugin permissions, docs, custom link pages (e.g. a Pterodactyl panel)
- **Login**: local admin via password (from `127.0.0.1` only), remote users via a one-time
  link from the `/accesspanel` command in Discord
- **Crash handler**: `launcher.py` restarts the bot automatically (configurable)
- **Cogs**
  - `AntiSpam` – spam protection (`/antispam`)
  - `verification` – verification with web page, levels, minimum account age,
    duplicate fingerprint blocking (`/verifypanel`, `/verifyconfig`, `/verifylist`,
    `/unverify`, `/unverify_bulk`)
  - `Voice_CreateAndDel` – join-to-create voice channels and auto message delete with web panel
  - `VRC-Bot-Control` – control VRChat client instances with OSC chatbox (`/vrchat`, Windows only)
  - `Games/numbers_game` – counting game (`/numbers_game`)
  - `access_panel` – `/accesspanel` with links to the web plugins

## Setup

Requirement: Python 3.10+ (tested with 3.14).

```bash
python -m venv venv
source venv/bin/activate              # Windows: venv\Scripts\activate
pip install -r Bot-Controll-Tool/requirements.txt
pip install -r Bot-Controll-Tool/managed_bots/Nexus-Bot/requirements.txt
```

**Bot only:**

```bash
cd Bot-Controll-Tool/managed_bots/Nexus-Bot
python launcher.py        # first start creates config.json – add your bot token there
```

Dashboard: <http://127.0.0.1:5001> (default password `admin`).

**With the Control Tool:**

```bash
cd Bot-Controll-Tool
python run.py             # first start creates config.json with login admin / admin
```

Open <http://127.0.0.1:5000>, log in, register the bot folder
(`managed_bots/Nexus-Bot`) in the admin dashboard and start it from there.

### Configuration

Both `config.json` files are created automatically on first start and must **never** be
committed (they contain the bot token, passwords and secret keys).

`Bot-Controll-Tool/managed_bots/Nexus-Bot/config.json`:
`discord_token`, `bot_prefix`, `dashboard_password`, `secret_key`, `base_url`
(public URL of the dashboard, used in links sent by the bot), `web_host`, `web_port`,
`web_plugin_settings`, `crash_handler`, `development`.

Control Tool: `dashboard_password`, `secret_key` in `Bot-Controll-Tool/config.json`;
host/port via the environment variables `CONTROLLER_HOST` / `CONTROLLER_PORT`.

## ⚠️ Security notice

- **Change the default passwords** (`admin`) of both panels immediately.
- The Control Tool lets users edit Python files in `cogs/` – that is code execution on the
  server. It only listens on `127.0.0.1` by default; only expose it with HTTPS and trusted users.
- The bot dashboard treats every request from `127.0.0.1` as "local" (password login).
  Behind a reverse proxy on the same machine all requests look local.
- Both use the Flask/Werkzeug development server.

## Changes compared to the original private version

- Removed: bot token, passwords, secret keys, databases with user data, ZIP backups,
  `__pycache__`, the old Drako Bot JS addons that were not converted yet.
- Fixed: the Control Tool crashed on a fresh install (`pbkdf2:sha266` typo → `sha256`).
- Fixed: Control Tool and bot dashboard both used port 5000; the bot dashboard now uses
  `web_port` (default 5001), the Control Tool binds to `127.0.0.1` by default.
- Fixed: the `VRC-Bot-Control` cog failed to load (command group was added as a cog) and
  `/vrchat dashboard` read a non-existent `port` config key.
- Requirements: pinned versions replaced by minimum versions (the old pins did not install
  on current Python), missing `Pillow`, `python-osc` and `flask-sock` added.

## Known state

Tested (October 2026, Python 3.14, discord.py 2.7, without a real Discord connection):

- Control Tool: fresh start, login (wrong/right password), registering the bot, file browser
  (cogs allowed, other paths and traversal rejected), starting the bot via Socket.IO with
  live logs
- Nexus-Bot: all 8 plugins load, 9 slash commands are registered, dashboard login and all
  pages, web plugins (verification page, voice panel, VRChat dashboard) respond

Not tested with a real bot token / live Discord server. While loading, the bot logs two
harmless "has no 'setup' function" errors for helper modules of `VRC-Bot-Control`.

## License

[MIT](LICENSE)
