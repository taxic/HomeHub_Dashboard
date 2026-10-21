package com.homelab.commandcentre.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.homelab.commandcentre.core.api.ContainerOut
import com.homelab.commandcentre.core.data.ContainerAction
import com.homelab.commandcentre.core.data.Loadable
import com.homelab.commandcentre.core.domain.ActionState
import com.homelab.commandcentre.core.domain.ContainerPolicy
import com.homelab.commandcentre.core.domain.Format
import com.homelab.commandcentre.ui.components.*
import com.homelab.commandcentre.viewmodel.*

fun containerLevel(c: ContainerOut): Pair<Format.Level, String> = when (c.state) {
    "running" -> when (c.health) {
        "unhealthy" -> Format.Level.Crit to "Running · unhealthy"
        "starting" -> Format.Level.Warn to "Running · starting"
        "healthy" -> Format.Level.Ok to "Running · healthy"
        else -> Format.Level.Ok to "Running"
    }
    "restarting" -> Format.Level.Warn to "Restarting"
    "exited" -> Format.Level.Crit to "Stopped"
    "dead" -> Format.Level.Crit to "Dead"
    "paused" -> Format.Level.Warn to "Paused"
    "created" -> Format.Level.Warn to "Created"
    else -> Format.Level.Unknown to "Unknown"
}

/** Confirmation -> progress -> result for container actions, driven by the shared controller state. */
@Composable
fun ActionDialog(state: ActionState, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    val (container, action) = when (state) {
        is ActionState.Confirming -> state.container to state.action
        is ActionState.Running -> state.container to state.action
        is ActionState.Succeeded -> state.container to state.action
        is ActionState.Failed -> state.container to state.action
        ActionState.Idle -> return
    }
    ConfirmDialog(
        title = "${action.label} ${container.name}?",
        body = when (action) {
            ContainerAction.Stop -> "The container will be stopped and will not restart automatically. Services in it will become unavailable."
            ContainerAction.Restart -> "The container will be restarted. Services in it will be briefly unavailable."
            ContainerAction.Start -> "The container will be started."
        },
        confirmLabel = action.label,
        destructive = action.destructive,
        running = state is ActionState.Running,
        result = (state as? ActionState.Succeeded)?.message,
        error = (state as? ActionState.Failed)?.message,
        onConfirm = onConfirm,
        onDismiss = onDismiss,
    )
}

