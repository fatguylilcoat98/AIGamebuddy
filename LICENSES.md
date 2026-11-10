# Licenses

Buddy's own code is in this repository. The Windows package also runs other people's programs. Read this before selling Buddy.

This is a summary of the upstream licenses, not legal advice.

## Installed by default

These are free-software licenses that allow commercial use if you follow them. GPL cores mean you have to offer the corresponding source and keep their notices. Do not strip those licenses out of the package.

| Piece | Version Buddy pins | License | Commercial use |
| --- | --- | --- | --- |
| RetroArch | 1.22.1 portable Windows x64 | GPL-3.0-or-later | Allowed if the GPL terms are kept |
| FCEUmm (NES) | core shipped beside that RetroArch | GPL-2.0-only | Allowed if the GPL terms are kept |
| bsnes (Super NES) | core shipped beside that RetroArch | GPL-3.0-or-later | Allowed if the GPL terms are kept |
| BlastEm (Genesis) | core shipped beside that RetroArch | GPL-3.0-or-later | Allowed if the GPL terms are kept |
| Python embeddable runtime | 3.12.8 | PSF License | Allowed. Keep the PSF notice |
| Visual C++ runtime | Microsoft redistributable, only if missing | Microsoft's redistribution terms | Allowed under those terms. It is not open source |

CRT-Guest-Advanced NTSC is the shader Buddy turns on when that preset is already inside the RetroArch folder (`shaders/shaders_slang/crt/crt-guest-advanced-ntsc.slangp`). If it is missing, Buddy uses `crt-geom`. If that is missing too, Buddy leaves shaders off. Buddy does not modify the shader source.

## Not installed

Libretro marks these as non-commercial. Buddy does not copy them into the install. Chris has to decide, and get permission, before selling a build that includes them.

| Core | License | Why it is flagged |
| --- | --- | --- |
| Snes9x | Non-commercial | Personal use only. Commercial use needs the copyright holders' permission. |
| PicoDrive | Non-commercial | Libretro's license table lists it as non-commercial. |
| Genesis Plus GX | Non-commercial | The license says it may not be sold or used in a commercial product. |

Mesen is GPL and may be used under the GPL, but it is not the default NES core. FCEUmm is.

## Not in the package

- No ROMs.
- No BIOS files.
- No links to ROM sites.
- The setup wizard tells the user to copy games they already own.

## Not built yet

- A paid license key. `license_hook_status()` returns `not_built`. The installer does not ask for a key.
- Code signing. `packaging/build-windows.ps1` leaves a signtool hook. Set `BUDDY_SIGNTOOL` and `BUDDY_SIGN_PFX` when there is a certificate. Do not commit the certificate.
