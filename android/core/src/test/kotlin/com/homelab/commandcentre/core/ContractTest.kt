package com.homelab.commandcentre.core

import com.homelab.commandcentre.core.api.*
import kotlinx.serialization.builtins.ListSerializer
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Guards the wire contract: models must parse what the actual backend emits. */
class ContractTest {
    @Test fun overviewParsesAndKeepsUnavailableAsNull() {
        val o = Fixtures.load("overview", Overview.serializer())
        assertNotNull(o.host)
        assertNotNull(o.host!!.memory)
        assertNull(o.host!!.swap)            // unavailable stays null (not zero)
        assertNull(o.host!!.temperatureC)
        assertTrue(o.containers.available)
        assertEquals(2, o.containers.running)
        assertEquals("missing", o.volumes.single().state) // /mnt/media does not exist in the fixture env
        assertEquals(10, o.refreshSeconds)
    }

    @Test fun servicesAndContainersAndControlFlags() {
        val services = Fixtures.load("services", Page.serializer(ServiceView.serializer()))
        val plex = services.items.first { it.name == "Plex" }
        assertEquals(listOf("restart", "start", "stop"), plex.allowedActions)
        assertEquals("healthy", plex.healthStatus)
        assertEquals("healthy", plex.effectiveStatus)
        val c = Fixtures.load("containers", ContainerList.serializer())
        assertTrue(c.dockerAvailable)
        val plexC = c.containers.first { it.name == "plex" }
        assertTrue(plexC.canControl)
        assertEquals(12, plexC.shortId.length)
        assertNotNull(plexC.stats?.cpuPercent)
        assertNull(c.containers.first { it.name == "old" }.stats)
        assertFalse(c.containers.first { it.name == "pihole" }.canControl)
    }

    @Test fun alertsEventsBackupsSettingsHistoryStorage() {
        val alerts = Fixtures.load("alerts", Page.serializer(AlertOut.serializer()))
        assertTrue(alerts.items.any { it.type == "mount_unavailable" && it.severity == "critical" })
        assertTrue(Fixtures.load("events", Page.serializer(EventOut.serializer())).items.isNotEmpty())
        val backups = Fixtures.load("backups", ListSerializer(BackupJob.serializer()))
        assertEquals("reported_success", backups.single().state)
        val s = Fixtures.load("settings", SettingsResponse.serializer())
        assertTrue(s.dockerControlEnabled)
        assertEquals(10, s.settings.dashboardRefreshSeconds)
        val h = Fixtures.load("history", HistoryResponse.serializer())
        assertEquals(3, h.points.size)
        assertNull(h.points.first().swapPercent)
        val st = Fixtures.load("storage", StorageResponse.serializer())
        assertEquals("root", st.root?.kind)
        assertEquals("missing", st.volumes.single().state)
        assertEquals(1, Fixtures.load("sessions", ListSerializer(SessionOut.serializer())).size)
    }

    @Test fun logsActionAndErrors() {
        assertEquals(2, Fixtures.load("logs", ContainerLogs.serializer()).lines.size)
        val a = Fixtures.load("action", ContainerActionResult.serializer())
        assertTrue(a.ok); assertEquals("restart", a.action)
        val forbidden = Fixtures.load("error_forbidden", ApiErrorEnvelope.serializer())
        assertEquals("not_permitted", forbidden.error.code)
        val validation = Fixtures.load("error_validation", ApiErrorEnvelope.serializer())
        assertEquals("blocked_url", validation.error.code)
        assertEquals("url", validation.error.details?.single()?.field)
    }

    @Test fun unknownFieldsFromNewerServersAreIgnored() {
        val json = """{"status":"ok","version":"9.9","time":"2030-01-01T00:00:00Z","brand_new_field":{"x":1}}"""
        assertEquals("9.9", ApiJson.decodeFromString(HealthOut.serializer(), json).version)
    }
}
