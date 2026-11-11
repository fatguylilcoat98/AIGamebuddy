# Buddy brain patch

Copy `server.js` and `call.js` over the copies on the home server, then restart the brain. Nothing else in the app changes.

The overlay does not use the web login cookie. `/ws` now also accepts a device token. Every other route still requires the login cookie.

Set this on the server before restart:

```
BUDDY_DEVICE_TOKEN=a long random string you keep
```

The overlay sends it as the `X-Buddy-Token` header. A `Authorization: Bearer …` header or a `?token=` query on `/ws` is accepted too. The compare is a SHA-256 timing-safe check. If `BUDDY_DEVICE_TOKEN` is empty, the token path stays closed and `/ws` still needs the cookie.

On Chris's PC, create this file (Roaming AppData, not Local):

```
%APPDATA%\Buddy\brain.json
```

```json
{
  "url": "https://buddy.thegoodneighborguard.com",
  "token": "the same string as BUDDY_DEVICE_TOKEN"
}
```

Buddy reads that file when the overlay starts. The token is not written into buddy.log. If the file is missing or the brain is down, Buddy stays quiet.
