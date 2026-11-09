# Streaming Buddy in OBS

Buddy's voice is a separate playback stream with its own volume. The overlay is a top-most window. Use a compact layout if the full frame covers too much of the game.

## Audio

1. Start Buddy with `Start-Buddy.bat`.
2. Install a virtual cable if you want Buddy on his own OBS track. VB-Audio Virtual Cable is the usual one. You can also use OBS Application Audio Capture on Windows 10/11 and skip the cable.
3. Open Buddy's menu and set the output device to that cable (the menu lists names from the PC). If the name is wrong, Buddy does not play audio and he says the device was not found.
4. Set Buddy's volume in the menu. That volume is only his voice.
5. In OBS, add an Audio Input Capture (or Application Audio Capture) for that device. Put your game and your mic on other tracks.
6. Mute Buddy from his menu when you need silence. Mute does not mute the game.

He speaks through Windows System.Speech, then plays the WAV on the device you picked. If speech cannot be created, he shows the line and reports that he did not speak.

## Picture

1. Capture the emulator with Game Capture or Window Capture.
2. Capture the Buddy window with Window Capture. A transparent overlay often needs the capture's "allow transparency" option. If the opening looks like a colored block, the capture is not reading the alpha. Capture the game and the Buddy window as two sources instead of one desktop grab.
3. In Buddy's menu choose **Compact stream layout** when you only want the hologram card. Choose **Full overlay** for the retro frame.
4. The full frame stays at a fixed position. It does not drag. Nudge is not required for a normal test; quit and start again if you need to reset it.
5. Commentary frequency (rare / normal / off) is in the same menu.

## What not to expect yet

Wake word is not implemented. Hold F9 to talk.
Buddy does not take control of a match. The takeover button only reports whether the offline permission gate opened, and it does not send inputs.
