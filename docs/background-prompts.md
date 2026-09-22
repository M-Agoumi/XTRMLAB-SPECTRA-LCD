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

All four are done -- generated from these prompts and shipped. The
notes below are kept as the record of what was asked for, and as the
template for the next one.

Originally: Generate each image
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

## Command Terminal — `command_terminal.jpg` — **done**
Widget style: cyberpunk, recoloured to phosphor green. Generated from
the prompt below at 1774×887 and bundled as
`assets/backgrounds/command_terminal.jpg`; the theme ships as the
"Command Terminal" preset.

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

## Molten Forge — `molten_forge.jpg` — **done**
Generated from the prompt below at 1774×887 and bundled as
`assets/backgrounds/molten_forge.jpg`; the theme ships as the "Molten Forge" preset.

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

## Abyssal — `abyssal.jpg` — **done**
Generated from the prompt below at 1774×887 and bundled as
`assets/backgrounds/abyssal.jpg`; the theme ships as the "Abyssal" preset.

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

## Sakura Ink — `sakura_ink.jpg` — **done**
Generated from the prompt below at 1774×887 and bundled as
`assets/backgrounds/sakura_ink.jpg`; the theme ships as the "Sakura Ink" preset.

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

---

# Character themes — rendered locally from Stable Diffusion recipes

Unlike the backgrounds above, these were rendered on a local ComfyUI from hand-picked civitai
recipes (a checkpoint plus LoRAs and sampler settings copied from a published image), as ONE
image with the figure and scene together, so the character shares the scene's light and
brushwork. Rendered at 1536x768 (2:1; some recipes add a hires-fix pass), then resized to 1774x887
JPEG q90 like the rest. The busier ones got a light blur (under 1px at panel size) so a full
panel frame still fits the panel's 80KB-per-frame JPEG cap at quality 75 or better; the driver
otherwise has to drop quality until it fits, which shows as blockiness. Where the art under the
widgets is busy, a soft feathered shade is baked in under them (no edges) so the text holds 4.5:1.

## Cyber Samurai — `cyber_samurai.jpg`
Seed 11; recipe `pick-rimix-samurai` on lane `rimix-illust` (`riMixIllustrious.safetensors`), LoRAs: detailer_tool_illust @ 0.9, callis_dystopian_sheek_illust @ 0.85, dynamic_poses_slider_illust @ 2.0, my_color_locon @ 1.0; euler_ancestral/normal, 32 steps, cfg 4.5, hires fix.

```text
1girl, sci-fi aesthetic, cyberpunk, samurai, huge ponytail, black and white kimono, DS-Illu, off shoulder, mature female, beautiful japanese woman, ((cybernetic arm)), katana over shoulder, earrings, cowboy shot, standing at the far left edge of the image, looking over her shoulder at viewer, proud pose, shinto design elements, modern technology, ink splash, glowing particles, very wide landscape composition, the right two thirds of the image is a dark rainy neon city at night fading into dark mist and deep shadow, empty and quiet, masterpiece, best quality, very aesthetic, depth of field, adult
```

## Crimson Priestess — `crimson_priestess.jpg`
Seed 11; recipe `pick-janku-13` on lane `janku` (`janku_v5_illust.safetensors`), LoRAs: dramatic_lighting_slider_pony_illu @ 2.4, sinozick_shiiro_s_styles_niji @ 0.7, trendcraft_the_people_s_style_detailer_noob_ @ 0.4; euler_ancestral/karras, 40 steps, cfg 4.5, hires fix.

```text
lazypos, Sinozick_illu, gradient, spot color, ((masterpiece, best quality, high quality)), ((greyscale with red)), high details, epic movie scene, very wide landscape composition, honorable white warrior priestess standing on top of a cliff at the far left edge of the image, absurdly long red hair blowing in the wind, braided hair, tattered archaic armor, linen embroidered tabard, holding a long sword, solo, intimidating expression, the rest of the image is an enormous empty grey misty sky over distant grey mountains, calm, quiet negative space, only the hair is red
```

## Moebius Pilot — `moebius_pilot.jpg`
Seed 11; recipe `pick-krea2-07` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: krea2_purpledreams @ 0.6; euler/normal, 8 steps, cfg 1.0, hires fix.

```text
ta86_inkriot, thin black outlines, art by Jean Giraud (Moebius), watercolor and ink illustration, very wide panoramic landscape, a female pilot holding a white helmet at the far right edge of the image, wearing a complex mechanical flight suit with black hoses and cables, the wreckage of a crashed mecha at the far left edge, between them a vast empty pale desert and an enormous open cloudy sky that fills the middle of the picture, calm and airy, another ship flying away tiny in the distance, vintage sci-fi comic art style, detailed linework, muted cream, sand and faded teal colors
```

