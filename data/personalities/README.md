# Personality packs

Buddy loads three modes from this folder. Drop a replacement pack in place; do not rename the mode folders.

```
data/personalities/ANTI-REPETITION.md
data/personalities/casual/STYLE.md
data/personalities/casual/seeds.json
data/personalities/casual/templates.json
data/personalities/sassy/...
data/personalities/extreme/...
```

- `STYLE.md` is the voice guide. It is sent to the model. It does not contain lines Buddy recites.
- `seeds.json` maps each of the 20 event categories to example lines. Those examples teach tone. Buddy does not play them back.
- `templates.json` maps the same categories to fresh shapes with `{placeholders}`. A template is spoken only when every placeholder is a fact Buddy already has (a count, a confident game title, a remembered event). Missing facts stay blank, and the line is skipped.
- `ANTI-REPETITION.md` is the angle list and the cooldown rules. Angle ids rotate inside a category. A blocked line is not spoken.

`regular` in the menu means `casual`. The character is Buddy. Do not put the name Zion in a pack.
