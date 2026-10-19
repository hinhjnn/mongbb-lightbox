# MongBB Lightbox

Published static build: https://hinhjnn.github.io/mongbb-lightbox/

156-city / 64×64 editor: https://hinhjnn.github.io/mongbb-lightbox/#city-map

Arduino sketch, all city coordinates, and USB/wiring guide are in `downloads/` and linked from the website. The downloadable ZIP contains the editable sketch and headers. Source geometry and optical assumptions are described in the app. RGB USB control does not control CCT strips.

Validated with browser emulation and pinned Arduino framework compilation. Actual ESP32-WROOM-32 / HUB75E driver IC, wiring, power and LED output are not physically verified. Read the guide before connecting.

GitHub Pages publishes branch `codex/pages`. No API keys, account login, remote assets or analytics are needed at runtime.

The city editor includes three region color controls: background (yellow), unselected land/cities (orange), and selected cities (brown). Change a color or load the city template to apply it to both previews. Send the current scene over USB, or enable live sync; save to ESP32 to retain it on the device. City checkboxes choose the selected color, including city points outside the original land artwork. Black disables a region's pixels. Existing per-city and map brightness controls still apply; brown is represented as a darker orange RGB color.

The first activation of region colors limits the current overall brightness to at most 10%; later city and color changes retain the chosen brightness. This is a relative brightness setting, not a current limit. Disable “使用三區配色” to use individual city colors. City JSON v2 stores the palette and selection; v1 files retain their original individual colors. General settings JSON keeps its v2 schema with optional `cityMap` editor metadata, so current exports restore the city controls too. Older general settings files still restore their source pixels. `Cities.h` cannot represent region backgrounds; use USB and “儲存到 ESP32” for the complete scene.

This checkout contains the published build rather than the original build project. Region logic and controls are maintained in `assets/city-regions.mjs`, with styling in `assets/city-regions.css`; the app bundle connects them to the existing React state, exports and USB transport. No firmware changes are required.

Browser integration tests use Python Playwright with Chromium. Install Playwright if needed and set `CHROMIUM_PATH` if Chromium is not at `/usr/bin/chromium`, then run:

```sh
python -m unittest discover -s tests -v
```

The tests serve the static checkout temporarily and use a mock serial peer; they verify actual app previews, outgoing rows, brightness retention, live sync, JSON round trips, legacy city files and rejected malformed palettes. They do not verify physical panel output.
