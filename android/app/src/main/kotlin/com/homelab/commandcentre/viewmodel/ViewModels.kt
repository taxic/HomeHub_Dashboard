package com.homelab.commandcentre.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.homelab.commandcentre.AppContainer
import com.homelab.commandcentre.core.api.*
import com.homelab.commandcentre.core.auth.AuthState
import com.homelab.commandcentre.core.data.*
import com.homelab.commandcentre.core.domain.ActionState
import com.homelab.commandcentre.core.domain.ContainerActionController
import com.homelab.commandcentre.core.domain.UrlCheck
import com.homelab.commandcentre.core.domain.UrlPolicy
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** Polling state with a pull-to-refresh hook; shared by all read-only screens. */
abstract class PollingViewModel : ViewModel() {
    protected val refreshRequests = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    fun refresh() { refreshRequests.tryEmit(Unit) }

    protected fun <T> poll(interval: () -> Long, fetch: suspend () -> ApiResult<T>): StateFlow<Loadable<T>> =
        pollingFlow(interval, refreshRequests, fetch = fetch)
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), Loadable.Loading)
}

class AuthViewModel(private val c: AppContainer) : ViewModel() {
    val state: StateFlow<AuthState> = c.session.state
    val baseUrl: StateFlow<String?> = c.baseUrl

    private val _busy = MutableStateFlow(false)
    val busy = _busy.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error = _error.asStateFlow()
    private val _urlWarning = MutableStateFlow<String?>(null)
    val urlWarning = _urlWarning.asStateFlow()

    init { start() }

    fun start() {
        if (c.baseUrl.value != null) viewModelScope.launch { c.session.bootstrap() }
    }

    /** Validate, probe /health, then save the server address. */
    fun connect(input: String) {
        when (val check = UrlPolicy.check(input)) {
            is UrlCheck.Invalid -> { _error.value = check.reason; _urlWarning.value = null }
            is UrlCheck.Valid -> viewModelScope.launch {
                _busy.value = true; _error.value = null; _urlWarning.value = check.warning
                when (val r = safeCall { c.probe(check.normalized).authApi.health() }) {
                    is ApiResult.Success -> { c.setBaseUrl(check.normalized); c.session.bootstrap() }
                    is ApiResult.Failure -> _error.value = when (r.failure) {
                        is ApiFailure.Offline -> "Could not reach ${check.normalized}. Check the address and that Tailscale is connected."
                        else -> "The server answered, but not like a HomeLab backend (${r.failure.message})."
                    }
                }
                _busy.value = false
            }
        }
    }

    fun login(user: String, pass: String) = submit { c.session.login(user.trim(), pass) }
    fun setup(user: String, pass: String, token: String?) = submit {
        when {
            pass.length < 12 -> ApiResult.Failure(ApiFailure.Validation("Use at least 12 characters"))
            else -> c.session.setup(user.trim(), pass, token)
        }
    }

    private fun submit(block: suspend () -> ApiResult<Unit>) = viewModelScope.launch {
        _busy.value = true; _error.value = null
        (block() as? ApiResult.Failure)?.let { _error.value = it.failure.message }
        _busy.value = false
    }

    fun changeServer() = viewModelScope.launch {
        c.session.logout() // revoke server-side first, best effort
        c.clearServer()
    }
    fun clearError() { _error.value = null }
}

class HomeViewModel(c: AppContainer) : PollingViewModel() {
    val overview = poll(c::refreshIntervalMs) { c.repository.overview() }
    val history = poll({ maxOf(15_000, c.refreshIntervalMs()) }) { c.repository.history("1h") }
}

class ServicesViewModel(c: AppContainer) : PollingViewModel() {
    val services = poll(c::refreshIntervalMs) { c.repository.services() }
}

class ServiceDetailViewModel(private val c: AppContainer, private val id: Int) : PollingViewModel() {
    val service = poll(c::refreshIntervalMs) { c.repository.service(id) }
    private val _checking = MutableStateFlow(false)
    val checking = _checking.asStateFlow()
    private val _checkError = MutableStateFlow<String?>(null)
    val checkError = _checkError.asStateFlow()

    fun checkNow() = viewModelScope.launch {
        _checking.value = true; _checkError.value = null
        (c.repository.checkService(id) as? ApiResult.Failure)?.let { _checkError.value = it.failure.message }
        refresh()
        _checking.value = false
    }
}

class ContainersViewModel(private val c: AppContainer) : PollingViewModel() {
    val containers = poll(c::refreshIntervalMs) { c.repository.containers() }
    private val controller = ContainerActionController(c.repository)
    val action: StateFlow<ActionState> = controller.state

