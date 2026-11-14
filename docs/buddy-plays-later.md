# Later: Buddy plays, and Buddy joins as player 2

Not in this build. Chris wants it after the couch-side commentator is solid.

## Buddy takes the controller

Buddy already has a permission gate that can open for a known offline game and then refuse to send input. The later step is a real input path, still behind that gate.

- The player says he wants Buddy to play, or picks it in the menu. Buddy asks once.
- Buddy only does this for a game he recognizes as offline and already running in RetroArch.
- Input goes in as RetroArch's player-1 port through the core, not by clicking the window. A failed send is said out loud. Buddy never pretends a button landed.
- He gives the controller back the moment the player asks, or when the game closes.
- He does not play online, and he does not keep the pad if the gate closes.

## Buddy joins as player 2

Separate from taking over. The player keeps player 1.

- Works only in games RetroArch is already running with two ports.
- Buddy's pad is port 2. Port 1 is never stolen for this.
- Same permission gate, same "hand it back" line, same refusal when the core has no second port.
- Co-op comments stay in his voice. He does not announce the port number unless something failed.

Both wait until looking, talking, and the frame are boringly reliable.
