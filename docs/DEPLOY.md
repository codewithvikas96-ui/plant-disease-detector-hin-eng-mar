# Putting the app on a public URL

Uses **Cloudflare Tunnel**. Free, no account, no card, running in under a minute.

Your laptop keeps serving the app; Cloudflare gives it a public HTTPS address. Nothing is
uploaded, nothing is hosted, nothing sleeps.

---

## Running it

Two windows, in this order:

**Window 1** — the app
```
scripts\start.bat
```

**Window 2** — the tunnel
```
scripts\tunnel.bat
```

`tunnel.bat` checks the server is actually up first, then prints a box containing your URL:

```
https://champions-demanding-fioricet-dozen.trycloudflare.com
```

That address works from any phone on any network — mobile data included, no shared Wi-Fi
needed. HTTPS is real, so *Add to Home screen* and the service worker both work.

It is also the only way a phone gets the **whole** app: browsers allow the live camera guide,
location (spray timing, outbreak map) and the microphone (voice questions) only on `https://`.
On the plain `http://192.168.x.x` Wi-Fi address those fall back or hide.

**Keep both windows open.** Closing either one breaks the link.

---

## Which window matters

| You stop | What happens to the URL |
|---|---|
| The app (`start.bat`) | URL **stays alive**. Visitors get `502` until you restart it, then the **same URL works again**. |
| The tunnel (`tunnel.bat`) | URL is **gone permanently**. Next run gives a different one. |

So you can restart the app freely without invalidating a printed QR code. Never Ctrl+C the
tunnel window — that's the irreversible one.

---

## The one catch

**The URL changes every time you restart the tunnel.** Quick tunnels are anonymous and
temporary, so there's no free way to keep a fixed address.

If you ever need a permanent one, it requires a domain on Cloudflare (~₹800/year) and a
*named* tunnel instead of a quick tunnel.

---

## Port already in use

If `start.bat` fails with `[Errno 10048] only one usage of each socket address`, a server is
already running. Find and stop it:

```powershell
netstat -ano | findstr :8000
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess | Stop-Process -Force
```

Only ever have one `start.bat` window open at a time.

---

## Verified working

Tested end to end on 2026-09-23 — `/api/health`, the PWA shell, service worker and manifest all
served correctly over the public HTTPS URL, with the model loaded at 99.53% validation accuracy.

---

## For the competition

**Do not make the public URL your primary demo.** Venue Wi-Fi fails, and a dead link in front
of a judge is unrecoverable. Run the live demo from your laptop with your phone on your own
hotspot — that depends on nothing external.

Use the public URL for a poster QR code so judges can try it themselves afterwards.

On the day:

1. Start `start.bat`, then `tunnel.bat`
2. Generate the QR code from the URL it prints
3. Leave the tunnel window untouched all day
4. **Disable sleep** — `Settings → System → Power → Screen and sleep → Never`. Sleep kills both
   processes and you would have to reprint the QR code.

Worth rehearsing once beforehand: with both running, close `start.bat`, reload the URL (expect
502), reopen `start.bat`, reload again. Confirming it recovers on the same URL means you know
your fallback under pressure.
