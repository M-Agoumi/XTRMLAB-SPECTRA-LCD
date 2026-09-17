# Dashboard background prompts

Generated with the built-in image generation tool. The selected outputs were converted to JPEG at quality 90, without cropping or creative edits. Originals were 1774×887 (2:1), cover-fitted by the renderer to the panel. Each preset applies its own dimming value so labels remain readable.

## Nocturne Cathedral — `assets/backgrounds/nocturne_cathedral.jpg`

```text
Use case: stylized-concept
Asset type: background image for a 2:1 landscape PC LCD dashboard, with live UI text and gauges layered on top
Primary request: heavy gothic cathedral atmosphere
Scene/backdrop: symmetrical interior of a ruined gothic cathedral at night, tall pointed arches, ornate stone tracery, subtle iron filigree, faint stained glass, mist and aged stone
Style/medium: richly detailed dark fantasy matte painting, elegant and dramatic, believable architectural detail
Composition/framing: wide 2:1 layout; architecture frames the left and right edges and top; central 45% remains very dark and visually quiet for a music player; lower third also dark and calm for data labels; no dominant central subject
Lighting/mood: restrained crimson stained glass glow with desaturated silver moonlight, ominous but readable
Color palette: near-black charcoal, oxblood red, antique silver, muted violet
Constraints: no lettering, no logos, no UI, no people, no skulls, no crosses, no watermarks. This must function as a subdued dashboard background, with excellent text contrast.
```

## Neon Ronin — `assets/backgrounds/neon_ronin.jpg`

```text
Use case: stylized-concept
Asset type: background artwork for a 960x480 PC sensor and Spotify dashboard, exact wide 2:1 landscape aspect ratio
Primary request: a cohesive heavy cyberpunk background for the Neon Ronin theme
Scene/backdrop: rain-soaked futuristic megacity at night, towering industrial architecture, layered elevated infrastructure, atmospheric haze, worn metal and cyan neon reflected on wet surfaces; a few restrained amber highlights
Style/medium: richly detailed cinematic science fiction matte painting, sophisticated and atmospheric
Composition/framing: architecture, cables, pipes, and light sources concentrated at far left and right edges and upper corners; the middle 35 percent is near-black empty mist for album art and music text. Left and right widget areas around 18 and 82 percent of the width must remain subdued, especially from 20 to 90 percent of image height. Lower third dark and quiet. Strong depth and atmosphere without a central subject.
Color palette: midnight navy, charcoal, deep teal, cyan lighting, rare warm amber
Constraints: no text, no logos, no signs with lettering, no numbers, no UI, no gauges, no characters, no vehicles in foreground, no watermark. Leave excellent contrast for cyan and pale text over the image.
```

## Arcane Observatory — `assets/backgrounds/arcane_observatory.jpg`

```text
Use case: stylized-concept
Asset type: background artwork for a 960x480 PC sensor and Spotify dashboard, exact wide 2:1 landscape aspect ratio
Primary request: a cohesive high fantasy background for the Arcane Observatory theme
Scene/backdrop: an ancient elven observatory open to a night sky, delicate carved stone pillars at the far edges, golden astrolabes and ornate celestial metalwork near the upper corners, ivy and ancient roots, a distant enchanted forest, subtle drifting emerald motes, deep atmospheric mist
Style/medium: richly detailed high fantasy matte painting with elegant craftsmanship, luminous restrained magic, enchanting and timeless
Composition/framing: pillars and leaves frame the outer edges; the central 35 percent is very dark emerald mist and clear negative space for a music player, with no giant moon or object in the center. Side widget areas near 18 and 82 percent of width are subdued and dark from 20 to 90 percent of image height. Lower third is quiet dark stone and mist for readings. Deep perspective, beautiful architectural detail concentrated around edges.
Lighting/mood: antique gold starlight touching carved details, subtle emerald light in the forest, a few distant tiny stars, mysterious and tranquil
Color palette: near-black forest green, deep teal, aged gold, muted ivory
Constraints: no text, no lettering or numbers, no logos, no UI, no gauges, no people, no creatures, no watermark. Maintain excellent contrast for warm ivory text and gold widget outlines.
```

---

# Requested backgrounds — four new themes

