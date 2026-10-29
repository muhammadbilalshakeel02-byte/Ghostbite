# GhostBite

> One-click browser virus. Self-hosted. Public link in one command.

GhostBite serves a prank-malware page and automatically opens a Cloudflare
quick tunnel so the link works on **any network** — not just your WiFi. The
victim taps once and their browser turns into a fake infected phone.

No accounts. No API keys. No port forwarding. No router config.

---

## What it does

On a single tap (just opening the link):

- Fake system scan → "7 VIRUSES FOUND"
- Ad popup storm with fake prize / storage-full / trojan alerts
- Vibration pulses (Android)
- Screen strobe + shake
- Native `alert()` popups
- Web Notifications spam (if allowed)
- Browser tab title flicker
- Back-button trap (5 presses before it releases)
- 2,500 junk DOM nodes to make the page sluggish
- Fake "SYSTEM COMPROMISED" HUD with the victim's real device data

## Persistence

GhostBite writes to **four** independent stores on first load:

1. `localStorage`
2. A 1-year cookie
3. IndexedDB (`ghostbite` database)
4. A Service Worker cache

If any of those exist on the next visit, GhostBite skips the scan and
re-infects instantly with a "STILL INFECTED" banner.

This survives: tab close, browser restart, phone reboot, airplane mode,
cache-clear-without-site-data.

It dies on: "Clear cookies and site data", private/incognito window, or
factory reset.

---

## Requirements

- Python 3.8+
- Termux (Android) or Kali Linux
- ~30 MB free for the `cloudflared` binary (auto-downloaded)

---

## Installation

### Termux

```bash
pkg update && pkg upgrade -y
pkg install python git -y
mkdir ghostbite && cd ghostbite
# create main.py, requirements.txt, README.md, LICENSE
pip install --upgrade pip
pip install -r requirements.txt
python3 main.py