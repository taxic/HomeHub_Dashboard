package com.homelab.commandcentre.core.domain

import java.time.Duration
import java.time.Instant
import java.util.Locale

/** `null` always renders as "—" (unavailable), never as zero. */
object Format {
    const val NA = "—"

    fun bytes(n: Long?, digits: Int = 1): String {
        if (n == null) return NA
        val units = listOf("B", "KB", "MB", "GB", "TB", "PB")
        var v = n.toDouble(); var i = 0
        while (v >= 1024 && i < units.lastIndex) { v /= 1024; i++ }
        return if (i == 0) "${n} B" else String.format(Locale.US, "%.${digits}f %s", v, units[i])
    }

    fun rate(bps: Double?): String = if (bps == null) NA else bytes(bps.toLong()) + "/s"
    fun percent(p: Double?, digits: Int = 0): String = if (p == null) NA else String.format(Locale.US, "%.${digits}f%%", p)
    fun temp(c: Double?): String = if (c == null) NA else String.format(Locale.US, "%.0f°C", c)

    fun duration(seconds: Double?): String {
        if (seconds == null) return NA
        val s = seconds.toLong(); val d = s / 86400; val h = s % 86400 / 3600; val m = s % 3600 / 60
        return when { d > 0 -> "${d}d ${h}h"; h > 0 -> "${h}h ${m}m"; else -> "${m}m" }
    }

    fun ago(iso: String?, now: Instant = Instant.now()): String {
        if (iso == null) return "never"
        val t = runCatching { Instant.parse(iso) }.getOrNull() ?: return NA
        val s = Duration.between(t, now).seconds.coerceAtLeast(0)
        return when {
            s < 5 -> "just now"; s < 60 -> "${s}s ago"; s < 3600 -> "${s / 60}m ago"
            s < 86400 -> "${s / 3600}h ago"; else -> "${s / 86400}d ago"
        }
    }

    enum class Level { Ok, Warn, Crit, Unknown }

    fun level(pct: Double?, warn: Double = 85.0, crit: Double = 95.0): Level = when {
        pct == null -> Level.Unknown; pct >= crit -> Level.Crit; pct >= warn -> Level.Warn; else -> Level.Ok
    }
}