These four have layouts designed but no artwork yet. Generate each image
from the prompt below (ChatGPT, or any image model that takes a long
prompt), save it as PNG or JPEG at the given name, and drop all four in
`C:\Users\agoum\Downloads\theme-backgrounds\`. They get converted to
JPEG quality 90 and bundled under `assets/backgrounds/`; no cropping is
needed as long as the aspect ratio is right.

**Every one of them: exactly 2:1 landscape** (the panel is 960×480).
1774×887 like the three above is ideal; anything 2:1 and at least
1440×720 is fine. Ask for "no cropping, full 2:1 frame".

**Why the composition lines are so specific:** the widgets sit at fixed
fractions of the panel, so the art has to leave those regions quiet or
the readings become unreadable. The middle ~35% is the music player on
all four, the two side columns near 18% and 82% of the width hold the
gauges, and the bottom third carries the text readings. Art belongs at
the edges and in the corners. If the model returns something with a big
bright subject in the middle, regenerate rather than settling — that
one region decides whether the theme looks designed or looks like text
dumped on a wallpaper.

## Command Terminal — `command_terminal.jpg`
Widget style: cyberpunk, recoloured to phosphor green.

```text
Use case: stylized-concept
Asset type: background artwork for a 960x480 PC sensor and music dashboard, exact wide 2:1 landscape aspect ratio
Primary request: a cold-war underground command centre display for the Command Terminal theme
Scene/backdrop: a vintage CRT tactical situation display: faint wireframe continents and orbital tracks rendered in thin phosphor-green vector lines, a fine hex grid, range rings and tick marks, subtle scanlines and screen curvature, faint burn-in glow, dust and glass reflection
Style/medium: retro-futuristic vector graphics on a dark CRT, thin crisp lines, no photorealism, no 3D rendering, restrained and technical
Composition/framing: the wireframe map and range rings sit in the upper-left and upper-right quadrants and fade out toward the middle; the central 35 percent of the frame is near-black empty screen for a music player, with no globe, no reticle and no bright object in the centre; side widget areas near 18 and 82 percent of the width stay dark and uncluttered from 20 to 90 percent of image height; the lower third is almost empty screen with only the faintest grid
Lighting/mood: self-lit phosphor glow in a dark room, calm and analytical, slight vignette
Color palette: near-black, deep green-black, phosphor green, rare amber warning accent
Constraints: no text, no lettering, no numbers, no country labels, no logos, no UI panels, no gauges, no people, no watermark. Lines must stay thin and dim enough that pale green text reads clearly on top.
```

## Molten Forge — `molten_forge.jpg`
Widget style: gothic, recoloured to ember and black iron.

```text
Use case: stylized-concept
Asset type: background image for a 2:1 landscape PC LCD dashboard, with live UI text and gauges layered on top
Primary request: a heavy industrial forge interior for the Molten Forge theme
Scene/backdrop: the inside of an enormous ancient foundry at night: black iron columns and riveted plate, hanging chains, brick furnace arches with banked coals behind them, drifting soot and ember sparks, cracked stone floor with thin cooling lava seams
Style/medium: richly detailed dark industrial matte painting, weighty and physical, believable metalwork and masonry
Composition/framing: the furnace arches, columns and chains frame the far left and far right edges and the upper corners; the central 35 percent is dark smoke and empty air for a music player, with no forge, anvil or fire in the centre; side widget areas near 18 and 82 percent of the width stay in shadow from 20 to 90 percent of image height; the lower third is dark cooled stone, with any lava seams thin, sparse and confined to the very bottom edge
Lighting/mood: deep orange furnace glow from the left and right edges falling off fast into blackness, a few floating embers, oppressive heat, everything else in shadow
Color palette: near-black charcoal, black iron grey, ember orange, dull brass, rare white-hot highlight
Constraints: no text, no lettering, no logos, no UI, no gauges, no people, no anvil in the centre, no watermark. The middle and lower thirds must stay dark enough for pale amber text to read cleanly.
```

## Abyssal — `abyssal.jpg`
Widget style: default renderer, gradient gauges in teal and violet.

```text
Use case: stylized-concept
Asset type: background artwork for a 960x480 PC sensor and music dashboard, exact wide 2:1 landscape aspect ratio
Primary request: a bioluminescent deep-ocean trench for the Abyssal theme
Scene/backdrop: the walls of a deep sea trench closing in from both sides, encrusted rock and pale coral, slow drifting marine snow, a few small bioluminescent jellyfish and glowing filaments clinging to the rock, faint god rays dissolving in the water far above, immense darkness below
Style/medium: atmospheric underwater matte painting, soft focus and heavy water haze, quiet and vast
Composition/framing: the trench walls occupy the far left and far right edges and the upper corners; the central 35 percent is open black water for a music player, with no creature, no submarine and no bright object in the centre; side widget areas near 18 and 82 percent of the width stay dim from 20 to 90 percent of image height; the lower third is near-black silt and deep water with only a few drifting particles
Lighting/mood: cold bioluminescent teal and violet light from the trench walls, one faint distant shaft of surface light from the top, everything else fading to black, still and weightless
Color palette: near-black navy, abyssal teal, cyan glow, muted violet, pale bone coral
Constraints: no text, no lettering, no logos, no UI, no gauges, no divers, no boats, no large fish or whale in the centre, no watermark. Keep excellent contrast for pale cyan text over the middle and lower areas.
```

## Sakura Ink — `sakura_ink.jpg`
Widget style: default renderer, stat text rows, engraved serif.

```text
Use case: stylized-concept
Asset type: background artwork for a 960x480 PC sensor and music dashboard, exact wide 2:1 landscape aspect ratio
Primary request: a minimal Japanese sumi-e ink wash for the Sakura Ink theme
Scene/backdrop: aged rice paper with visible fibre and a faint warm stain, a distant ink-wash mountain ridge and mist along the upper third, a single bare cherry branch entering from the top-left corner and a smaller one from the top-right, a handful of loose petals drifting, one small crimson seal stamp in the upper-right corner
Style/medium: traditional sumi-e brush painting, black ink on paper, generous empty space, confident sparse strokes, absolutely no digital gloss
Composition/framing: ink work is confined to the upper third and the two top corners; the central 35 percent is clean empty paper for a music player, with no mountain peak, tree trunk or blossom cluster in the centre; side widget areas near 18 and 82 percent of the width stay pale and unmarked from 20 to 90 percent of image height; the lower third is bare paper with at most two or three faint drifting petals
Lighting/mood: flat even daylight on paper, tranquil, unhurried, nothing dramatic
Color palette: warm off-white paper, soft grey ink washes, deep black ink accents, one vermilion red seal
Constraints: no text, no calligraphy, no kanji, no signature, no logos, no UI, no gauges, no people, no buildings, no watermark. The paper is light, so keep the centre and lower third clean and untextured enough for dark ink-coloured text to read clearly.
```
