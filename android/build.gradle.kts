// Root build: plugin versions live in gradle/libs.versions.toml; modules apply what they need.
plugins {
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.serialization) apply false
}
