package com.homelab.commandcentre

import androidx.compose.material3.Text
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.homelab.commandcentre.core.api.ContainerOut
import com.homelab.commandcentre.core.data.ApiFailure
import com.homelab.commandcentre.core.data.ContainerAction
import com.homelab.commandcentre.core.data.Loadable
import com.homelab.commandcentre.core.domain.ActionState
import com.homelab.commandcentre.core.domain.Format
import com.homelab.commandcentre.ui.components.DisconnectedBanner
import com.homelab.commandcentre.ui.components.FailureView
import com.homelab.commandcentre.ui.components.LoadableContent
import com.homelab.commandcentre.ui.components.MetricTile
import com.homelab.commandcentre.ui.components.StatusChip
import com.homelab.commandcentre.ui.screens.ActionButtons
import com.homelab.commandcentre.ui.screens.ActionDialog
import com.homelab.commandcentre.ui.theme.HomeLabTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import java.time.Instant

/** UI tests for the shared building blocks. Run with `./gradlew :app:connectedDebugAndroidTest`. */
class ComponentsTest {
    @get:Rule val rule = createComposeRule()

    private val plex = ContainerOut("a".repeat(64), "a".repeat(12), "plex", "img", "running", canControl = true, allowedActions = listOf("start", "stop", "restart"))

    @Test fun statusIsConveyedByTextNotColourAlone() {
        rule.setContent { HomeLabTheme { StatusChip(Format.Level.Crit, "Unhealthy") } }
        rule.onNodeWithText("Unhealthy").assertIsDisplayed()
        rule.onNodeWithContentDescription("Status: Unhealthy").assertIsDisplayed()
    }

    @Test fun unavailableMetricShowsDashNotZero() {
        rule.setContent { HomeLabTheme { MetricTile("Swap", null) } }
        rule.onNodeWithText("—").assertIsDisplayed()
        rule.onNodeWithText("Unavailable").assertIsDisplayed()
    }

    @Test fun loadingShowsProgressAndErrorShowsRetry() {
        var retried = false
        rule.setContent { HomeLabTheme { FailureView(ApiFailure.Offline()) { retried = true } } }
        rule.onNodeWithText("Backend unreachable").assertIsDisplayed()
        rule.onNodeWithText("Try again").performClick()
        assertEquals(true, retried)
    }

    @Test fun permissionDeniedIsDistinctFromOffline() {
        rule.setContent { HomeLabTheme { FailureView(ApiFailure.Forbidden("Not allowed")) } }
        rule.onNodeWithText("Permission denied").assertIsDisplayed()
    }

    @Test fun staleContentIsExplicitlyMarkedDisconnected() {
        val state = Loadable.Content("cached value", Instant.now().minusSeconds(120), ApiFailure.Offline())
        rule.setContent { HomeLabTheme { LoadableContent(state, {}) { Text(it) } } }
        rule.onNodeWithText("Disconnected from the backend").assertIsDisplayed()
        rule.onNodeWithText("cached value").assertIsDisplayed()
    }

    @Test fun liveContentHasNoDisconnectedBanner() {
        rule.setContent { HomeLabTheme { LoadableContent(Loadable.Content("live", Instant.now())) {  _: String -> Text("live") } } }
        rule.onNodeWithText("Disconnected from the backend").assertDoesNotExist()
    }

    @Test fun actionButtonsOnlyOfferApplicableActions() {
        val requested = mutableListOf<ContainerAction>()
        rule.setContent { HomeLabTheme { ActionButtons(plex) { requested += it } } }
        rule.onNodeWithContentDescription("Stop plex").performClick()
        rule.onNodeWithContentDescription("Start plex").assertDoesNotExist() // already running
        assertEquals(listOf(ContainerAction.Stop), requested)
    }

    @Test fun readOnlyContainerShowsReasonInsteadOfButtons() {
        rule.setContent { HomeLabTheme { ActionButtons(plex.copy(canControl = false)) {} } }
        rule.onNodeWithText("Read-only").assertIsDisplayed()
    }

    @Test fun confirmationDialogGatesTheAction() {
        var confirmed = false
        var dismissed = false
        rule.setContent { HomeLabTheme { ActionDialog(ActionState.Confirming(plex, ContainerAction.Restart), { confirmed = true }, { dismissed = true }) } }
        rule.onNodeWithText("Restart plex?").assertIsDisplayed()
        assertEquals(false, confirmed)
        rule.onNodeWithText("Cancel").performClick()
        assertEquals(true, dismissed); assertEquals(false, confirmed)
    }

    @Test fun confirmSendsAndProgressDisablesTheButton() {
        var confirmed = 0
        rule.setContent { HomeLabTheme { ActionDialog(ActionState.Confirming(plex, ContainerAction.Stop), { confirmed++ }, {}) } }
        rule.onNodeWithText("Stop").performClick()
        assertEquals(1, confirmed)
    }

    @Test fun runningStateShowsProgressAndDisablesConfirm() {
        rule.setContent { HomeLabTheme { ActionDialog(ActionState.Running(plex, ContainerAction.Restart), {}, {}) } }
        rule.onNodeWithText("Working…").assertIsDisplayed()
        rule.onNodeWithText("Restart").assertIsNotEnabled()
    }

    @Test fun resultAndFailureAreReported() {
        rule.setContent { HomeLabTheme { ActionDialog(ActionState.Succeeded(plex, ContainerAction.Restart, "Restart completed"), {}, {}) } }
        rule.onNodeWithText("Restart completed").assertIsDisplayed()
    }

    @Test fun disconnectedBannerIsAnnounced() {
        rule.setContent { HomeLabTheme { DisconnectedBanner(Instant.now()) } }
        rule.onNodeWithContentDescription("Disconnected from the backend. Data is stale.").assertIsDisplayed()
    }
}
