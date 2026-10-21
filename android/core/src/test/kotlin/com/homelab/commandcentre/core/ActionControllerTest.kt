package com.homelab.commandcentre.core

import com.homelab.commandcentre.core.api.ApiClient
import com.homelab.commandcentre.core.api.ContainerOut
import com.homelab.commandcentre.core.auth.InMemoryTokenStore
import com.homelab.commandcentre.core.auth.SessionManager
import com.homelab.commandcentre.core.data.ContainerAction
import com.homelab.commandcentre.core.data.HomeLabRepository
import com.homelab.commandcentre.core.domain.ActionState
import com.homelab.commandcentre.core.domain.ContainerActionController
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class ActionControllerTest {
    private lateinit var server: MockWebServer
    private lateinit var controller: ContainerActionController

    private val plex = ContainerOut("a".repeat(64), "a".repeat(12), "plex", "img", "running", canControl = true, allowedActions = listOf("start", "stop", "restart"))

    @BeforeTest fun setUp() {
        server = MockWebServer().also { it.start() }
        val tokens = InMemoryTokenStore().also { it.accessToken = "t" }
        lateinit var c: ApiClient
        val session = SessionManager({ c.authApi }, tokens)
        c = ApiClient(server.url("/").toString(), tokens, session)
        controller = ContainerActionController(HomeLabRepository { c.api })
    }

    @AfterTest fun tearDown() = server.shutdown()

    private fun ok() = MockResponse().setHeader("Content-Type", "application/json").setBody(Fixtures.text("action"))

    @Test fun nothingIsSentUntilConfirmed() = runBlocking<Unit> {
        controller.request(plex, ContainerAction.Restart)
        assertIs<ActionState.Confirming>(controller.state.value)
        assertEquals(0, server.requestCount)
        controller.dismiss()
        assertEquals(ActionState.Idle, controller.state.value)
        assertFalse(controller.confirm())          // nothing to confirm after dismissal
        assertEquals(0, server.requestCount)
    }

    @Test fun confirmSendsExactlyOneRequestAndReportsResult() = runBlocking<Unit> {
        server.enqueue(ok())
        controller.request(plex, ContainerAction.Restart)
        assertTrue(controller.confirm())
        val s = assertIs<ActionState.Succeeded>(controller.state.value)
        assertTrue(s.message.isNotBlank())
        assertFalse(controller.confirm())          // cannot be re-sent without a new confirmation
        assertEquals(1, server.requestCount)
        assertEquals("/api/v1/containers/${plex.id}/restart", server.takeRequest().path)
    }

    @Test fun serverRefusalIsShownNotSwallowed() = runBlocking<Unit> {
        server.enqueue(MockResponse().setResponseCode(403).setHeader("Content-Type", "application/json").setBody(Fixtures.text("error_forbidden")))
        controller.request(plex, ContainerAction.Stop)
        controller.confirm()
        val f = assertIs<ActionState.Failed>(controller.state.value)
        assertTrue(f.message.contains("not permitted"))
    }

    @Test fun actionsNotOfferedCannotBeRequested() {
        controller.request(plex.copy(canControl = false), ContainerAction.Restart)
        assertEquals(ActionState.Idle, controller.state.value)
        controller.request(plex, ContainerAction.Start) // already running
        assertEquals(ActionState.Idle, controller.state.value)
        controller.request(plex.copy(protected = true), ContainerAction.Stop)
        assertEquals(ActionState.Idle, controller.state.value)
    }

    @Test fun networkFailureDuringActionReportsOffline() = runBlocking<Unit> {
        controller.request(plex, ContainerAction.Restart)
        server.shutdown()
        controller.confirm()
        val f = assertIs<ActionState.Failed>(controller.state.value)
        assertTrue(f.message.contains("Cannot reach"))
    }
}
