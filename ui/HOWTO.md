# How to open the lp2graph demo UI — beginner's guide

A calm, copy-paste walkthrough for testing the demo tomorrow. No prior
networking knowledge assumed. Read the **Big picture** once, then just follow
**The 3 steps**.

---

## Big picture (read once)

Three facts decide everything:

1. **The demo is a web page.** To see it you need a *web browser*.
2. **This machine (`91.99.202.115`) has no browser** — it's a headless server
   you reach over SSH from your laptop. Your browser lives on your **laptop**.
3. **The server only listens on "localhost"** (itself), for safety. The public
   internet can't reach it (the cloud firewall blocks port 8000 — that's why
   `http://91.99.202.115:8000` didn't load).

So we need a private bridge from your laptop's browser to the server. That
bridge is an **SSH tunnel**. It means:

> "On my laptop, make `localhost:8000` secretly point to `localhost:8000` on
> the server, through my existing SSH login."

Then you open `http://localhost:8000` *on your laptop*, and it's really talking
to the server. Encrypted, private, no firewall changes, no extra key.

```
  Your laptop                          The server (91.99.202.115)
 ┌─────────────┐      SSH tunnel      ┌──────────────────────────┐
 │  browser    │  ===============>    │  python server.py        │
 │ localhost:  │   (encrypted)        │  listening on            │
 │   8000      │                      │  localhost:8000          │
 └─────────────┘                      └──────────────────────────┘
```

---

## The 3 steps

### Step 1 — Start the server on the machine

In your normal SSH session to the server, run:

```bash
cd ~/lp2graph/ui
python3 server.py
```

You'll see something like:

```
lp2graph 0.3.0 — demo UI at http://127.0.0.1:8000
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Leave this terminal open — the server runs here. (To stop it later: press
**Ctrl+C** in this window.)

> Prefer it to keep running even if you close the terminal? Start it detached
> instead:
> ```bash
> cd ~/lp2graph/ui
> nohup python3 server.py > /tmp/lp2graph_ui.log 2>&1 &
> ```
> Watch it with `tail -f /tmp/lp2graph_ui.log`, stop it with `pkill -f server.py`.

### Step 2 — Open the tunnel from your laptop

Open a **second terminal on your laptop** (not on the server) and run the same
SSH command you normally use to log in, **with `-L 8000:localhost:8000` added**:

```bash
ssh -L 8000:localhost:8000 joern@91.99.202.115
```

- If you normally pass a key file, keep it:
  ```bash
  ssh -i /path/to/your_key -L 8000:localhost:8000 joern@91.99.202.115
  ```
- This logs you in *and* opens the tunnel at the same time. Just leave this
  window open. (No new key is needed — it's the same login you already use.)

**What `-L 8000:localhost:8000` means**, left to right:
`-L <laptop_port>:<host_as_seen_from_server>:<server_port>`
→ "forward my laptop's port 8000 to localhost:8000 over on the server."

### Step 3 — Open it in your laptop browser

Go to:

## http://localhost:8000

The page loads with an example MILP already translated: editor on the left,
the generated graph in the middle, family + metrics on the right. 🎉

---

## Stopping everything

- **Browser:** just close the tab.
- **Tunnel:** type `exit` in the laptop SSH window (Step 2), or close it.
- **Server:** `Ctrl+C` in the Step 1 window, or if you started it detached:
  ```bash
  pkill -f server.py
  ```

---

## Don't want to keep two terminals? (the `~C` shortcut)

If you're already logged into the server in one terminal and don't want a
second SSH window, you can add the tunnel to your **current** session:

1. Make sure the server is running (Step 1) — easiest with the `nohup` form so
   one terminal can do both.
2. Press **Enter** to be on a clean, empty line.
3. Type **`~C`** (the `~` key, then capital `C`). A small `ssh>` prompt appears.
4. Type:
   ```
   -L 8000:localhost:8000
   ```
   and press Enter. It replies `Forwarding port.`
5. Open `http://localhost:8000` on your laptop.

> If pressing `~C` does nothing: you're probably inside `tmux` or `screen`, or
> another nested SSH — the shortcut only works on the outermost SSH. Just use
> the two-terminal method (Steps 1–3) instead; it always works.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Browser: "can't connect to localhost:8000" | Tunnel (Step 2) isn't running | Make sure the `ssh -L ...` window is open and logged in |
| Browser connects but page is blank/errors | Server (Step 1) isn't running | Start it; check `tail -f /tmp/lp2graph_ui.log` |
| `bind: Address already in use` when starting server | An old server is still running | `pkill -f server.py`, then start again — or use another port: `python3 server.py --port 8010` (and match it in the tunnel: `-L 8010:localhost:8010`) |
| `channel ... open failed: connect failed` in the SSH window | Tunnel is up but server isn't listening | Start the server first, then it'll work — no need to reopen the tunnel |
| `ssh: Permission denied (publickey)` | Wrong/missing key in Step 2 | Use the exact command/key you normally log in with, just add `-L ...` |
| Want a different local port (8000 taken on laptop) | e.g. use 8888 | `ssh -L 8888:localhost:8000 ...` then open `http://localhost:8888` |

Quick server health check (run on the **server**, any time):
```bash
curl -s http://127.0.0.1:8000/api/health
# -> {"ok":true,"lp2graph":"0.3.0"}
```

---

## Cheat sheet

```bash
# ON THE SERVER — start (foreground, Ctrl+C to stop):
cd ~/lp2graph/ui && python3 server.py

# ON THE SERVER — start (background):
cd ~/lp2graph/ui && nohup python3 server.py > /tmp/lp2graph_ui.log 2>&1 &
tail -f /tmp/lp2graph_ui.log     # watch
pkill -f server.py               # stop

# ON YOUR LAPTOP — tunnel + login in one go:
ssh -L 8000:localhost:8000 joern@91.99.202.115

# IN YOUR LAPTOP BROWSER:
http://localhost:8000
```

---

## Later: making it a real public website (for the actual demo day)

The tunnel is perfect for *testing*. For a public, shareable URL you have two
clean options — do this when you're ready, not under time pressure:

1. **Open the firewall + bind public (quick, least secure).**
   In the **Hetzner Cloud console** → your server → *Firewalls*, add an inbound
   rule allowing **TCP 8000**. Then run the server with:
   ```bash
   python3 server.py --host 0.0.0.0
   ```
   and share `http://91.99.202.115:8000`. (No HTTPS, anyone can reach it — fine
   for a short live demo, not for leaving up.)

2. **Reverse proxy with HTTPS (proper).**
   Put nginx or Caddy in front, terminate TLS, proxy to the localhost server.
   Caddy example (`/etc/caddy/Caddyfile`), once you have a domain pointed here:
   ```
   demo.yourdomain.tld {
       reverse_proxy 127.0.0.1:8000
   }
   ```
   Run the app with `python3 server.py` (localhost is correct here — only Caddy
   needs to reach it), and Caddy fetches a certificate automatically. This is
   the setup the UI's main `README.md` ("self-hosted website") refers to.

For tomorrow's quick test, you only need **The 3 steps** above.
