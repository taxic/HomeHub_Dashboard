package com.homelab.commandcentre.core.auth

import com.homelab.commandcentre.core.api.AuthApi
import com.homelab.commandcentre.core.api.LoginRequest
import com.homelab.commandcentre.core.api.RefreshRequest
import com.homelab.commandcentre.core.api.SetupRequest
import com.homelab.commandcentre.core.data.ApiFailure
import com.homelab.commandcentre.core.data.ApiResult
import com.homelab.commandcentre.core.data.safeCall
import com.homelab.commandcentre.core.data.toFailure
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import retrofit2.HttpException

/** Platform-provided secure storage (Android: Keystore-backed). Tokens never go to plain prefs. */
interface TokenStore {
    var accessToken: String?
    var refreshToken: String?
    var username: String?
    fun clear()
}

class InMemoryTokenStore : TokenStore {
    override var accessToken: String? = null
    override var refreshToken: String? = null
    override var username: String? = null
    override fun clear() { accessToken = null; refreshToken = null; username = null }
}

sealed interface AuthState {
    data object Unknown : AuthState
    data class SetupRequired(val tokenRequired: Boolean) : AuthState
    data object SignedOut : AuthState
    data class SignedIn(val username: String) : AuthState
    data object Unreachable : AuthState
}

class SessionManager(
    private val authApi: () -> AuthApi,
    private val tokens: TokenStore,
    private val conflictRetryDelayMs: Long = 300,
) {
    private val _state = MutableStateFlow<AuthState>(AuthState.Unknown)
    val state: StateFlow<AuthState> = _state.asStateFlow()
    private val refreshLock = Mutex()

    val accessToken: String? get() = tokens.accessToken

    /** Decide the initial screen: setup, login, or straight in with the stored credentials. */
    suspend fun bootstrap() {
        val st = safeCall { authApi().status() }
        when (st) {
            is ApiResult.Failure -> {
                // Offline but we hold a refresh token: stay signed in, screens show "disconnected".
                _state.value = if (st.failure is ApiFailure.Offline) {
                    if (tokens.refreshToken != null) AuthState.SignedIn(tokens.username.orEmpty()) else AuthState.Unreachable
                } else AuthState.SignedOut
            }
            is ApiResult.Success -> when {
                st.value.setupRequired -> _state.value = AuthState.SetupRequired(st.value.setupTokenRequired)
                tokens.refreshToken == null -> _state.value = AuthState.SignedOut
                else -> {
                    if (refreshIfStale(tokens.accessToken, force = true) != null) {
                        _state.value = AuthState.SignedIn(tokens.username.orEmpty())
                    } else if (_state.value !is AuthState.SignedOut && tokens.refreshToken != null) {
                        _state.value = AuthState.SignedIn(tokens.username.orEmpty()) // transient failure
                    }
                }
            }
        }
    }

    suspend fun login(username: String, password: String): ApiResult<Unit> {
        val r = safeCall { authApi().login(LoginRequest(username, password, "mobile")) }
        return when (r) {
            is ApiResult.Failure -> r
            is ApiResult.Success -> {
                tokens.accessToken = r.value.accessToken
                tokens.refreshToken = r.value.refreshToken
                tokens.username = r.value.username.ifBlank { username }
                _state.value = AuthState.SignedIn(tokens.username.orEmpty())
                ApiResult.Success(Unit)
            }
        }
    }

    suspend fun setup(username: String, password: String, setupToken: String?): ApiResult<Unit> {
        val r = safeCall { authApi().setup(SetupRequest(username, password, setupToken?.ifBlank { null })) }
        if (r is ApiResult.Failure) return r
        return login(username, password)
    }

    /**
     * Single-flight refresh. If another caller already replaced [staleAccess] while we waited on the
     * lock, reuse their token instead of spending (and invalidating) the one-time refresh token.
     * Returns the usable access token, or null if the session is gone / backend unreachable.
     */
    suspend fun refreshIfStale(staleAccess: String?, force: Boolean = false): String? = refreshLock.withLock {
        val current = tokens.accessToken
        if (!force && current != null && current != staleAccess) return current
        val refresh = tokens.refreshToken ?: return null
        doRefresh(refresh)
    }

    private suspend fun doRefresh(refresh: String): String? {
        var attempts = 0
        while (true) {
            try {
                val r = authApi().refresh(RefreshRequest(refresh))
                tokens.accessToken = r.accessToken
                r.refreshToken?.let { tokens.refreshToken = it } // rotated
                return r.accessToken
            } catch (e: HttpException) {
                val body = runCatching { e.response()?.errorBody()?.string() }.getOrNull().orEmpty()
                if (e.code() == 401 && body.contains("refresh_conflict") && attempts++ < 2) {
                    delay(conflictRetryDelayMs) // another client rotated first; retry
                    continue
                }
                if (e.code() == 401) endSession()
                return null
            } catch (e: java.io.IOException) {
                return null // offline: keep credentials, do not sign out
            }
        }
    }

    suspend fun logout() {
        tokens.refreshToken?.let { rt -> runCatching { authApi().logout(RefreshRequest(rt)) } } // best effort
        endSession()
    }

    /** Forget everything (used when the user switches to a different server). */
    fun reset() {
        tokens.clear()
        _state.value = AuthState.Unknown
    }

    private fun endSession() {
        tokens.clear()
        _state.value = AuthState.SignedOut
    }
}
