# Buddy brain patch

Copy `server.js`, `call.js`, `persona.js`, and `vision_message.js` over the copies on the home server, then restart the brain. Nothing else in the app changes.

Muse sees the latest game JPEG on the current turn only. The user message is an array: a text part, then `{type:'image_url', image_url:{url:'data:image/jpeg;base64,...'}}`. The call is the same one as before: `POST https://api.meta.ai/v1/chat/completions`, model `muse-spark-1.3`, `reasoning_effort` `minimal`, `store` false, `stream` true, and `stream_options.include_usage`. Older pictures are not kept in the history. Buddy talks about the broad action, the game, the characters, and the stage. He does not call a health bar or a PAUSE label unless it is unmistakable, and he says nothing about a black or loading frame.

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