## Ukiyo Tide — `ukiyo_tide.jpg`
Seed 11; recipe `pick-krea2-05` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: iiyo_sumi_ukiyo_e_sumi_e_flat_art_ @ 1.0, detailcore_forever_by_stx @ 0.8; euler/normal, 8 steps, cfg 1.0, hires fix.

```text
ukiyo-e woodblock print, flat colors, bold outlines, wide panoramic landscape, enormous curling ocean waves with white foam claws rising at the far left edge and the far right edge of the image, framing the scene, the center of the image is a calm pale sky above a quiet sea with a tiny snow-capped mount fuji low on the horizon, the middle third is empty and quiet, lower third calm flat water, prussian blue, indigo, cream paper and soft grey palette, aged paper texture, no text, no calligraphy, no seal, no signature, no boats in the center
```

## Solarpunk Haven — `solarpunk_haven.jpg`
Seed 11; recipe `pick-krea2-34` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: mrpopo_s_krea2_anime_art_enhanced @ 1.0; euler/normal, 8 steps, cfg 1.0, hires fix.

```text
An aerial perspective of a serene sun-drenched solarpunk city, ancient stone arches and white terraces overgrown with lush hanging gardens stand at the far left and far right edges of the image, curved glass solar sails and small wind turbines on the rooftops, flowering trees with orange-red leaves, the whole center of the image is a calm, wide, clear turquoise lagoon with gentle ripples and nothing on it, the lower third is quiet still water, warm golden sunlight, soft shadows, anime art, painterly, wide panoramic composition, palette of turquoise, sage green, ivory stone and warm orange accents, no text, no people
```

## Rogue Unit — `rogue_unit.jpg`
Seed 11; recipe `pick-krea2-31` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: grandline_legendary_stylized_illustration @ 0.65, afterveil_worn_memory_style @ 0.85; euler/normal, 8 steps, cfg 1.0, hires fix.

```text
digital painting of a dark menacing robot with a hooded tattered cloak standing at the far right edge of a very wide image, its head partially open revealing glowing orange internal lights, heavily damaged armor with exposed glowing red and orange elements, dark wet cloak in tattered strips, the rest of the image is empty foggy dark grey atmosphere with faint distant ruined towers, moody ominous, low-angle, very dark and quiet on the left two thirds
```

## Sky Whale — `sky_whale.jpg`
Seed 22; recipe `pick-krea2-24` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: between_pages @ 1.0; euler_ancestral/normal, 8 steps, cfg 1.0, hires fix.

```text
PagesDaal, a surreal storybook scene, a colossal gentle sky-whale drifts between enormous soft clouds along the far right side of a very wide panoramic image, carrying a tiny cottage, vegetable garden and clothesline on its back, a tiny traveler in an umbrella-shaped flying boat far off at the left edge, the middle of the picture is open pale peach and cream sky with thin wisps of cloud, calm and airy, gentle morning light, soft pastel colors
```

## Neon Courier — `neon_courier.jpg`
Seed 11; recipe `pick-krea2-40` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: krea2_flux_vividly_surreal @ 1.0; euler_ancestral/normal, 8 steps, cfg 1.0, hires fix.

```text
Realistic detailed cyberpunk comic art in the style of Frank Quitely, very wide panoramic image, a young adult woman courier in an oversized hoverbike helmet with an orange visor leans against a grungy metal wall at the far left edge, her hoverbike parked beside her, the rest of the image is a rainy cyberpunk street at night stretching into the distance with neon signs reflected in puddles, deep blue shadows, the right two thirds dark and uncluttered, no readable text on signs
```

## Summer Coast — `summer_coast.jpg`
Seed 11; recipe `pick-wai-illustrious-16` on lane `wai-illustrious` (`waiIllustrious_v14.safetensors`), LoRAs: none; euler_ancestral/normal, 30 steps, cfg 7.0, hires fix.

```text
A very wide eye-level anime illustration of a lush sunlit meadow, a fluffy round bumblebee with velvet yellow and black fur and iridescent wings hovers near the far left edge, tall wildflowers and clover along the bottom corners, the middle and top of the image is a soft bright blue sky with a few round white clouds, cheerful, clean, lots of open space, vibrant colors
```

## Toon Knight — `toon_knight.jpg`
Seed 22; recipe `pick-krea2-39` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: cartoon_world @ 1.0; euler/simple, 7 steps, cfg 1.0, hires fix.

```text
ToonDaal, a very wide cartoon landscape, a knight in heavy armor riding a tiny fat horse with whimsically thin legs at the far right edge, oversized sword raised to the sky, the horse looks exhausted with its tongue hanging out, rolling green hilltops and distant forests, a huge clear blue sky with a few puffy clouds fills the left and middle of the image, bright and funny
```

