package com.homelab.commandcentre.core

import com.homelab.commandcentre.core.api.ContainerOut
import com.homelab.commandcentre.core.data.ContainerAction
import com.homelab.commandcentre.core.domain.ContainerPolicy
import com.homelab.commandcentre.core.domain.Format
import com.homelab.commandcentre.core.domain.UrlCheck
import com.homelab.commandcentre.core.domain.UrlPolicy
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PolicyTest {
    private fun c(state: String = "running", control: Boolean = true, protected: Boolean = false, actions: List<String> = listOf("start", "stop", "restart")) =
        ContainerOut("a".repeat(64), "a".repeat(12), "plex", "img", state, canControl = control, allowedActions = actions, protected = protected)

    @Test fun runningContainerOffersStopAndRestartNotStart() =
        assertEquals(listOf(ContainerAction.Stop, ContainerAction.Restart), ContainerPolicy.available(c()))

    @Test fun stoppedContainerOffersOnlyStart() =
        assertEquals(listOf(ContainerAction.Start), ContainerPolicy.available(c(state = "exited")))

    @Test fun respectsPerServiceAllowList() =
        assertEquals(listOf(ContainerAction.Restart), ContainerPolicy.available(c(actions = listOf("restart"))))

    @Test fun readOnlyAndProtectedOfferNothing() {
        assertTrue(ContainerPolicy.available(c(control = false)).isEmpty())
        assertTrue(ContainerPolicy.available(c(protected = true)).isEmpty())
        assertEquals("Protected container", ContainerPolicy.readOnlyReason(c(protected = true)))
        assertEquals("Read-only", ContainerPolicy.readOnlyReason(c(control = false)))
        assertNull(ContainerPolicy.readOnlyReason(c()))
    }

    @Test fun stopAndRestartAreMarkedDestructiveForConfirmation() {
        assertTrue(ContainerAction.Stop.destructive && ContainerAction.Restart.destructive)
        assertTrue(!ContainerAction.Start.destructive)
    }

    @Test fun urlValidation() {
        fun valid(s: String) = UrlPolicy.check(s) as UrlCheck.Valid
        assertEquals("http://100.101.102.103:8080/", valid("http://100.101.102.103:8080").normalized)
        assertEquals("https://homelab.tail1234.ts.net/", valid(" https://homelab.tail1234.ts.net ").normalized)
        listOf("", "homelab", "ftp://x", "http://", "http://u:p@host/", "http://host/api", "http://host/?x=1", "javascript:alert(1)")
            .forEach { assertTrue(UrlPolicy.check(it) is UrlCheck.Invalid, "should reject '$it'") }
    }

    @Test fun cleartextWarnings() {
        assertTrue(valid("http://203.0.113.9:8080").warning!!.contains("unencrypted"))
        assertTrue(valid("http://192.168.1.10:8080").warning!!.contains("acceptable"))
        assertTrue(valid("http://100.64.1.2:8080").warning!!.contains("Tailscale"))
        assertNull(valid("https://example.com").warning)
        assertTrue(valid("http://localhost:8000").warning!!.contains("phone itself"))
    }

    private fun valid(s: String) = UrlPolicy.check(s) as UrlCheck.Valid

    @Test fun formatDistinguishesZeroFromUnavailable() {
        assertEquals("0%", Format.percent(0.0)); assertEquals("—", Format.percent(null))
        assertEquals("0 B/s", Format.rate(0.0)); assertEquals("—", Format.rate(null))
        assertEquals("1.5 KB", Format.bytes(1536)); assertEquals("—", Format.bytes(null))
        assertEquals("1d 1h", Format.duration(90061.0)); assertEquals("—", Format.duration(null))
        val now = Instant.parse("2026-01-01T12:00:00Z")
        assertEquals("2m ago", Format.ago("2026-01-01T11:58:00Z", now)); assertEquals("never", Format.ago(null, now))
        assertEquals(Format.Level.Warn, Format.level(90.0)); assertEquals(Format.Level.Unknown, Format.level(null))
    }
}
