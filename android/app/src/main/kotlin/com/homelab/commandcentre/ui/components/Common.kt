package com.homelab.commandcentre.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.border
import androidx.compose.foundation.background
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.homelab.commandcentre.core.data.ApiFailure
import com.homelab.commandcentre.core.data.Loadable
import com.homelab.commandcentre.core.domain.Format
import com.homelab.commandcentre.ui.theme.LocalStatusColors
import java.time.Instant

@Composable
fun levelColor(level: Format.Level): Color = LocalStatusColors.current.let {
    when (level) { Format.Level.Ok -> it.ok; Format.Level.Warn -> it.warn; Format.Level.Crit -> it.crit; Format.Level.Unknown -> it.unknown }
}

private fun levelIcon(level: Format.Level): ImageVector = when (level) {
    Format.Level.Ok -> Icons.Outlined.CheckCircle
    Format.Level.Warn -> Icons.Outlined.Warning
    Format.Level.Crit -> Icons.Outlined.ErrorOutline
    Format.Level.Unknown -> Icons.Outlined.HelpOutline
}

/** Status is always icon + text label; colour is reinforcement only. */
@Composable
fun StatusChip(level: Format.Level, label: String, modifier: Modifier = Modifier) {
    val color = levelColor(level)
    Row(
        modifier
            .border(1.dp, color.copy(alpha = 0.4f), RoundedCornerShape(50))
            .background(color.copy(alpha = 0.12f), RoundedCornerShape(50))
            .padding(horizontal = 10.dp, vertical = 3.dp)
            .semantics { contentDescription = "Status: $label" },
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Icon(levelIcon(level), contentDescription = null, tint = color, modifier = Modifier.size(14.dp))
        Text(label, color = color, style = MaterialTheme.typography.labelMedium)
    }
}

fun serviceLevel(status: String) = when (status) {
    "healthy" -> Format.Level.Ok to "Healthy"
    "degraded" -> Format.Level.Warn to "Degraded"
    "unhealthy" -> Format.Level.Crit to "Unhealthy"
    "disabled" -> Format.Level.Unknown to "Disabled"
    else -> Format.Level.Unknown to "Unknown"
}

@Composable
fun SectionCard(title: String? = null, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (title != null) Text(title.uppercase(), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            content()
        }
    }
}

/** Big-number tile. [value] == null renders "—" and a muted note: unavailable, not zero. */
@Composable
fun MetricTile(title: String, value: String?, unit: String = "", percent: Double? = null, sub: String? = null, modifier: Modifier = Modifier) {
    SectionCard(title, modifier) {
        Text(
            if (value == null) Format.NA else value + unit,
            style = MaterialTheme.typography.headlineMedium,
            color = if (value == null) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface,
        )
        if (percent != null) UsageBar(percent, "$title usage")
        Text(sub ?: if (value == null) "Unavailable" else "", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
fun UsageBar(percent: Double, description: String, level: Format.Level = Format.level(percent)) {
    LinearProgressIndicator(
        progress = { (percent / 100.0).toFloat().coerceIn(0f, 1f) },
        modifier = Modifier.fillMaxWidth().height(8.dp).semantics { contentDescription = "$description ${percent.toInt()} percent" },
        color = levelColor(level),
        trackColor = MaterialTheme.colorScheme.surfaceVariant,
        strokeCap = StrokeCap.Round,
    )
}

@Composable
fun CenteredMessage(title: String, body: String? = null, action: (@Composable () -> Unit)? = null) {
    Column(Modifier.fillMaxWidth().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium)
        if (body != null) Text(body, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
        action?.invoke()
    }
}

/** Distinct presentations for offline / permission-denied / other failures. */
@Composable
fun FailureView(failure: ApiFailure, onRetry: (() -> Unit)? = null) {
    val (title, body) = when (failure) {
        is ApiFailure.Offline -> "Backend unreachable" to "Check your connection and that Tailscale is connected, then try again."
        is ApiFailure.Forbidden -> "Permission denied" to failure.message
        is ApiFailure.Unauthorized -> "Signed out" to failure.message
        is ApiFailure.Unavailable -> "Service unavailable" to failure.message
        else -> "Something went wrong" to failure.message
    }
    CenteredMessage(title, body) { if (onRetry != null) Button(onClick = onRetry) { Text("Try again") } }
}

/** Shown above stale content so cached numbers are never mistaken for live ones. */
@Composable
fun DisconnectedBanner(updatedAt: Instant) {
    val c = LocalStatusColors.current.crit
    Row(
        Modifier.fillMaxWidth().background(c.copy(alpha = 0.14f), RoundedCornerShape(10.dp)).border(1.dp, c, RoundedCornerShape(10.dp)).padding(12.dp)
            .semantics { contentDescription = "Disconnected from the backend. Data is stale." },
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(Icons.Outlined.CloudOff, null, tint = c)
        Column {
            Text("Disconnected from the backend", color = c, style = MaterialTheme.typography.titleSmall)
            Text("Showing data from ${Format.ago(updatedAt.toString())}. Retrying automatically.", style = MaterialTheme.typography.bodySmall)
        }
    }
}

/** Renders a [Loadable] with the loading / error / disconnected conventions used everywhere. */
@Composable
fun <T> LoadableContent(state: Loadable<T>, onRetry: () -> Unit, content: @Composable (T) -> Unit) {
    when (state) {
        Loadable.Loading -> Box(Modifier.fillMaxWidth().padding(48.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        is Loadable.Failed -> FailureView(state.failure, onRetry)
        is Loadable.Content -> Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            val err = state.refreshError
            if (err is ApiFailure.Offline) DisconnectedBanner(state.updatedAt)
            else if (err != null) Text("Could not refresh: ${err.message}", color = LocalStatusColors.current.warn, style = MaterialTheme.typography.bodySmall)
            content(state.data)
        }
    }
}

@Composable
fun ConfirmDialog(title: String, body: String, confirmLabel: String, destructive: Boolean, running: Boolean, result: String?, error: String?, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = { if (!running) onDismiss() },
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                when {
                    result != null -> Text(result)
                    error != null -> Text(error, color = LocalStatusColors.current.crit)
                    else -> Text(body)
                }
                if (running) Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    Text("Working…")
                }
            }
        },
        confirmButton = {
            if (result != null || error != null) TextButton(onClick = onDismiss) { Text("Close") }
            else TextButton(onClick = onConfirm, enabled = !running) {
                Text(confirmLabel, color = if (destructive) LocalStatusColors.current.crit else MaterialTheme.colorScheme.primary)
            }
        },
        dismissButton = { if (result == null && error == null) TextButton(onClick = onDismiss, enabled = !running) { Text("Cancel") } },
    )
}