## Night Bus — `night_bus.jpg`
Seed 22; recipe `pick-krea2-33` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: geffstyle_stylemix_by_lostcut_style_krea2_lo @ 1.0; euler/simple, 8 steps, cfg 1.0, hires fix.

```text
2d, geffstyle, a deeply atmospheric and textural oil painting with visible gritty brushstrokes and a rich limited color palette, very wide view of the inside of an empty city bus at night, warm dim interior lights, a tired young woman dozing against the rain-streaked window at the far right, the long row of empty seats and dark rainy windows with blurred city lights stretching to the left, cozy lo-fi mood, deep blues and warm amber
```

## Steel Horizon — `steel_horizon.jpg`
Seed 11; recipe `tab-krea2-286` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: yoshitaka_amano_final_fantasy_style_for_anim @ 1.0, frank_frazetta_style_oil_painting_krea2_flux @ 1.0, retro_anime_style @ 1.0, steel_horizons_mecha_sci_fi_lora @ 1.0; euler_ancestral/normal, 8 steps, cfg 1.0.

```text
retro anime illustration, wide cinematic interior of a dark mecha hangar at night, a giant armored mecha robot stands at the far right edge of the frame, only its right side visible, cropped by the image border, amber warning lights and hazard stripes, steel scaffolding and cables along the top edge, the left two thirds of the image is a dark quiet empty hangar wall with deep shadow and faint haze, very dark and low contrast behind where text will go, color palette of near-black gunmetal, deep teal shadow and warm amber highlights, no text, no letters, no numbers, no logos, no people
```

## Ink Ronin — `ink_ronin.jpg`
Seed 22; recipe `anima-inkwash` on lane `anima` (`oneObsessionAnima_v30.safetensors`), LoRAs: none; euler/simple, 30 steps, cfg 5.0.

```text
masterpiece, best quality, absurdres, wide landscape composition, ink wash, sumi-e, visible brushwork, expansive negative space, aged rice paper texture, a lone swordswoman with long red hair and a black coat standing at the far left edge of the frame, seen from behind, katana held low, her figure fills the left quarter of the image, faint misty mountains painted in pale grey ink along the distant horizon, a few red plum blossom petals drifting, the right three quarters of the image is empty pale rice paper with only soft faded mist, calm and quiet, muted palette of charcoal black, warm paper beige and a single vermilion accent, no text, no seal stamp, no signature
```

## Oni Lounge — `oni_lounge.jpg`
Seed 11; recipe `pick-hassaku-14` on lane `hassaku` (`hassakuXL_illust_v13a.safetensors`), LoRAs: noobai_xl_detailer @ 1.0, dramatic_lighting_slider_pony_illu @ -0.35, ma1ma1helmes_shiiro_s_styles_niji @ 0.45, people_s_works_sdxl @ 0.4, style_filter_xu_er_thick_paint_composition_l @ 0.3, mge_monster_girls @ 0.85; dpmpp_2m/karras, 28 steps, cfg 6.0, hires fix.

```text
(4k,8k,Ultra HD), masterpiece, best quality, ultra-detailed, very aesthetic, depth of field, best lighting, detailed illustration, detailed background, cinematic, beautiful face, ambient occlusion, soft lighting, cute girl, adult woman, BREAK Aka-Oni, oni, (oni horns), colored skin, (red skin), smooth horns, black horns, straight horns, black kimono slipping off one shoulder, sitting on a wooden veranda at the far left of the image, holding a sake cup, confident smile, BREAK very wide composition, night garden with paper lanterns and a full moon, the right side of the image is dark night sky and quiet garden
```

## Deadlight — `deadlight.jpg`
Seed 22; recipe `pick-pony-15` on lane `pony` (`ponyDiffusionV6XL.safetensors`), LoRAs: incase_style_noob @ 0.5, moriimee_gothic_illust @ 0.5, envy_zoom_slider_xl_01 @ 2.0, vixon_s_anima_pony_styles_gothic_neon @ 0.2, wadustyle @ 0.25; dpmpp_2m/karras, 35 steps, cfg 5.0, hires fix.

```text
score_9_up, score_9, score_8_up, score_8, score_7_up, raw, high quality, absurdres, morimee_style, masterpiece, best quality, 1girl, adult woman, curvy, elegant black gothic gown with a deep neckline, fully clothed, ethereal empress of death, glowing scythe, green glow, crescent eye tattoo, glowing eyes, standing at the entrance to the underworld, very wide composition, the figure on the right side, dark stone archways and drifting green deadlight fog, the left half of the image is dark shadowy fog, intense low lighting
```

## Armored Allure — `armored_allure.jpg`
Seed 11; recipe `pick-amix-samurai` on lane `amix` (`aMix_illust.safetensors`), LoRAs: rimix_style_v2_illust @ 1.0; euler_ancestral/normal, 30 steps, cfg 6.0.

