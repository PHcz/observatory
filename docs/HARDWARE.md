# Hardware

Everything you need to build your own Observatory: a Raspberry Pi brain, an
outdoor weather node, and (optionally) a cosmic-ray muon detector. Prices are
approximate, verified against UK suppliers in May 2026, and will drift — treat
them as ranges, not quotes.

## Bill of materials

| Item | Supplier | Approx price | Notes |
|---|---|---|---|
| Raspberry Pi 4 + heatsink + USB-C PSU + 32GB microSD | [The Pi Hut](https://thepihut.com/) / [Pimoroni](https://shop.pimoroni.com/) | £0 (assumed already owned; ~£35–60 if buying) | The brain. 32GB is plenty — Pi OS Lite is ~3GB, code+deps 1–2GB, the SQLite DB grows ~5–10GB/year worst case. A decent A1/A2 card lasts 2–4 years under this light write workload. |
| Small USB stick (~5GB) | any | ~£5 (often already owned) | Rolling weekly SQLite backup target. |
| Pimoroni Enviro Weather (Pico W Aboard) | [The Pi Hut](https://thepihut.com/products/enviro-weather-pico-w-aboard-board-only) | ~£30 | Off-the-shelf outdoor node: Pico W (wifi), BME280 (temp/humidity/pressure), LTR-559 (light), JST battery connector, onboard RTC for deep sleep, Qw/ST expansion port. No soldering. |
| 2× AA battery holder with switch + JST-PH connector | [The Pi Hut](https://thepihut.com/collections/battery-holders) | ~£1.80 | JST-PH connector (not JST-XH/ZH). Powers the Enviro Weather. |
| 4× AA NiMH rechargeable batteries + charger | Amazon | ~£15 | Eneloop or similar. ~8–14 months between charges at the default 5-min read / 25-min publish cycle. |
| TFA 98.1114 protective sensor shelter (Stevenson screen) | [Weather Spares](https://weatherspares.co.uk/products/tfa-protective-sensor-shelter-stevenson-screen-98-1114) | ~£20 | White louvred plastic, generous internal space (Enviro Weather + AA pack fit), cable opening at bottom, mounting brackets included. |
| UKRAA PicoMuon detector | [UKRAA store](https://ukraa.com/store/categories/cosmic-rays) | ~£360 | Plug-and-play cosmic-ray muon detector. Two scintillators (17mm separation), onboard BMP280 (temp + pressure for flux correction), software pre-installed, USB output. Inc. UK P&P, no VAT; ships with a micro-USB cable. Optional but it's the headline science feed. |

Supplier contact for the PicoMuon: `picomuon@ukraa.com` (UKRAA's public sales address).

## Alternatives

### Stevenson screen

The TFA 98.1114 (~£20) is the recommended buy, but you have cheaper and pricier options:

| Option | Cost | Notes |
|---|---|---|
| 3D print | ~£10 filament | [MakerMeik radiation-shield design](https://www.printables.com/model/109971-radiation-shield-stevenson-screen-temperature-sens) is solid. Use PETG or ASA — PLA degrades in UV after 1–2 years. Only worth it if you already own a printer. |
| Plant-pot saucer stack | ~£5 | 6–8 white plastic saucers from a DIY store with a central bolt and washers as spacers. Cheap and cheerful. |
| MetSpec MET01 | £80–150+ | [Weather Shop UK](https://www.weathershop.co.uk/metspec-met01screen-traditionaloutdoor). Met Office spec, powder-coated aluminium. Overkill for a hobby build. |

### Batteries

The Enviro Weather accepts 2–5.5V, so several chemistries work. AA NiMH is recommended
over Pimoroni's default AAA because:

- **2–3× longer life**: ~2000mAh AA NiMH vs ~800mAh AAA NiMH.
- **Better antenna positioning**: the AAA holder mounts behind the board against the
  Pico W's wifi antenna; the AA holder sits beside the board, leaving the antenna clear.
- **Wider availability** for emergency swaps, and the TFA screen has room for the pack.

Other options: 2× AA alkaline (3V, ~12–20 months, single-use); 2× AAA NiMH (2.4V,
~3–6 months, smallest fit); 2× AAA alkaline (3V, ~4–8 months); a single-cell LiPo
(works, but needs a separate LiPo Amigo charger). Battery life depends heavily on
upload frequency — deep-sleep current is just 20µA.

### Muon detector

The PicoMuon is the easy, plug-and-play path. A DIY scintillator build
([CosmicWatch](http://www.cosmicwatch.lns.mit.edu/)) is far cheaper in parts but a
much bigger project. For Phase 1, the PicoMuon's onboard BMP280 gives
pressure-corrected flux from a single USB device with no extra wiring.

## Rough cost & effort

Two honest brackets (the muon detector dominates the full-kit total):

- **Core weather + dashboard build: ~£70–100.** Pi 4 assumed already owned; Enviro
  Weather (~£30) + Stevenson screen (~£20) + batteries & charger (~£15) + sundries.
  Add ~£35–60 if you need to buy a Pi.
- **Full build incl. muon detector: ~£450–480.** The ~£360 PicoMuon is the bulk of it.

Effort: roughly **6–8 weekends** end-to-end — Pi setup, weather-node provisioning, muon
setup, external API pollers, and the SvelteKit dashboard. None of it requires soldering.
