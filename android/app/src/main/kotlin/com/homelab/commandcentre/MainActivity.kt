package com.homelab.commandcentre

import android.Manifest
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.homelab.commandcentre.core.auth.AuthState
import com.homelab.commandcentre.ui.screens.*
import com.homelab.commandcentre.ui.theme.HomeLabTheme
import com.homelab.commandcentre.viewmodel.*
import com.homelab.commandcentre.work.AlertWorker

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val container = (application as HomeLabApp).container
        setContent {
            val theme by container.theme.collectAsState()
            HomeLabTheme(theme) { Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) { Root(container) } }
        }
    }
}

@Composable
private fun Root(container: AppContainer) {
    val auth: AuthViewModel = viewModel(factory = Factory(container))
    val state by auth.state.collectAsState()
    val baseUrl by auth.baseUrl.collectAsState()
    when {
        baseUrl == null -> ConnectScreen(auth)
        else -> when (val s = state) {
            AuthState.Unknown -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
            AuthState.Unreachable -> ConnectScreen(auth, baseUrl.orEmpty())
            is AuthState.SetupRequired -> SetupScreen(auth, s.tokenRequired)
            AuthState.SignedOut -> LoginScreen(auth)
            is AuthState.SignedIn -> MainScaffold(container, auth)
        }
    }
}

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    Tab("home", "Home", Icons.Outlined.Home),
    Tab("services", "Services", Icons.Outlined.Dns),
    Tab("metrics", "Metrics", Icons.Outlined.ShowChart),
    Tab("alerts", "Alerts", Icons.Outlined.NotificationsNone),
    Tab("settings", "Settings", Icons.Outlined.Settings),
)

@Composable
private fun MainScaffold(container: AppContainer, auth: AuthViewModel) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val current = entry?.destination?.route
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    fun go(route: String) = nav.navigate(route) { launchSingleTop = true }

    Scaffold(
        bottomBar = {
            if (current in tabs.map { it.route }) NavigationBar {
                tabs.forEach { t ->
                    NavigationBarItem(
                        selected = current == t.route,
                        onClick = { nav.navigate(t.route) { popUpTo(nav.graph.findStartDestination().id) { saveState = true }; launchSingleTop = true; restoreState = true } },
                        icon = { Icon(t.icon, contentDescription = null) },
                        label = { Text(t.label) },
                    )
                }
            }
        },
    ) { pad ->
        NavHost(nav, startDestination = "home", modifier = Modifier.padding(pad)) {
            composable("home") { HomeScreen(viewModel(factory = Factory(container)), ::go) }
            composable("services") { ServicesScreen(viewModel(factory = Factory(container))) { go("service/$it") } }
            composable("service/{id}", listOf(navArgument("id") { type = NavType.IntType })) { e ->
                val id = e.arguments!!.getInt("id")
                ServiceDetailScreen(viewModel(key = "svc$id", factory = Factory(container, id.toString())), nav::popBackStack) { go("container/$it") }
            }
            composable("containers") { ContainersScreen(viewModel(factory = Factory(container))) { go("container/$it") } }
            composable("container/{id}", listOf(navArgument("id") { type = NavType.StringType })) { e ->
                val id = e.arguments!!.getString("id")!!
                ContainerDetailScreen(viewModel(key = "ctr$id", factory = Factory(container, id)), id, nav::popBackStack)
            }
            composable("metrics") { MetricsScreen(viewModel(factory = Factory(container))) }
            composable("alerts") { AlertsScreen(viewModel(factory = Factory(container))) }
            composable("storage") { StorageScreen(viewModel(factory = Factory(container)), nav::popBackStack) }
            composable("backups") { BackupsScreen(viewModel(factory = Factory(container)), nav::popBackStack) }
            composable("settings") {
                SettingsScreen(
                    viewModel(factory = Factory(container)),
                    onSignedOutOrServerChanged = {},
                    requestNotificationPermission = { if (android.os.Build.VERSION.SDK_INT >= 33) permission.launch(Manifest.permission.POST_NOTIFICATIONS) },
                    onToggleWorker = { on -> if (on) AlertWorker.schedule(ctx) else AlertWorker.cancel(ctx) },
                    onChangeServer = auth::changeServer,
                )
            }
        }
    }
}