```text
samurai woman, sexy, black hair, medium length, straight hair, fair skin, blue eyes, large breasts, ornate traditional japanese armor, seductive pose, cowboy shot, standing at the far right edge of the image, very wide landscape composition, the left two thirds of the image is a dark empty temple interior with deep black shadow, faint red paper lanterns high in the corner, very dark and quiet, dramatic red rim lighting, masterpiece, best quality, detailed, depth of field, very aesthetic, adult, mature female
```

## Bug Knight — `bug_knight.jpg`
Seed 22; recipe `pick-krea2-39` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: cartoon_world @ 1.0; euler/simple, 7 steps, cfg 1.0, hires fix.

```text
ToonDaal, a very wide cartoon scene inside a vast glowing underground cavern, a tiny round bug knight with a little nail sword and a big white mask stands on a ledge at the far left edge, glowing blue lanterns hanging from stalactites along the top corners, the center and right of the image is a deep calm dark blue cave space with soft glowing mist, cute and moody, video game art
```

## Arcade Night — `arcade_night.jpg`
Seed 11; recipe `pick-krea2-40` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: krea2_flux_vividly_surreal @ 1.0; euler_ancestral/normal, 8 steps, cfg 1.0, hires fix.

```text
Realistic detailed comic art in the style of Frank Quitely, very wide view of a dim retro arcade at night, a row of glowing arcade cabinets along the far right edge, a young adult woman gamer in a hoodie leaning on a cabinet playing, the left two thirds of the image is a dark carpeted floor and a dark wall with soft purple and cyan glow, uncluttered, moody, no readable text on the screens
```

## Station Window — `station_window.jpg`
Seed 22; recipe `pick-krea2-31` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: grandline_legendary_stylized_illustration @ 0.65, afterveil_worn_memory_style @ 0.85; euler/normal, 8 steps, cfg 1.0, hires fix.

```text
digital painting of the inside of a dark space station observation deck, a lone astronaut silhouette standing at the far left edge looking out, an enormous curved window fills the image showing a huge ringed gas giant planet low on the right and a calm black starfield across the middle and top, very dark and quiet, cinematic, blue and amber rim light
```

## Library Cat — `library_cat.jpg`
Seed 11; recipe `pick-krea2-24` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: between_pages @ 1.0; euler_ancestral/normal, 8 steps, cfg 1.0, hires fix.

```text
PagesDaal, a cozy storybook illustration, very wide view of a warm magical library, tall bookshelves along the far left and far right edges, a ginger cat asleep on a sunny window seat at the right, floating glowing books drifting near the top corners, the middle of the image is a soft sunlit cream plaster wall with gentle dust motes, calm and empty center, warm soft pastel colors
```

## Player Two — `player_two.jpg`
Seed 11; recipe `pick-hassaku-18` on lane `hassaku` (`hassakuXL_illust_v13a.safetensors`), LoRAs: none; euler_ancestral/normal, 30 steps, cfg 5.0, hires fix.

```text
masterpiece, best quality, good quality, very aesthetic, absurdres, newest, depth of field, focused subject, in the style of ckncore, 1girl, solo, black hair, hair over one eye, long hair, black bodysuit, gaming headset, sitting sideways in a gaming chair at the far left edge of the image, holding a game controller, cables attached, many cables hanging, very wide composition, the rest of the image is a flat plain red background, simple background, empty, adult
```

## Reaper — `reaper.jpg`
Seed 11; recipe `pick-pony-15` on lane `pony` (`ponyDiffusionV6XL.safetensors`), LoRAs: incase_style_noob @ 0.5, moriimee_gothic_illust @ 0.5, envy_zoom_slider_xl_01 @ 2.0, vixon_s_anima_pony_styles_gothic_neon @ 0.2, wadustyle @ 0.25; dpmpp_2m/karras, 35 steps, cfg 5.0, hires fix.

```text
score_9_up, score_9, score_8_up, score_8, score_7_up, raw, high quality, absurdres, morimee_style, masterpiece, best quality, 1girl, adult woman, curvy, elegant black gothic gown with a deep neckline, fully clothed, ethereal empress of death, glowing scythe, green glow, crescent eye tattoo, glowing eyes, standing at the entrance to the underworld, very wide composition, the figure on the right side, dark stone archways and drifting green deadlight fog, the left half of the image is dark shadowy fog, intense low lighting
```

## Ram Field — `ram_field.jpg`
Seed 22; recipe `pick-wai-illustrious-16` on lane `wai-illustrious` (`waiIllustrious_v14.safetensors`), LoRAs: none; euler_ancestral/normal, 30 steps, cfg 7.0, hires fix.

