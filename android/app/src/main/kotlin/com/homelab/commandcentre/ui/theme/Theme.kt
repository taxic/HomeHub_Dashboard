package com.homelab.commandcentre.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/** Same palette roles as the web tokens (docs/DESIGN.md), adapted to Material 3. */
private val DarkScheme = darkColorScheme(
    primary = Color(0xFF5B9DFF), onPrimary = Color(0xFF0B1220),
    background = Color(0xFF0E1116), onBackground = Color(0xFFE8EBEF),
    surface = Color(0xFF151A21), onSurface = Color(0xFFE8EBEF),
    surfaceVariant = Color(0xFF1B222B), onSurfaceVariant = Color(0xFFAAB2BD),
    outline = Color(0xFF2A323D), error = Color(0xFFF06B6B),
)
private val LightScheme = lightColorScheme(
    primary = Color(0xFF1F6FE0), onPrimary = Color(0xFFFFFFFF),
    background = Color(0xFFF4F6F9), onBackground = Color(0xFF121820),
    surface = Color(0xFFFFFFFF), onSurface = Color(0xFF121820),
    surfaceVariant = Color(0xFFF0F3F7), onSurfaceVariant = Color(0xFF4A5563),
    outline = Color(0xFFD9DEE6), error = Color(0xFFC22E2E),
)

@Immutable
data class StatusColors(val ok: Color, val warn: Color, val crit: Color, val unknown: Color, val series1: Color, val series2: Color, val series3: Color)

private val DarkStatus = StatusColors(Color(0xFF3FB97A), Color(0xFFE8A23A), Color(0xFFF06B6B), Color(0xFF8B95A3), Color(0xFF3987E5), Color(0xFFD95926), Color(0xFF199E70))
private val LightStatus = StatusColors(Color(0xFF0F7A45), Color(0xFF8F5A00), Color(0xFFC22E2E), Color(0xFF5C6672), Color(0xFF2A78D6), Color(0xFFEB6834), Color(0xFF1BAF7A))

val LocalStatusColors = staticCompositionLocalOf { DarkStatus }

/** [mode]: "dark" (default, like the web app), "light", or "system". */
@Composable
fun HomeLabTheme(mode: String = "dark", content: @Composable () -> Unit) {
    val useDark = when (mode) { "light" -> false; "system" -> isSystemInDarkTheme(); else -> true }
    androidx.compose.runtime.CompositionLocalProvider(LocalStatusColors provides if (useDark) DarkStatus else LightStatus) {
        MaterialTheme(colorScheme = if (useDark) DarkScheme else LightScheme, content = content)
    }
}
