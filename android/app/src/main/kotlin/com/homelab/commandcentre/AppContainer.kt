package com.homelab.commandcentre

import android.content.Context
import com.homelab.commandcentre.core.api.ApiClient
import com.homelab.commandcentre.core.auth.SessionManager
import com.homelab.commandcentre.core.data.HomeLabRepository
import com.homelab.commandcentre.data.AppPrefs
import com.homelab.commandcentre.data.SecureTokenStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Manual dependency container (small app; avoids a DI framework dependency). */
class AppContainer(context: Context) {
    val prefs = AppPrefs(context)
    val tokens = SecureTokenStore(context)

    private val _baseUrl = MutableStateFlow(prefs.baseUrl)
    /** null until the user has entered a server address. */
    val baseUrl: StateFlow<String?> = _baseUrl.asStateFlow()

    private val _theme = MutableStateFlow(prefs.theme)
    val theme: StateFlow<String> = _theme.asStateFlow()
    fun setTheme(t: String) { prefs.theme = t; _theme.value = t }

    private var client: ApiClient? = null

    val session = SessionManager(authApi = { requireClient().authApi }, tokens = tokens)
    val repository = HomeLabRepository(api = { requireClient().api })

    /** Poll interval, read on each cycle so settings changes apply without restarting screens. */
    fun refreshIntervalMs(): Long = prefs.refreshSeconds * 1000L

    init {
        _baseUrl.value?.let { client = ApiClient(it, tokens, session) }
    }

    fun setBaseUrl(url: String) {
        if (url != prefs.baseUrl) tokens.clear() // credentials belong to one server
        prefs.baseUrl = url
        client = ApiClient(url, tokens, session)
        _baseUrl.value = url
    }

    /** Switch servers: drop the address and every credential issued by the old one. */
    fun clearServer() {
        session.reset()
        prefs.baseUrl = null
        client = null
        _baseUrl.value = null
    }

    /** Probe a candidate address without saving it. */
    fun probe(url: String): ApiClient = ApiClient(url, tokens, session)

    private fun requireClient(): ApiClient = checkNotNull(client) { "Server address not configured" }
}