```text
A very wide eye-level anime illustration of a lush sunlit meadow, a fluffy round bumblebee with velvet yellow and black fur and iridescent wings hovers near the far left edge, tall wildflowers and clover along the bottom corners, the middle and top of the image is a soft bright blue sky with a few round white clouds, cheerful, clean, lots of open space, vibrant colors
```

## Maple Torii — `maple_torii.jpg`
Seed 11; recipe `pick-rimix-samurai` on lane `rimix-illust` (`riMixIllustrious.safetensors`), LoRAs: detailer_tool_illust @ 0.9, callis_dystopian_sheek_illust @ 0.85, dynamic_poses_slider_illust @ 2.0, my_color_locon @ 1.0; euler_ancestral/normal, 32 steps, cfg 4.5, hires fix.

```text
1girl, adult woman, kitsune, fox ears, fluffy fox tail, shrine maiden, red and white miko outfit slipping off one shoulder, mature female, sly smile, DS-Illu, cowboy shot, standing at the far left edge of the image under a red torii gate, autumn maple leaves drifting, ink splash, glowing particles, very wide landscape composition, the right two thirds of the image is a calm dusk sky over misty mountains, quiet, masterpiece, best quality, very aesthetic, depth of field, adult
```

## Moonlit Oni — `moonlit_oni.jpg`
Seed 22; recipe `pick-hassaku-14` on lane `hassaku` (`hassakuXL_illust_v13a.safetensors`), LoRAs: noobai_xl_detailer @ 1.0, dramatic_lighting_slider_pony_illu @ -0.35, ma1ma1helmes_shiiro_s_styles_niji @ 0.45, people_s_works_sdxl @ 0.4, style_filter_xu_er_thick_paint_composition_l @ 0.3, mge_monster_girls @ 0.85; dpmpp_2m/karras, 28 steps, cfg 6.0, hires fix.

```text
(4k,8k,Ultra HD), masterpiece, best quality, ultra-detailed, very aesthetic, depth of field, best lighting, detailed illustration, detailed background, cinematic, beautiful face, ambient occlusion, soft lighting, cute girl, adult woman, BREAK Aka-Oni, oni, (oni horns), colored skin, (red skin), smooth horns, black horns, straight horns, black kimono slipping off one shoulder, sitting on a wooden veranda at the far left of the image, holding a sake cup, confident smile, BREAK very wide composition, night garden with paper lanterns and a full moon, the right side of the image is dark night sky and quiet garden
```

## Lantern Hall — `lantern_hall.jpg`
Seed 22; recipe `pick-amix-samurai` on lane `amix` (`aMix_illust.safetensors`), LoRAs: rimix_style_v2_illust @ 1.0; euler_ancestral/normal, 30 steps, cfg 6.0.

```text
samurai woman, sexy, black hair, medium length, straight hair, fair skin, blue eyes, large breasts, ornate traditional japanese armor, seductive pose, cowboy shot, standing at the far right edge of the image, very wide landscape composition, the left two thirds of the image is a dark empty temple interior with deep black shadow, faint red paper lanterns high in the corner, very dark and quiet, dramatic red rim lighting, masterpiece, best quality, detailed, depth of field, very aesthetic, adult, mature female
```

## Red Vigil — `red_vigil.jpg`
Seed 22; recipe `pick-janku-13` on lane `janku` (`janku_v5_illust.safetensors`), LoRAs: dramatic_lighting_slider_pony_illu @ 2.4, sinozick_shiiro_s_styles_niji @ 0.7, trendcraft_the_people_s_style_detailer_noob_ @ 0.4; euler_ancestral/karras, 40 steps, cfg 4.5, hires fix.

```text
lazypos, Sinozick_illu, gradient, spot color, ((masterpiece, best quality, high quality)), ((greyscale with red)), high details, epic movie scene, very wide landscape composition, honorable white warrior priestess standing on top of a cliff at the far left edge of the image, absurdly long red hair blowing in the wind, braided hair, tattered archaic armor, linen embroidered tabard, holding a long sword, solo, intimidating expression, the rest of the image is an enormous empty grey misty sky over distant grey mountains, calm, quiet negative space, only the hair is red
```

## Rain Courier — `rain_courier.jpg`
Seed 22; recipe `pick-krea2-40` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: krea2_flux_vividly_surreal @ 1.0; euler_ancestral/normal, 8 steps, cfg 1.0, hires fix.

```text
Realistic detailed cyberpunk comic art in the style of Frank Quitely, very wide panoramic image, a young adult woman courier in an oversized hoverbike helmet with an orange visor leans against a grungy metal wall at the far left edge, her hoverbike parked beside her, the rest of the image is a rainy cyberpunk street at night stretching into the distance with neon signs reflected in puddles, deep blue shadows, the right two thirds dark and uncluttered, no readable text on signs
```

