# Shared design specification

One visual language, adapted per platform (web: CSS variables in `web/src/styles/tokens.css`; Android:
Material 3 colour schemes in `ui/theme/Theme.kt`).

* **Theme:** dark by default, light supported (web: Settings → Dashboard; Android: Settings → Appearance).
* **Surfaces:** background → card (rounded 14 px, 1 px subtle border) → raised; restrained accent blue.
* **Status colours** (green ok / amber warning / red critical / grey unknown) are *reinforcement only*:
  every status carries an icon **and** a text label and an accessible description. Light-mode status
  colours are darkened to keep ≥4.5:1 text contrast on their tinted backgrounds.
* **Data semantics:** unavailable → "—" + reason; zero is shown as zero; stale data is always labelled
  with a "Disconnected" banner and its timestamp; Docker-unavailable shows no container rows.
* **Charts:** categorical slots 1–3 only (blue `#3987e5`, orange `#d95926`, aqua `#199e70` in dark;
  `#2a78d6 / #eb6834 / #1baf7a` in light), ≤2 series per chart with a legend, 2 px lines, recessive grid,
  null = gap, a **Table** view on web for exact values, content descriptions on Android.
* **Navigation:** web sidebar ≥900 px, bottom tab bar (+ "More") below; Android bottom bar
  Home / Services / Metrics / Alerts / Settings, with Containers, Storage and Backups reached from Home.
* **States:** every list/page has loading, empty, error (offline vs permission-denied vs other) and
  pull-to-refresh (Android) / refresh buttons (web).
