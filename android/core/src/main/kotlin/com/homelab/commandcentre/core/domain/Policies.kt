package com.homelab.commandcentre.core.domain

import com.homelab.commandcentre.core.api.ContainerOut
import com.homelab.commandcentre.core.data.ContainerAction
import java.net.URI

/** Which buttons to offer. Mirrors the web UI; the server remains the authority and re-checks. */
object ContainerPolicy {
    fun available(c: ContainerOut): List<ContainerAction> {
        if (!c.canControl || c.protected) return emptyList()
        return ContainerAction.entries.filter { a ->
            a.wire in c.allowedActions && (if (a == ContainerAction.Start) c.state != "running" else c.state == "running")
        }
    }

    fun readOnlyReason(c: ContainerOut): String? = when {
        c.protected -> "Protected container"
        !c.canControl -> "Read-only"
        else -> null
    }
}

sealed interface UrlCheck {
    data class Valid(val normalized: String, val warning: String? = null) : UrlCheck
    data class Invalid(val reason: String) : UrlCheck
}

/** Validates the server address a user types on the connection screen. */
object UrlPolicy {
    fun check(input: String): UrlCheck {
        val raw = input.trim()
        if (raw.isEmpty()) return UrlCheck.Invalid("Enter the server address")
        val uri = try { URI(raw) } catch (e: Exception) { return UrlCheck.Invalid("That is not a valid URL") }
        if (uri.scheme !in listOf("http", "https")) return UrlCheck.Invalid("Start with http:// or https://")
        val host = uri.host?.lowercase() ?: return UrlCheck.Invalid("The address needs a host name or IP")
        if (uri.userInfo != null) return UrlCheck.Invalid("Do not put credentials in the address")
        if (!uri.path.isNullOrEmpty() && uri.path != "/") return UrlCheck.Invalid("Use only the server address, without a path")
        if (uri.query != null || uri.fragment != null) return UrlCheck.Invalid("Remove the query or fragment")
        val normalized = buildString {
            append(uri.scheme).append("://").append(if (":" in host) "[$host]" else host)
            if (uri.port != -1) append(':').append(uri.port)
            append('/')
        }
        val warning = if (uri.scheme == "http" && !isPrivateOrTailnet(host)) {
            "This is an unencrypted connection to a non-private address. Your password and tokens would be visible on the network. Use https:// or your Tailscale address."
        } else if (uri.scheme == "http") {
            "Traffic is not TLS-encrypted by the app. This is acceptable over Tailscale (WireGuard) or a trusted LAN; use https:// where possible."
        } else null
        if (host == "localhost" || host == "127.0.0.1" || host == "::1") {
            return UrlCheck.Valid(normalized, "On a phone, \"localhost\" is the phone itself, not your server. Use the server's Tailscale name or IP.")
        }
        return UrlCheck.Valid(normalized, warning)
    }

    internal fun isPrivateOrTailnet(host: String): Boolean {
        if (host.endsWith(".ts.net") || host.endsWith(".local") || host.endsWith(".lan") || host.endsWith(".home.arpa") || !host.contains('.') && !host.contains(':')) return true
        val p = host.split('.').mapNotNull { it.toIntOrNull() }
        if (p.size == 4) {
            return p[0] == 10 || (p[0] == 172 && p[1] in 16..31) || (p[0] == 192 && p[1] == 168) ||
                (p[0] == 100 && p[1] in 64..127) || p[0] == 127
        }
        return host.startsWith("fd") || host.startsWith("fe80") || host == "::1"
    }
}