## Rage Quit — `rage_quit.jpg`
Seed 22; recipe `pick-hassaku-18` on lane `hassaku` (`hassakuXL_illust_v13a.safetensors`), LoRAs: none; euler_ancestral/normal, 30 steps, cfg 5.0, hires fix.

```text
masterpiece, best quality, good quality, very aesthetic, absurdres, newest, depth of field, focused subject, in the style of ckncore, 1girl, solo, black hair, hair over one eye, long hair, black bodysuit, gaming headset, sitting sideways in a gaming chair at the far left edge of the image, holding a game controller, cables attached, many cables hanging, very wide composition, the rest of the image is a flat plain red background, simple background, empty, adult
```

## Mars Colony — `mars_colony.jpg`
Seed 11; recipe `pick-krea2-34` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: mrpopo_s_krea2_anime_art_enhanced @ 1.0; euler/normal, 8 steps, cfg 1.0, hires fix.

```text
An aerial perspective of a hopeful solarpunk colony on mars, glass greenhouse domes full of green gardens and white solar sails clustered along the far left and far right edges, red desert dunes and canyons, the whole center of the image is a wide calm salmon-pink martian sky above a smooth dune plain, anime art, painterly, wide panoramic composition, soft warm light, no text, no people
```

## Ramen Night — `ramen_night.jpg`
Seed 11; recipe `pick-krea2-33` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: geffstyle_stylemix_by_lostcut_style_krea2_lo @ 1.0; euler/simple, 8 steps, cfg 1.0, hires fix.

```text
2d, geffstyle, a deeply atmospheric and textural oil painting with visible gritty brushstrokes and a rich limited color palette, very wide view of a tiny ramen stall on a rainy night street, the glowing stall with steam and a cook at the far right edge, the rest of the image is a dark empty wet street and dark buildings with a few soft glowing windows, cozy lo-fi mood, deep navy and warm amber, the left two thirds dark and calm
```

## Frozen Shrine — `frozen_shrine.jpg`
Seed 11; recipe `pick-krea2-05` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: iiyo_sumi_ukiyo_e_sumi_e_flat_art_ @ 1.0, detailcore_forever_by_stx @ 0.8; euler/normal, 8 steps, cfg 1.0, hires fix.

```text
ukiyo-e woodblock print, flat colors, bold outlines, wide panoramic winter landscape, snow-covered pine trees and a small red torii gate at the far left edge, snowy mountain peaks along the far right edge, the center of the image is a pale grey sky with gently falling snow above a calm frozen lake, quiet and empty middle, prussian blue, white and vermilion palette, aged paper texture, no text, no calligraphy, no seal
```

## Desert Nomad — `desert_nomad.jpg`
Seed 11; recipe `pick-krea2-07` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: krea2_purpledreams @ 0.6; euler/normal, 8 steps, cfg 1.0, hires fix.

```text
ta86_inkriot, thin black outlines, art by Jean Giraud (Moebius), watercolor and ink illustration, very wide panoramic desert, a lone nomad rider on a huge long-legged beast walking at the far right edge, strange tall rock spires at the far left edge, the middle of the image is an enormous empty pale sky over a flat sand plain, calm and airy, vintage sci-fi comic art style, muted sand, peach and pale teal colors
```

## Kitsune Shrine — `kitsune_shrine.jpg`
Seed 22; recipe `pick-rimix-samurai` on lane `rimix-illust` (`riMixIllustrious.safetensors`), LoRAs: detailer_tool_illust @ 0.9, callis_dystopian_sheek_illust @ 0.85, dynamic_poses_slider_illust @ 2.0, my_color_locon @ 1.0; euler_ancestral/normal, 32 steps, cfg 4.5, hires fix.

```text
1girl, adult woman, kitsune, fox ears, fluffy fox tail, shrine maiden, red and white miko outfit slipping off one shoulder, mature female, sly smile, DS-Illu, cowboy shot, standing at the far left edge of the image under a red torii gate, autumn maple leaves drifting, ink splash, glowing particles, very wide landscape composition, the right two thirds of the image is a calm dusk sky over misty mountains, quiet, masterpiece, best quality, very aesthetic, depth of field, adult
```

## Shield Maiden — `shield_maiden.jpg`
Seed 22; recipe `pick-wai-illustrious-28` on lane `wai-illustrious` (`waiIllustrious_v14.safetensors`), LoRAs: smoothdetailer_illust @ 0.4, smooth_style @ 0.8, fantasy_forge @ 0.7; euler/normal, 25 steps, cfg 4.0, hires fix.

```text
masterpiece, best quality, newest, absurdres, highres, ultra detailed, sharp focus, depth of field, (cel shading:1.3), addmicrodetails, 1girl, solo, adult woman, mature female, viking shield maiden warrior, long braided blonde hair, ornate bronze breastplate with cleavage, fur cloak, bare midriff, battle skirt, round shield and axe, confident smirk, standing on a rocky ledge at the far left of the image, very wide composition, the right two thirds of the image is a stormy fjord at dusk with dark sea and low clouds, dramatic rim light
```

