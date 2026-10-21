package com.homelab.commandcentre.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.homelab.commandcentre.core.api.*
import com.homelab.commandcentre.core.data.Loadable
import com.homelab.commandcentre.core.domain.Format
import com.homelab.commandcentre.ui.components.*
import com.homelab.commandcentre.ui.theme.LocalStatusColors
import com.homelab.commandcentre.viewmodel.*

@Composable
fun ScreenScaffold(title: String, onRefresh: () -> Unit, actions: @Composable RowScope.() -> Unit = {}, content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
            Text(title, style = MaterialTheme.typography.headlineSmall)
            Row(verticalAlignment = Alignment.CenterVertically, content = actions)
        }
        PullToRefreshBox(isRefreshing = false, onRefresh = onRefresh, modifier = Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = content)
        }
    }
}

private val hostStatus = mapOf(
    "healthy" to (Format.Level.Ok to "All systems healthy"),
    "warning" to (Format.Level.Warn to "Needs attention"),
    "critical" to (Format.Level.Crit to "Critical issues"),
    "unknown" to (Format.Level.Unknown to "Status unknown"),
)

@Composable
fun HomeScreen(vm: HomeViewModel, onNavigate: (String) -> Unit) {
    val state by vm.overview.collectAsState()
    val history by vm.history.collectAsState()
    ScreenScaffold("Overview", vm::refresh) {
        LoadableContent(state, vm::refresh) { o ->
            val (lvl, label) = hostStatus[o.status] ?: hostStatus.getValue("unknown")
            SectionCard {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    StatusChip(lvl, label)
                    Text(Format.ago(o.lastUpdate), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                o.statusReason?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                Text("Last host sample ${o.lastUpdate ?: Format.NA}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                o.host?.let { Text("Uptime ${Format.duration(it.uptimeSeconds)} · Load ${it.loadAvg?.joinToString(" ") { v -> "%.2f".format(v) } ?: Format.NA}", style = MaterialTheme.typography.bodySmall) }
            }
            val h = o.host
            if (h == null) SectionCard { CenteredMessage("No host metrics yet", "The monitor has not produced a sample.") } else {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    MetricTile("CPU", h.cpuPercent?.let { "%.0f".format(it) }, "%", h.cpuPercent, h.cpuCount?.let { "$it threads" }, Modifier.weight(1f))
                    MetricTile("Memory", h.memory?.let { "%.0f".format(it.percent) }, "%", h.memory?.percent, h.memory?.let { "${Format.bytes(it.availableBytes)} free" }, Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    val root = o.rootVolume?.takeIf { it.state == "ok" }
                    MetricTile("Root disk", root?.percent?.let { "%.0f".format(it) }, "%", root?.percent, root?.let { "${Format.bytes(it.freeBytes)} free" }, Modifier.weight(1f))
                    MetricTile("CPU temp", h.temperatureC?.let { "%.0f".format(it) }, "°C", null, null, Modifier.weight(1f))
                }
                SectionCard("Network") {
                    val n = h.network
                    if (n == null) Text("Host network counters unavailable", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    else Text("↓ ${Format.rate(n.rxBps)}   ↑ ${Format.rate(n.txBps)}", style = MaterialTheme.typography.titleMedium)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                SectionCard("Containers", Modifier.weight(1f).clickable { onNavigate("containers") }) {
                    if (!o.containers.available) Text("Docker unavailable", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    else { Text("${o.containers.running} running", style = MaterialTheme.typography.titleLarge); Text("${o.containers.stopped} stopped · ${o.containers.unhealthy} unhealthy", style = MaterialTheme.typography.bodySmall) }
                }
                SectionCard("Services", Modifier.weight(1f).clickable { onNavigate("services") }) {
                    Text("${o.services.healthy} healthy", style = MaterialTheme.typography.titleLarge)
                    Text("${o.services.unhealthy} unhealthy · ${o.services.unknown + o.services.degraded} other", style = MaterialTheme.typography.bodySmall)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                SectionCard("Alerts", Modifier.weight(1f).clickable { onNavigate("alerts") }) {
                    Text("${o.alerts.open} open", style = MaterialTheme.typography.titleLarge)
                    Text("${o.alerts.critical} critical · ${o.alerts.warning} warning", style = MaterialTheme.typography.bodySmall)
                }
                SectionCard("Backups", Modifier.weight(1f).clickable { onNavigate("backups") }) {
                    Text("${o.backups.ok} / ${o.backups.total} OK", style = MaterialTheme.typography.titleLarge)
                    Text(if (o.backups.problem > 0) "${o.backups.problem} need attention" else "No problems", style = MaterialTheme.typography.bodySmall)
                }
            }
            SectionCard("Storage", Modifier.clickable { onNavigate("storage") }) {
                (listOfNotNull(o.rootVolume) + o.volumes).forEach { v -> VolumeRow(v) }
            }
            (history as? Loadable.Content)?.data?.points?.let { pts ->
                val s = LocalStatusColors.current
                LineChart("CPU & memory · last hour", listOf(ChartSeries("CPU", s.series1, pts.map { it.cpuPercent }), ChartSeries("Memory", s.series2, pts.map { it.memPercent })), maxFixed = 100.0) { Format.percent(it) }
            }
            if (o.recentAlerts.isNotEmpty()) SectionCard("Recent alerts", Modifier.clickable { onNavigate("alerts") }) {
                o.recentAlerts.forEach { a -> AlertLine(a) }
            }
        }
    }
}

@Composable
fun VolumeRow(v: VolumeStatus) {
    val lvl = if (v.state == "ok") Format.level(v.percent) else if (v.state == "disabled") Format.Level.Unknown else Format.Level.Crit
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text(v.name, style = MaterialTheme.typography.titleSmall)
            if (v.state == "ok") Text(Format.percent(v.percent)) else StatusChip(lvl, when (v.state) { "unmounted" -> "Not mounted"; "missing" -> "Missing"; "unresponsive" -> "Not responding"; "unreadable" -> "Unreadable"; else -> v.state })
        }
        if (v.state == "ok" && v.percent != null) {
            UsageBar(v.percent!!, "${v.name} usage", lvl)
            Text("${Format.bytes(v.usedBytes)} of ${Format.bytes(v.totalBytes)} · ${Format.bytes(v.freeBytes)} free", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else Text(v.message ?: "", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun AlertLine(a: AlertOut) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(a.title, style = MaterialTheme.typography.bodyMedium)
            Text(Format.ago(a.lastSeenAt), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        when {
            a.status == "resolved" -> StatusChip(Format.Level.Ok, "Resolved")
            a.severity == "critical" -> StatusChip(Format.Level.Crit, "Critical")
            else -> StatusChip(Format.Level.Warn, "Warning")
        }
    }
}

@Composable
fun ServicesScreen(vm: ServicesViewModel, onOpen: (Int) -> Unit) {
    val state by vm.services.collectAsState()
    ScreenScaffold("Services", vm::refresh) {
        LoadableContent(state, vm::refresh) { list ->
            if (list.isEmpty()) CenteredMessage("No services configured", "Add services from the web dashboard (Services → Add service).")
            list.groupBy { it.category }.forEach { (cat, items) ->
                SectionCard(cat) {
                    items.forEach { s ->
                        val (lvl, label) = serviceLevel(s.effectiveStatus)
                        Row(Modifier.fillMaxWidth().clickable { onOpen(s.id) }.padding(vertical = 6.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(s.name, style = MaterialTheme.typography.titleSmall)
                                Text(s.url ?: "container: ${s.containerName}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            StatusChip(lvl, label)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun ServiceDetailScreen(vm: ServiceDetailViewModel, onBack: () -> Unit, onContainer: (String) -> Unit) {
    val state by vm.service.collectAsState()
    val checking by vm.checking.collectAsState()
    val checkError by vm.checkError.collectAsState()
    ScreenScaffold("Service", vm::refresh, actions = { TextButton(onBack) { Text("Back") } }) {
        LoadableContent(state, vm::refresh) { s ->
            val (lvl, label) = serviceLevel(s.effectiveStatus)
            SectionCard(s.name) {
                StatusChip(lvl, label)
                s.effectiveReason?.let { Text(it) }
                s.description?.let { Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
            if (s.url != null) SectionCard("Health check") {
                Text(s.url!!, style = MaterialTheme.typography.bodySmall)
                Text("Last check: ${Format.ago(s.lastCheckedAt)}")
                Text("Result: " + when { s.healthStatus == "unknown" -> "not checked yet"; s.lastError != null -> s.lastError!!; else -> "OK (HTTP ${s.lastStatusCode ?: Format.NA})" })
                Text("Response time: ${s.lastResponseMs?.let { "%.0f ms".format(it) } ?: Format.NA}")
                Text("Last success: ${Format.ago(s.lastSuccessAt)} · failures in a row: ${s.consecutiveFailures}")
                checkError?.let { Text(it, color = LocalStatusColors.current.crit) }
                Button(vm::checkNow, enabled = !checking) { Text(if (checking) "Checking…" else "Check now") }
            }
            if (s.containerName != null) SectionCard("Docker") {
                Text("Container: ${s.containerName}")
                Text("State: ${s.containerState ?: "unknown (Docker unavailable)"}")
                Text("Remote control: " + if (s.allowControl) "allowed (${s.allowedActions.joinToString()})" else "not permitted")
                OutlinedButton({ onContainer(s.containerName!!) }) { Text("Open container") }
            }
        }
    }
}

@Composable
fun MetricsScreen(vm: MetricsViewModel) {
    val state by vm.history.collectAsState()
    val range by vm.selectedRange.collectAsState()
    ScreenScaffold("Metrics", vm::refresh) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("1h", "6h", "24h", "7d", "30d").forEach { r -> FilterChip(selected = r == range, onClick = { vm.select(r) }, label = { Text(r) }) }
        }
        LoadableContent(state, vm::refresh) { h ->
            val s = LocalStatusColors.current
            val p = h.points
            LineChart("CPU utilisation", listOf(ChartSeries("CPU", s.series1, p.map { it.cpuPercent })), maxFixed = 100.0) { Format.percent(it) }
            LineChart("Memory utilisation", listOf(ChartSeries("Memory", s.series1, p.map { it.memPercent })), maxFixed = 100.0) { Format.percent(it) }
            LineChart("Storage utilisation", listOf(ChartSeries("Root", s.series1, p.map { it.diskRootPercent }), ChartSeries("Fullest volume", s.series2, p.map { it.storageMaxPercent })), maxFixed = 100.0) { Format.percent(it) }
            LineChart("Network throughput", listOf(ChartSeries("Download", s.series1, p.map { it.netRxBps }), ChartSeries("Upload", s.series2, p.map { it.netTxBps }))) { Format.rate(it) }
            LineChart("CPU temperature", listOf(ChartSeries("Temp", s.series2, p.map { it.tempC }))) { Format.temp(it) }
        }
    }
}

@Composable
fun AlertsScreen(vm: AlertsViewModel) {
    val open by vm.open.collectAsState()
    val events by vm.events.collectAsState()
    var tab by remember { mutableIntStateOf(0) }
    ScreenScaffold("Alerts", vm::refresh) {
        TabRow(selectedTabIndex = tab) {
            listOf("Open", "Events").forEachIndexed { i, t -> Tab(tab == i, { tab = i }, text = { Text(t) }) }
        }
        if (tab == 0) LoadableContent(open, vm::refresh) { list ->
            if (list.isEmpty()) CenteredMessage("No open alerts", "Everything monitored is within its limits.")
            list.forEach { a ->
                SectionCard {
                    AlertLine(a)
                    Text(a.message, style = MaterialTheme.typography.bodySmall)
                    if (a.acknowledgedAt != null) Text("Acknowledged by ${a.acknowledgedBy}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    else OutlinedButton({ vm.acknowledge(a.id) }) { Text("Acknowledge") }
                }
            }
        } else LoadableContent(events, vm::refresh) { list ->
            SectionCard { list.forEach { e -> Column(Modifier.padding(vertical = 4.dp)) { Text(e.message, style = MaterialTheme.typography.bodyMedium); Text("${Format.ago(e.ts)} · ${e.actor ?: "system"}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) } } }
        }
    }
}

@Composable
fun SettingsScreen(vm: SettingsViewModel, onSignedOutOrServerChanged: () -> Unit, requestNotificationPermission: () -> Unit, onToggleWorker: (Boolean) -> Unit, onChangeServer: () -> Unit) {
    val settings by vm.settings.collectAsState()
    val sessions by vm.sessions.collectAsState()
    val notif by vm.notificationsEnabled.collectAsState()
    val message by vm.message.collectAsState()
    var cur by remember { mutableStateOf("") }
    var new by remember { mutableStateOf("") }
    var secs by remember { mutableStateOf(vm.refreshSeconds.toString()) }
    ScreenScaffold("Settings", vm::refresh) {
        SectionCard("Alerts") {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Notify me of critical alerts")
                    Text("Checked roughly every 15 minutes in the background. Use Telegram on the server for instant delivery.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(notif, { on -> vm.setNotifications(on); if (on) requestNotificationPermission(); onToggleWorker(on) })
            }
        }
        SectionCard("Appearance") {
            val theme by vm.theme.collectAsState()
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("dark" to "Dark", "light" to "Light", "system" to "System").forEach { (v, l) -> FilterChip(theme == v, { vm.setTheme(v) }, label = { Text(l) }) }
            }
        }
        SectionCard("Refresh interval") {
            val n = secs.toIntOrNull()
            OutlinedTextField(secs, { secs = it }, label = { Text("Seconds (5–300)") }, singleLine = true, isError = n == null || n !in 5..300, modifier = Modifier.fillMaxWidth())
            Button({ n?.takeIf { it in 5..300 }?.let(vm::setRefreshSeconds) }, enabled = n != null && n in 5..300) { Text("Save") }
        }
        SectionCard("Server") {
            LoadableContent(settings, vm::refresh) { s ->
                Text("Backend version ${s.version}")
                Text("Container control: " + if (s.dockerControlEnabled) "enabled on server" else "disabled (read-only)")
                Text("Telegram: " + if (s.telegramConfigured) "configured" else "not configured")
            }
            OutlinedButton(onChangeServer) { Text("Use a different server") }
        }
        SectionCard("Active sessions") {
            LoadableContent(sessions, vm::refresh) { list ->
                list.forEach { s ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text((if (s.client == "mobile") "Mobile app" else "Web browser") + if (s.current) " · this device" else "")
                            Text("Signed in ${Format.ago(s.createdAt)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (!s.current) TextButton({ vm.revoke(s.id) }) { Text("Sign out") }
                    }
                }
            }
        }
        SectionCard("Change password") {
            OutlinedTextField(cur, { cur = it }, label = { Text("Current password") }, singleLine = true, visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
            OutlinedTextField(new, { new = it }, label = { Text("New password (12+ characters)") }, singleLine = true, visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
            message?.let { Text(it) }
            Button({ vm.changePassword(cur, new) }, enabled = cur.isNotEmpty() && new.isNotEmpty()) { Text("Change password") }
        }
        OutlinedButton({ vm.logout(); onSignedOutOrServerChanged() }, Modifier.fillMaxWidth()) { Text("Sign out") }
    }
}
