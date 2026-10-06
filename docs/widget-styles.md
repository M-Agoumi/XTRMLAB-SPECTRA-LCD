# Dashboard widget styles

Load a preset from the Dashboard preset picker, then choose **Save layout** to apply it. Loading a preset stages its elements and background together.

| Preset | Style | Appearance |
| --- | --- | --- |
| Nocturne Cathedral | Gothic | Cathedral backdrop, blackletter title, engraved serif readings, silver dials, spear needles, pointed crimson meters, and a lancet album frame. |
| Neon Ronin | Cyberpunk | Rain-soaked futuristic city backdrop, Orbitron lettering, angular bezels and corner brackets, segmented cyan meters, and an angular media frame. |
| Arcane Observatory | High Fantasy | An elven observatory and enchanted forest backdrop, gold astrolabe ornament, carved serif lettering, floral dial tracery, jewel accents, and a gilt album frame. |
| Command Terminal | Cyberpunk, phosphor green | A CRT situation display backdrop whose two wireframe hemispheres sit under the CPU and GPU dials, angular bezels and segmented meters in phosphor green, amber alerts, and a date-showing clock where the screen is blackest. No theme title. |
| Molten Forge | Gothic, ember | A foundry backdrop, engraved serif, spear needles and iron dials in ember orange, a six-reading row along the cooled floor, and heat and clock readings flanking the player. |
| Abyssal | Default | A deep-sea trench backdrop with no dials at all: CPU and GPU are full-height vertical meters against the trench walls, everything else is plain teal type. |
| Sakura Ink | Default, light | The app's only light theme -- sumi-e ink on rice paper, near-black readings, vermilion hairline meters, no album tile. |

Each preset includes Spotify album art, title, artist, elapsed time and progress; CPU and GPU load gauges; RAM, CPU frequency, disk usage, GPU temperature, VRAM and network readings; and a clock with the date. Spotify uses the existing Windows media-session integration and requires `winsdk`; no Spotify API key is needed. Missing sensor readings display `--`, and unavailable media shows a styled placeholder.

## Customization

- **Background → Widget style** selects a shared style for the layout. The background image or procedural mode remains a separate choice.
- **Widget appearance** on an element selects “Use theme style,” a named style, or “Default.” Explicit element settings take priority over inherited defaults.
- Styled gauges, bars and media widgets expose **Accent**, **Metal**, **Text**, **Font**, and **Bold** controls. **Use theme colors and font** clears those overrides.
- Text and digital clocks retain their font, size and color controls. New bundled fonts are **UnifrakturCook** (blackletter) and **Cinzel** (engraved serif); Cyberpunk uses the existing **Orbitron** font.
- Existing geometry, stat binding, opacity, labels, media visibility, clock/date, drag/resize, duplication and preset saving controls still apply. Thin bars can be adjusted down to 1% height in the property panel.
- Album art, song details and progress can each be hidden. Custom idle artwork and idle text continue to work; styled widgets otherwise show “Awaiting Spotify.”

Styled meters use their style's accent and metalwork. Gradient and knob controls apply to the Default renderer. Styled gauges retain numeric metric ticks rather than replacing percentages with decorative Roman numerals. High load/temperature gauge readings use the style's brighter alert accent.

## JSON and inheritance

The repository includes `nocturne_cathedral.json`, `neon_ronin.json` and `arcane_observatory.json`, each in the existing `{ "background": {...}, "elements": [...] }` preset shape. They require this version of the renderer and its bundled assets; the JSON does not embed image or font files.

```json
{
  "background": { "mode": "solid", "scheme": "blue", "widget_style": "cyberpunk" },
  "elements": [
    { "id": "cpu", "type": "gauge", "stat": "cpu_load", "x": 0.2, "y": 0.35, "radius": 0.145 },
    { "id": "music", "type": "media", "x": 0.5, "y": 0.47, "width": 0.315, "height": 0.59,
      "widget_style": "high_fantasy", "color": [70, 190, 145] }
  ]
}
```

Style keys are `gothic`, `cyberpunk`, and `high_fantasy`. Missing/null element values inherit; `widget_style: "default"` opts out. `font: "default"` explicitly selects the system font. Resolution happens on copies at render time, so it never writes inherited values into saved layouts.

Font sources and redistribution notices are in `assets/fonts/LICENSES.md` and the accompanying OFL files. Both rendering and editor previews use bundled fonts; no runtime font download is needed.

All three backgrounds are bundled JPEGs under `assets/backgrounds/`. They were generated with the built-in image generation tool; the final prompts are recorded in [background-prompts.md](background-prompts.md).

## Picture skins

Two optional element fields swap a drawn widget part for a transparent PNG: a bundled one named by file name (`assets/skins/`), or an uploaded one stored in the app's image folder. Any other path is ignored, so a shared preset can't point the renderer at an arbitrary file. Both fall back to the normal drawing when the field is unset or the file can't be read. Export inlines uploaded skins the same way it inlines images.

- **`skin`** on a horizontal `bar` (styled or not): the picture is the meter. Drawn left (0%) to right (100%), scaled to the bar's width with its aspect kept. The empty part shows the picture darkened and faded, and the filled part reveals the picture itself up to the current value, with a hint of the bar's `color`. A katana lights up from hilt to tip, a row of lanterns lights one by one.
- **`face_image`** on a styled `gauge`: the picture replaces the dial face. The track, ticks and live needle still draw over it.

```json
{ "type": "bar", "stat": "ram", "x": 0.1, "y": 0.9, "width": 0.16, "height": 0.055, "skin": "katana.png" }
{ "type": "gauge", "stat": "cpu_load", "x": 0.1, "y": 0.42, "radius": 0.14, "widget_style": "cyberpunk", "face_image": "tsuba.png" }
```

Skins are cut out of rendered images (object on a plain background, then background removal), cropped to the object, and saved with alpha.

## Presets as data

Presets can also ship as files: each `assets/presets/*.json` holds `name`, `bundled_background` (`mode` plus a picture in `assets/backgrounds/`) and the usual `background`/`elements`. The app loads them at startup next to the built-in ones, so a new theme is a JSON file and a picture, no code. A file that can't be read is skipped with a log line.