## Night Nurse — `night_nurse.jpg`
Seed 11; recipe `pick-wai-illustrious-17` on lane `wai-illustrious` (`waiIllustrious_v14.safetensors`), LoRAs: dramatic_lighting_slider_pony_illustrious @ 4.0, neurocore_anime_shadow_circuit_by_chronoknig @ 0.4, ai @ 0.15, detailer_il @ 0.4; euler/normal, 29 steps, cfg 4.0, hires fix.

```text
HDR, 8K, masterpiece, best quality, amazing quality, very aesthetic, (flat color:1.75), (haiz_ai:1), (lineart:1.5), (no outline:1), (Flat vector:1.1), 1girl, adult woman, mature female, cyberpunk nurse in a tight white nurse uniform with short skirt, white stockings, nurse cap, holding a glowing syringe, playful wink, leaning against a wall at the far right of the image, very wide composition, the left two thirds of the image is a dim empty futuristic hospital corridor with teal neon strip lights, clean flat shapes
```

## Pirate Captain — `pirate_captain.jpg`
Seed 22; recipe `pick-krea2-nsfw-20` on lane `krea2-nsfw` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: iiyo_sumi_ukiyo_e_sumi_e_flat_art_pop_art_3d @ 1.0; euler_ancestral/normal, 11 steps, cfg 1.0, hires fix.

```text
nsfw; Anime screenshot, 2D cel-shaded illustration with painterly detail, drawn animation still, modern painterly anime, movie-quality animation, atmospheric, cinematic composition, a confident adult woman pirate captain, tricorn hat, open red coat, corset with deep neckline, tall boots, hand on a cutlass, standing at the ship's wheel at the far left of the image, very wide composition, the rest of the image is a moonlit night sea with a calm dark sky and distant ship lanterns
```

## Grid Racer — `grid_racer.jpg`
Seed 11; recipe `pick-rimix-samurai` on lane `rimix-illust` (`riMixIllustrious.safetensors`), LoRAs: detailer_tool_illust @ 0.9, callis_dystopian_sheek_illust @ 0.85, dynamic_poses_slider_illust @ 2.0, my_color_locon @ 1.0; euler_ancestral/normal, 32 steps, cfg 4.5, hires fix.

```text
1girl, sci-fi aesthetic, cyberpunk, adult woman, mature female, beautiful motorbike racer, tight black and red leather racing suit unzipped to the chest, helmet under her arm, long ponytail, DS-Illu, cowboy shot, leaning on a futuristic motorcycle at the far left of the image, confident look, glowing particles, very wide landscape composition, the right two thirds of the image is an empty dark neon race track at night fading into dark mist, masterpiece, best quality, very aesthetic, depth of field, adult
```

## Bounty Hunter — `bounty_hunter.jpg`
Seed 11; recipe `pick-hassaku-18` on lane `hassaku` (`hassakuXL_illust_v13a.safetensors`), LoRAs: none; euler_ancestral/normal, 30 steps, cfg 5.0, hires fix.

```text
masterpiece, best quality, good quality, very aesthetic, absurdres, newest, depth of field, focused subject, in the style of ckncore, 1girl, solo, adult woman, space bounty hunter, short silver hair, tight black bodysuit with armor plates, utility belt, holding a blaster, cables attached, leaning against a spaceship hull at the far right of the image, very wide composition, the rest of the image is a flat deep blue background with a few faint stars, simple background, adult
```

## Velvet Boudoir — `velvet_boudoir.jpg`
Seed 11; recipe `pick-wai-illustrious-28` on lane `wai-illustrious` (`waiIllustrious_v14.safetensors`), LoRAs: smoothdetailer_illust @ 0.4, smooth_style @ 0.8, fantasy_forge @ 0.7; euler/normal, 25 steps, cfg 4.0, hires fix.

```text
masterpiece, best quality, newest, absurdres, highres, ultra detailed, sharp focus, depth of field, (cel shading:1.3), addmicrodetails, 1girl, solo, adult woman, mature female, long black hair, sheer black lace negligee, stockings, reclining on a red velvet chaise longue at the far left of the image, seductive smile, looking at viewer, very wide composition, the right two thirds of the image is a dark candlelit boudoir with deep shadow and heavy red curtains, dim warm light, quiet and dark
```

## Amber Sorceress — `amber_sorceress.jpg`
Seed 11; one-off lane: `krea2` pipeline with checkpoint `JANK2AnimeKrea2Turbo_v10.safetensors`, no LoRAs; euler/simple, 8 steps, cfg 1.0.