    fun request(container: ContainerOut, a: ContainerAction) = controller.request(container, a)
    fun confirm() = viewModelScope.launch { if (controller.confirm()) refresh() }
    fun dismiss() = controller.dismiss()
}

class ContainerDetailViewModel(private val c: AppContainer, private val ref: String) : PollingViewModel() {
    val containers = poll(c::refreshIntervalMs) { c.repository.containers() }
    private val controller = ContainerActionController(c.repository)
    val action: StateFlow<ActionState> = controller.state

    private val _logs = MutableStateFlow<Loadable<ContainerLogs>>(Loadable.Loading)
    val logs = _logs.asStateFlow()
    var tail = 100
        private set

    fun loadLogs(tail: Int = this.tail) = viewModelScope.launch {
        this@ContainerDetailViewModel.tail = tail
        _logs.value = Loadable.Loading
        _logs.value = when (val r = c.repository.containerLogs(ref, tail)) {
            is ApiResult.Success -> Loadable.Content(r.value, java.time.Instant.now())
            is ApiResult.Failure -> Loadable.Failed(r.failure)
        }
    }

    fun request(container: ContainerOut, a: ContainerAction) = controller.request(container, a)
    fun confirm() = viewModelScope.launch { if (controller.confirm()) refresh() }
    fun dismiss() = controller.dismiss()
}

class MetricsViewModel(private val c: AppContainer) : PollingViewModel() {
    private val range = MutableStateFlow("1h")
    val selectedRange = range.asStateFlow()
    val history = poll({ maxOf(15_000, c.refreshIntervalMs()) }) { c.repository.history(range.value) }

    fun select(r: String) { range.value = r; refresh() }
}

class AlertsViewModel(c: AppContainer, private val repo: HomeLabRepository = c.repository) : PollingViewModel() {
    val open = poll(c::refreshIntervalMs) { repo.alerts("open") }
    val history = poll({ 30_000 }) { repo.alerts("resolved") }
    val events = poll({ 30_000 }) { repo.events() }

    fun acknowledge(id: Int) = viewModelScope.launch { repo.acknowledge(id); refresh() }
}

class BackupsViewModel(c: AppContainer) : PollingViewModel() {
    val backups = poll(c::refreshIntervalMs) { c.repository.backups() }
}

class StorageViewModel(c: AppContainer) : PollingViewModel() {
    val storage = poll(c::refreshIntervalMs) { c.repository.storage() }
}

class SettingsViewModel(private val c: AppContainer) : PollingViewModel() {
    val settings = poll({ 60_000 }) { c.repository.settings() }
    val sessions = poll({ 60_000 }) { c.repository.sessions() }
    private val _notif = MutableStateFlow(c.prefs.alertNotifications)
    val notificationsEnabled = _notif.asStateFlow()
    private val _message = MutableStateFlow<String?>(null)
    val message = _message.asStateFlow()

    fun setNotifications(on: Boolean) { c.prefs.alertNotifications = on; _notif.value = on }
    fun setRefreshSeconds(s: Int) { c.prefs.refreshSeconds = s }
    val theme = c.theme
    fun setTheme(t: String) = c.setTheme(t)
    val refreshSeconds: Int get() = c.prefs.refreshSeconds

    fun revoke(id: Int) = viewModelScope.launch { c.repository.revokeSession(id); refresh() }
    fun logout() = viewModelScope.launch { c.session.logout() }
    fun changePassword(cur: String, new: String) = viewModelScope.launch {
        _message.value = when {
            new.length < 12 -> "New password must be at least 12 characters"
            else -> when (val r = c.repository.changePassword(cur, new)) {
                is ApiResult.Success -> "Password changed; other sessions were signed out"
                is ApiResult.Failure -> r.failure.message
            }
        }
    }
    fun clearMessage() { _message.value = null }
}

/** Creates ViewModels with the app container (no DI framework). */
class Factory(private val c: AppContainer, private val arg: String? = null) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T = when (modelClass) {
        AuthViewModel::class.java -> AuthViewModel(c)
        HomeViewModel::class.java -> HomeViewModel(c)
        ServicesViewModel::class.java -> ServicesViewModel(c)
        ServiceDetailViewModel::class.java -> ServiceDetailViewModel(c, arg!!.toInt())
        ContainersViewModel::class.java -> ContainersViewModel(c)
        ContainerDetailViewModel::class.java -> ContainerDetailViewModel(c, arg!!)
        MetricsViewModel::class.java -> MetricsViewModel(c)
        AlertsViewModel::class.java -> AlertsViewModel(c)
        BackupsViewModel::class.java -> BackupsViewModel(c)
        StorageViewModel::class.java -> StorageViewModel(c)
        SettingsViewModel::class.java -> SettingsViewModel(c)
        else -> error("Unknown ViewModel ${modelClass.name}")
    } as T
}