@Composable
fun ActionButtons(c: ContainerOut, onAction: (ContainerAction) -> Unit) {
    val available = ContainerPolicy.available(c)
    if (available.isEmpty()) {
        Text(ContainerPolicy.readOnlyReason(c) ?: "No actions available", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        available.forEach { a -> OutlinedButton({ onAction(a) }, Modifier.semantics { contentDescription = "${a.label} ${c.name}" }) { Text(a.label) } }
    }
}

@Composable
fun ContainersScreen(vm: ContainersViewModel, onOpen: (String) -> Unit) {
    val state by vm.containers.collectAsState()
    val action by vm.action.collectAsState()
    ScreenScaffold("Containers", vm::refresh) {
        LoadableContent(state, vm::refresh) { d ->
            if (!d.dockerAvailable) SectionCard("Docker is unavailable") { Text(d.dockerError ?: "The Docker integration cannot be reached. No container data is shown rather than stale values.") }
            else if (d.containers.isEmpty()) CenteredMessage("No containers found")
            d.containers.forEach { c ->
                val (lvl, label) = containerLevel(c)
                SectionCard {
                    Row(Modifier.fillMaxWidth().clickable { onOpen(c.id) }, horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(c.name, style = MaterialTheme.typography.titleSmall)
                            Text(c.image, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        StatusChip(lvl, label)
                    }
                    Text("CPU ${Format.percent(c.stats?.cpuPercent, 1)} · Mem ${Format.bytes(c.stats?.memoryBytes)}", style = MaterialTheme.typography.bodySmall)
                    ActionButtons(c) { a -> vm.request(c, a) }
                }
            }
        }
    }
    ActionDialog(action, onConfirm = vm::confirm, onDismiss = vm::dismiss)
}

@Composable
fun ContainerDetailScreen(vm: ContainerDetailViewModel, ref: String, onBack: () -> Unit) {
    val state by vm.containers.collectAsState()
    val action by vm.action.collectAsState()
    val logs by vm.logs.collectAsState()
    LaunchedEffect(ref) { vm.loadLogs() }
    ScreenScaffold("Container", vm::refresh, actions = { TextButton(onBack) { Text("Back") } }) {
        LoadableContent(state, vm::refresh) { d ->
            val c = d.containers.firstOrNull { it.id == ref || it.name == ref || it.id.startsWith(ref) }
            if (c == null) { CenteredMessage("Container not found", if (d.dockerAvailable) "It may have been removed." else "Docker is unavailable."); return@LoadableContent }
            val (lvl, label) = containerLevel(c)
            SectionCard(c.name) {
                StatusChip(lvl, label)
                Text("${c.shortId} · ${c.image}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("Started: ${Format.ago(c.startedAt)} · restarts: ${c.restartCount ?: Format.NA}")
                Text("Service: ${c.serviceName ?: "not linked"}")
                ActionButtons(c) { a -> vm.request(c, a) }
            }
            SectionCard("Resources") {
                if (c.stats == null) Text("Stats unavailable (not running, or Docker did not report them).", color = MaterialTheme.colorScheme.onSurfaceVariant)
                else { Text("CPU: ${Format.percent(c.stats!!.cpuPercent, 1)}"); Text("Memory: ${Format.bytes(c.stats!!.memoryBytes)}" + (c.stats!!.memoryLimitBytes?.let { " of ${Format.bytes(it)}" } ?: "")) }
            }
            SectionCard("Recent logs") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(50, 100, 200).forEach { n -> FilterChip(vm.tail == n, { vm.loadLogs(n) }, label = { Text("$n") }) }
                    TextButton({ vm.loadLogs() }) { Text("Reload") }
                }
                when (val l = logs) {
                    Loadable.Loading -> CircularProgressIndicator(Modifier.size(24.dp))
                    is Loadable.Failed -> FailureView(l.failure) { vm.loadLogs() }
                    is Loadable.Content -> Text(
                        l.data.lines.joinToString("\n").ifEmpty { "(no log output)" },
                        fontFamily = FontFamily.Monospace, fontSize = 11.sp,
                        modifier = Modifier.fillMaxWidth().background(Color(0xFF0A0D11), RoundedCornerShape(8.dp)).padding(10.dp).horizontalScroll(rememberScrollState()),
                        color = Color(0xFFD6DBE1),
                    )
                }
            }
        }
    }
    ActionDialog(action, onConfirm = vm::confirm, onDismiss = vm::dismiss)
}

@Composable
fun StorageScreen(vm: StorageViewModel, onBack: () -> Unit) {
    val state by vm.storage.collectAsState()
    ScreenScaffold("Storage", vm::refresh, actions = { TextButton(onBack) { Text("Back") } }) {
        Text("Read-only: nothing is mounted, repaired or written by this app.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        LoadableContent(state, vm::refresh) { s ->
            (listOfNotNull(s.root) + s.volumes).forEach { v -> SectionCard(v.path) { VolumeRow(v); Text("Checked ${Format.ago(v.checkedAt)}", style = MaterialTheme.typography.labelSmall) } }
            SectionCard("Disk I/O") { Text("Read ${Format.rate(s.diskIo?.readBps)} · Write ${Format.rate(s.diskIo?.writeBps)}") }
        }
    }
}

@Composable
fun BackupsScreen(vm: BackupsViewModel, onBack: () -> Unit) {
    val state by vm.backups.collectAsState()
    ScreenScaffold("Backups", vm::refresh, actions = { TextButton(onBack) { Text("Back") } }) {
        LoadableContent(state, vm::refresh) { jobs ->
            if (jobs.isEmpty()) CenteredMessage("No backup jobs", "Add jobs from the web dashboard; your backup scripts report results to the API.")
            jobs.forEach { j ->
                val (lvl, label) = when (j.state) {
                    "restore_verified" -> Format.Level.Ok to "Restore verified"
                    "reported_success" -> Format.Level.Warn to "Success reported (unverified)"
                    "never_run" -> Format.Level.Warn to "Never reported"
                    "overdue" -> Format.Level.Crit to "Overdue"
                    "failed" -> Format.Level.Crit to "Failed"
                    "restore_failed" -> Format.Level.Crit to "Restore test failed"
                    else -> Format.Level.Unknown to "Disabled"
                }
                SectionCard(j.name) {
                    StatusChip(lvl, label)
                    Text(j.stateReason ?: "", style = MaterialTheme.typography.bodySmall)
                    Text("Last success: ${Format.ago(j.lastSuccessAt)} · max age ${j.maxAgeHours}h")
                    Text("Restore test: " + (j.lastRestoreTestAt?.let { (if (j.lastRestoreTestOk == true) "passed " else "FAILED ") + Format.ago(it) } ?: "none recorded"))
                }
            }
        }
    }
}