```text
anime illustration, a beautiful adult sorceress with long silver hair and amber eyes, elegant dark robes with a plunging neckline and gold embroidery, casting a swirl of amber magic from her hand, standing at the far right of the image, very wide landscape composition, the left two thirds of the image is a dark ancient library hall fading into deep shadow with floating amber embers, calm and dark, cinematic lighting
```

## Neon Idol — `neon_idol.jpg`
Seed 11; one-off lane: `krea2` pipeline with checkpoint `JANK2AnimeKrea2Turbo_v10.safetensors`, no LoRAs; euler/simple, 8 steps, cfg 1.0.

```text
anime illustration, a confident adult cyberpunk pop idol with pink twin tails, cropped holographic jacket, short skirt, thigh-high boots, microphone in hand, winking, standing on a stage at the far left of the image, very wide landscape composition, the right two thirds of the image is a dark empty concert hall with faint magenta and cyan spotlights in haze, calm and dark, cinematic lighting
```

# Widget skins — `assets/skins/`

Objects rendered alone on plain white, then cut out (BiRefNet background removal, or a
luminance key for ink on paper) and cropped to the object. See docs/widget-styles.md.

## `katana.png`
Seed 11; recipe `tab-krea2-19` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: none; euler/simple, 8 steps, cfg 1.0; BiRefNet cutout.

```text
a single japanese katana sword lying perfectly horizontal across the whole image, hilt on the left and blade tip on the right, straight side view, black silk-wrapped handle with a small round black iron tsuba guard, long polished silver steel blade with a wavy hamon temper line, product photograph, isolated on a plain pure white background, even studio lighting, sharp, entire sword visible, no hands, no text, no stand
```

## `longsword_red.png`
Seed 11; recipe `tab-krea2-19` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: none; euler/simple, 8 steps, cfg 1.0; BiRefNet cutout.

```text
a single long straight double-edged sword lying perfectly horizontal across the whole image, hilt on the left and blade tip on the right, straight side view, worn leather-wrapped grip, dark iron crossguard and round pommel, long dark steel blade with a thin red glowing edge, fantasy weapon, product photograph, isolated on a plain pure white background, even studio lighting, sharp, entire sword visible, no hands, no text
```

## `tsuba.png`
Seed 22; recipe `tab-krea2-19` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: none; euler/simple, 8 steps, cfg 1.0; BiRefNet cutout.

```text
a single round japanese katana sword guard tsuba seen perfectly flat from the front, centered, filling the frame, black iron with delicate silver inlay of waves and a small crescent moon, ornate pierced openwork around the rim, empty plain dark center, product photograph, isolated on a plain pure white background, even studio lighting, sharp, no text, no hands
```

## `brush_stroke.png`
Seed 11; recipe `tab-krea2-19` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: none; euler/simple, 8 steps, cfg 1.0; luminance key.

```text
a single long horizontal stroke of black sumi ink made with a wide calligraphy brush, going straight from the left edge to the right edge, dry-brush texture with bristle streaks at the right end, on plain white paper, isolated on a plain pure white background, even studio lighting, sharp, no text, no hands
```

## `hearts.png`
Seed 11; recipe `tab-krea2-19` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: none; euler/simple, 8 steps, cfg 1.0; BiRefNet cutout.

```text
a straight horizontal row of five identical glossy red cartoon hearts evenly spaced from the left edge to the right edge, retro video game health bar icons, bold black outline, flat colors, isolated on a plain pure white background, even studio lighting, sharp, no text, no hands
```

## `lanterns.png`
Seed 11; recipe `tab-krea2-19` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: none; euler/simple, 8 steps, cfg 1.0; BiRefNet cutout.

```text
a straight horizontal string of six small round red japanese paper lanterns hanging evenly spaced from a thin black cord running from the left edge to the right edge, isolated on a plain pure white background, even studio lighting, sharp, no text, no hands
```

## `battery.png`
Seed 11; recipe `tab-krea2-19` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: none; euler/simple, 8 steps, cfg 1.0; BiRefNet cutout.

```text
a long horizontal sci-fi energy cell battery bar made of eight glowing orange rectangular segments inside a dark gunmetal casing, side view, from the left edge to the right edge, isolated on a plain pure white background, even studio lighting, sharp, no text, no hands
```

## `cockpit.png`
Seed 11; recipe `tab-krea2-19` on lane `krea2` (`krea2_turbo_fp8_scaled.safetensors`), LoRAs: none; euler/simple, 8 steps, cfg 1.0; BiRefNet cutout.

```text
a single round vintage aircraft cockpit instrument dial seen perfectly flat from the front, centered, filling the frame, cream face with a worn brass bezel and screws, completely blank face with no numbers and no needle, ink and watercolor illustration in the style of Moebius, isolated on a plain pure white background, even studio lighting, sharp, no text, no hands
```
