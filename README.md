# FOFUS CAD Suite

One installer for **Blender**, **Fusion 360** and **SolidWorks**. Log in with your FOFUS account inside your CAD tool and the web app follows you in — **Account | Works | Earnings** tabs right in the sidebar, plus buttons to open your full dashboard.

## Install (2 minutes)

1. Download **FOFUS-CAD-Suite-1.1.0.zip** from [Releases](../../releases/latest)
2. Unzip and run **install.bat** (or `py install.py`)
3. Open your CAD tool → **FOFUS panel** → **Log in with FOFUS**

Your browser opens designai.fofus.in once; the plugin links itself and shows your account. That's it — when you're genuinely designing, customers see you **Online** on the FOFUS roster.

### Tool-specific finishing steps

| Tool | After install.bat |
|---|---|
| Blender | Edit → Preferences → Add-ons → tick **FOFUS CAD Suite** |
| Fusion 360 | Utilities → Add-Ins → **FofusCadSuite** → Run (tick *Run on startup*) |
| SolidWorks | Admin cmd: `regasm /codebase FofusCadSuite.dll` → Tools → Add-Ins → **FOFUS CAD Suite** |

## What it does

- **Login** — first run asks for your FOFUS account (browser handoff, or email + password). Only your session token is stored on this PC.
- **Tabs inside the tool** —
  - **Account** — your name, rank, wallet and points.
  - **Works** — your live job board: project, stage, price, est. earnings, deadline, unread-chat badge; buttons to open the full board and find new work.
  - **Earnings** — available / pending / lifetime wallet + your last earn events; jump to withdrawal.
  - **Dashboard** — open the full web app in your browser.
  - Blender shows the full tab experience; Fusion 360 and SolidWorks show Works + Earnings as text panels and one-click deep links.
- **Presence** — signed heartbeats prove you're actively designing. Nothing about your files, paths or screen ever leaves your PC: only `{tool, active, idle_sec}` crosses the wire.
- **Privacy** — log out anytime (inside the plugin), and revoke the device from the dashboard → Connect CAD.

## Privacy & security

- Only activity status crosses the wire — never filenames, paths or screens.
- Heartbeats are HMAC-signed; tokens can be revoked per device anytime.
- Login handoff happens over HTTPS; the localhost receiver listens only on 127.0.0.1 during login.

## Build from source

- Blender: plain Python, no build needed.
- Fusion 360: zip in `adapters/fusion360/` is the shipping form.
- SolidWorks: see `adapters/solidworks/BUILD-SOLIDWORKS.txt`.

## Links

- Dashboard (account details): https://designai.fofus.in
- Store: https://store.fofus.in/in/store
- FOFUS: https://fofus.in

© 2026 FOFUS · GNI Labs LLP, Thrissur, Kerala, India