pluginManagement {
    repositories {
        mavenCentral()
        gradlePluginPortal()
        google()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
        google()
    }
}
rootProject.name = "homelab-command-centre"
include(":core")
// The Android application module needs the Android SDK + Google Maven (AGP/AndroidX). It is
// included only when the SDK is available, so `:core` can be built and tested anywhere with a JDK.
val sdkAvailable = System.getenv("ANDROID_HOME") != null || System.getenv("ANDROID_SDK_ROOT") != null ||
    file("local.properties").let { it.exists() && it.readText().contains("sdk.dir") }
if (sdkAvailable || System.getProperty("homelab.includeApp") == "true") {
    include(":app")
}
