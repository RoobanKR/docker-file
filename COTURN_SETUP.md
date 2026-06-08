# Self-Hosted coturn (TURN/STUN) Setup — LMS Live Screens

This is the production relay for the live screen-sharing / proctor monitoring
feature. It replaces the free public OpenRelay (which is rate-limited and fails
under concurrent load) so the system can reliably handle **10–50 simultaneous
screens**.

coturn is **free & open source (BSD)**. The only cost is the small VPS it runs
on (~$5/month is enough for 50 low-res screens).

---

## 1. What you need

- A **VPS with a public IP** (Hetzner, DigitalOcean, Contabo, Linode, AWS…).
  - 1 vCPU / 1–2 GB RAM is plenty for 50 low-res thumbnails.
  - Bandwidth: pick a plan with several TB/month (Hetzner CX22 ≈ 20 TB).
- **Open these ports** (both in the cloud firewall/security group AND on the OS):
  | Port | Proto | Purpose |
  |------|-------|---------|
  | 3478 | TCP + UDP | STUN/TURN |
  | 5349 | TCP + UDP | TURN over TLS (turns:) |
  | 49152–49999 | UDP | **relayed media** — if this is closed, TURN allocates but video never flows (black screen) |
- (Recommended) A **domain/subdomain** pointing at the VPS IP, e.g.
  `turn.yourdomain.com`, so you can enable TLS — TLS on TCP is what gets through
  strict college/corporate firewalls that block UDP.

---

## 2. Install (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y coturn
# Enable the service to run as a daemon:
sudo sed -i 's/#TURNSERVER_ENABLED=1/TURNSERVER_ENABLED=1/' /etc/default/coturn
```

---

## 3. Configure

Edit `/etc/turnserver.conf` (back up the original first). Replace the whole file
with this, filling in the **3 placeholders** (`<PUBLIC_IP>`, `<REALM>`,
`<STRONG_PASSWORD>`):

```ini
# --- Network ---
listening-port=3478
tls-listening-port=5349

# Public IP of the VPS. On clouds with 1:1 NAT (AWS/GCP) where the box sees a
# private IP, use:  external-ip=<PUBLIC_IP>/<PRIVATE_IP>
external-ip=<PUBLIC_IP>

# Constrain the relay media port range (must match the firewall rule above).
min-port=49152
max-port=49999

# --- Authentication (long-term credentials) ---
lt-cred-mech
realm=<REALM>                      # e.g. turn.yourdomain.com  (any string is fine)
user=lmsturn:<STRONG_PASSWORD>     # username:password the app will send

# --- Hardening ---
fingerprint
no-multicast-peers
no-cli
no-tlsv1
no-tlsv1_1

# --- TLS (optional but recommended; see step 5) ---
# cert=/etc/letsencrypt/live/turn.yourdomain.com/fullchain.pem
# pkey=/etc/letsencrypt/live/turn.yourdomain.com/privkey.pem

# --- Logging ---
log-file=/var/log/turnserver.log
simple-log
```

> **Quick start without a domain/TLS:** leave the `cert`/`pkey` lines commented.
> `turn:` on 3478 (UDP+TCP) works immediately with just the public IP. Add TLS
> later for firewall-restricted students.

Start it:

```bash
sudo systemctl enable coturn
sudo systemctl restart coturn
sudo systemctl status coturn        # should be "active (running)"
```

---

## 4. Open the firewall (OS level)

```bash
sudo ufw allow 3478/tcp
sudo ufw allow 3478/udp
sudo ufw allow 5349/tcp
sudo ufw allow 5349/udp
sudo ufw allow 49152:49999/udp
sudo ufw reload
```

**Also open the same ports in your cloud provider's security group / firewall** —
this is the #1 cause of "TURN connects but screen stays black."

---

## 5. (Recommended) Enable TLS with Let's Encrypt

Needs a domain pointing at the VPS.

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d turn.yourdomain.com
# Uncomment the cert= and pkey= lines in /etc/turnserver.conf, then:
sudo usermod -aG ssl-cert turnserver          # let coturn read the certs
sudo systemctl restart coturn
```

Auto-reload certs on renewal:
```bash
echo 'systemctl restart coturn' | sudo tee /etc/letsencrypt/renewal-hooks/deploy/coturn.sh
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/coturn.sh
```

---

## 6. Point the app at your coturn

Edit **`client/src/lib/webrtc.ts`** and fill in the 3 constants at the top:

```ts
const COTURN_HOST = "turn.yourdomain.com"; // or your raw "203.0.113.10"
const COTURN_USERNAME = "lmsturn";         // must match user= in turnserver.conf
const COTURN_CREDENTIAL = "<STRONG_PASSWORD>";
```

Then **rebuild + redeploy the client** (`next build`) — `webrtc.ts` is compiled
in, so a redeploy is required.

Once you've confirmed it works, delete the `// FALLBACK ONLY` OpenRelay block in
`webrtc.ts` so all traffic uses your own relay.

---

## 7. Verify it actually relays

1. Open the [Trickle ICE tester](https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/).
2. Remove the default STUN row. Add your server:
   - URI: `turn:turn.yourdomain.com:3478`
   - Username: `lmsturn`  ·  Credential: `<STRONG_PASSWORD>`
3. Click **Gather candidates**. You MUST see a candidate of **type `relay`**. ✅
   - Only `host`/`srflx` and no `relay` → wrong creds, or the relay UDP port
     range / firewall is blocked. ❌

Server-side check:
```bash
sudo tail -f /var/log/turnserver.log     # watch allocations appear when students connect
```

---

## 8. Sizing for 50 screens

- **Bitrate:** grid thumbnails are ~200 kbps each. 50 × 200 kbps ≈ **10 Mbps**
  total (only the fraction that can't go peer-to-peer is actually relayed).
- **Monthly:** worst case all-relay, 1-hour exam ≈ 4–9 GB. A 20 TB plan covers
  hundreds of exams.
- **CPU/RAM:** coturn just forwards packets — a 1 vCPU box handles this easily.
  (The heavier load is on the *proctor's browser*, which decodes all the streams
  — that's a client-side limit, not a coturn one.)

---

## 9. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Trickle ICE shows no `relay` candidate | Firewall (cloud SG **or** ufw) blocking 3478 or the 49152–49999 UDP relay range |
| `relay` works in tester but screen still black | Client not rebuilt after editing `webrtc.ts`, or `external-ip` wrong on a NAT'd cloud |
| Works on Wi-Fi, fails on campus/corporate net | UDP blocked → make sure **TLS `turns:5349/tcp`** is enabled (step 5) |
| 401/Unauthorized in turnserver.log | `username`/`credential` in `webrtc.ts` don't match `user=` in turnserver.conf, or `realm` missing |
| Service won't start | Run `sudo turnserver -c /etc/turnserver.conf` to see the config error |