data class ChartSeries(val label: String, val color: Color, val values: List<Double?>)

/** Minimal line chart: null values break the line (gap), so unavailable != zero. */
@Composable
fun LineChart(title: String, series: List<ChartSeries>, modifier: Modifier = Modifier, maxFixed: Double? = null, format: (Double) -> String) {
    val all = series.flatMap { it.values }.filterNotNull()
    SectionCard(title, modifier) {
        if (all.isEmpty()) {
            Text("No data in this range (metric unavailable or not collected yet).", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
            return@SectionCard
        }
        val top = maxFixed ?: (all.max().coerceAtLeast(1e-9) * 1.1)
        val grid = MaterialTheme.colorScheme.outline
        Text("0 – ${format(top)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Canvas(
            Modifier.fillMaxWidth().height(140.dp)
                .semantics { contentDescription = "$title chart. Latest ${series.joinToString { s -> s.label + " " + (s.values.lastOrNull { it != null }?.let(format) ?: "unavailable") }}" },
        ) {
            for (i in 0..4) drawLine(grid, androidx.compose.ui.geometry.Offset(0f, size.height * i / 4), androidx.compose.ui.geometry.Offset(size.width, size.height * i / 4), 1f)
            series.forEach { s ->
                val n = s.values.size
                if (n < 2) return@forEach
                var path = Path(); var drawing = false
                s.values.forEachIndexed { i, v ->
                    if (v == null) { if (drawing) { drawPath(path, s.color, style = Stroke(4f, cap = StrokeCap.Round)); path = Path(); drawing = false }; return@forEachIndexed }
                    val x = size.width * i / (n - 1)
                    val y = size.height * (1f - (v / top).toFloat().coerceIn(0f, 1f))
                    if (!drawing) { path.moveTo(x, y); drawing = true } else path.lineTo(x, y)
                }
                if (drawing) drawPath(path, s.color, style = Stroke(4f, cap = StrokeCap.Round))
            }
        }
        if (series.size > 1) Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            series.forEach { s ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Box(Modifier.size(width = 12.dp, height = 3.dp).background(s.color, RoundedCornerShape(2.dp)))
                    Text(s.label, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
    }
}

@Composable
fun LocalStatusColorsWarning(text: String) {
    val c = LocalStatusColors.current.warn
    Row(
        Modifier.fillMaxWidth().background(c.copy(alpha = 0.12f), RoundedCornerShape(10.dp)).border(1.dp, c.copy(alpha = 0.5f), RoundedCornerShape(10.dp)).padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(Icons.Outlined.Warning, null, tint = c)
        Text(text, style = MaterialTheme.typography.bodySmall)
    }
}
