# Android app

> **Not compiled by the author.** `android/core` (all networking/auth/state logic) has 40 passing JVM
> tests. `android/app` (Compose screens, ViewModels, Keystore store, WorkManager worker) was written
> without an Android SDK; expect to fix small compile errors on first build, and run
> `./gradlew :app:connectedDebugAndroidTest` yourself.

## Build
1. Install Android Studio (Ladybug or newer) with SDK 35. Open the `android/` folder.
2. Let Gradle sync. Library versions are in `gradle/libs.versions.toml` (mid-2025 releases, chosen as
   mutually compatible; bump if Studio suggests).
3. Debug APK: `./gradlew :app:assembleDebug` → `app/build/outputs/apk/debug/app-debug.apk`.
4. Release APK: create a keystore **outside the repo**, then `android/keystore.properties`
   (git-ignored): `storeFile=../../keys/homelab.jks`, `storePassword=…`, `keyAlias=…`, `keyPassword=…`;
   `./gradlew :app:assembleRelease`.
5. Install: `adb install -r app-debug.apk`, or copy the APK to the phone and allow "install unknown apps".

Without an SDK you can still run the logic tests: `./gradlew :core:test` (JDK 17+; the `:app` module is
included automatically only when `ANDROID_HOME`/`local.properties` is present).

## Connecting over Tailscale
1. Install Tailscale on the phone and join the same tailnet as the server.
2. In the app's first screen enter the server address: `http://100.x.y.z:8741` (from
   `tailscale ip -4`) or `http://<hostname>.<tailnet>.ts.net:8741`, or the `https://…ts.net/` address if
   you use `tailscale serve`. **Never `localhost`** — on the phone that is the phone.
3. The app checks `/api/v1/health` before saving, then shows setup (first run) or sign-in.
4. Notifications: Settings → "Notify me of critical alerts" (Android 13+ asks for permission). This is a
   best-effort 15-minute background check; for immediate delivery use Telegram on the server.

## Architecture
`:core` (JVM) — `api/` (models validated against real backend JSON, Retrofit), `auth/` (SessionManager:
single-flight refresh, rotation, offline-safe), `data/` (repository, `Loadable` + `pollingFlow` giving
explicit *stale/disconnected* state), `domain/` (container policy & action state machine, URL policy,
formatting). `:app` — Compose UI + thin ViewModels (`viewmodel/`), `SecureTokenStore` (Keystore),
`AlertWorker` (WorkManager), manual DI (`AppContainer`). Room is intentionally **not** used: cached
metrics could mislead, so nothing is persisted except the server address, theme and the encrypted
refresh token.
