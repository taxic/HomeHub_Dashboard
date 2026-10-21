package com.homelab.commandcentre.core

import com.homelab.commandcentre.core.api.ApiClient
import com.homelab.commandcentre.core.auth.AuthState
import com.homelab.commandcentre.core.auth.InMemoryTokenStore
import com.homelab.commandcentre.core.auth.SessionManager
import com.homelab.commandcentre.core.data.ApiFailure
import com.homelab.commandcentre.core.data.ApiResult
import com.homelab.commandcentre.core.data.ContainerAction
import com.homelab.commandcentre.core.data.HomeLabRepository
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

class NetworkTest {
    private lateinit var server: MockWebServer
    private lateinit var tokens: InMemoryTokenStore
    private lateinit var session: SessionManager
    private lateinit var client: ApiClient
    private lateinit var repo: HomeLabRepository

    private fun json(code: Int, body: String) = MockResponse().setResponseCode(code).setHeader("Content-Type", "application/json").setBody(body)
    private fun err(code: Int, c: String, m: String) = json(code, """{"error":{"code":"$c","message":"$m"}}""")

    @BeforeTest fun setUp() {
        server = MockWebServer().also { it.start() }
        tokens = InMemoryTokenStore()
        lateinit var holder: ApiClient
        session = SessionManager({ holder.authApi }, tokens, conflictRetryDelayMs = 1)
        client = ApiClient(server.url("/").toString(), tokens, session).also { holder = it }
        repo = HomeLabRepository { client.api }
    }

    @AfterTest fun tearDown() { server.shutdown() }

    private fun signedIn(access: String = "old", refresh: String = "r1") { tokens.accessToken = access; tokens.refreshToken = refresh; tokens.username = "admin" }

    @Test fun sendsBearerTokenAndParsesRealOverview() = runBlocking<Unit> {
        signedIn("tok")
        server.enqueue(json(200, Fixtures.text("overview")))
        val r = repo.overview()
        assertIs<ApiResult.Success<*>>(r)
        assertEquals("Bearer tok", server.takeRequest().getHeader("Authorization"))
    }

    @Test fun on401RefreshesOnceThenRetriesWithRotatedToken() = runBlocking<Unit> {
        signedIn("expired", "r1")
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse = when {
                request.path!!.endsWith("/auth/refresh") -> json(200, """{"access_token":"new","expires_in":900,"refresh_token":"r2","username":"admin"}""")
                request.getHeader("Authorization") == "Bearer new" -> json(200, Fixtures.text("overview"))
                else -> err(401, "unauthorized", "expired")
            }
        }
        assertIs<ApiResult.Success<*>>(repo.overview())
        assertEquals("new", tokens.accessToken); assertEquals("r2", tokens.refreshToken)
        assertEquals(listOf("/api/v1/overview", "/api/v1/auth/refresh", "/api/v1/overview"), (1..3).map { server.takeRequest().path })
    }

    @Test fun concurrentExpiredRequestsShareOneRefresh() = runBlocking<Unit> {
        signedIn("expired", "r1")
        val refreshes = AtomicInteger()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse = when {
                request.path!!.endsWith("/auth/refresh") -> { refreshes.incrementAndGet(); Thread.sleep(100); json(200, """{"access_token":"new","expires_in":900,"refresh_token":"r2","username":"admin"}""") }
                request.getHeader("Authorization") == "Bearer new" -> json(200, Fixtures.text("services"))
                else -> err(401, "unauthorized", "expired")
            }
        }
        val results = (1..4).map { async(kotlinx.coroutines.Dispatchers.IO) { repo.services() } }.awaitAll()
        assertTrue(results.all { it is ApiResult.Success })
        assertEquals(1, refreshes.get(), "refresh tokens are single-use; exactly one refresh may be spent")
    }

    @Test fun failedRefreshSignsOutAndSurfacesUnauthorized() = runBlocking<Unit> {
        signedIn("expired", "revoked")
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest) =
                if (request.path!!.endsWith("/auth/refresh")) err(401, "invalid_refresh_token", "Invalid refresh token") else err(401, "unauthorized", "expired")
        }
        val r = repo.overview()
        assertIs<ApiResult.Failure>(r); assertIs<ApiFailure.Unauthorized>(r.failure)
        assertNull(tokens.refreshToken, "credentials are wiped when the server rejects the refresh token")
        assertEquals(AuthState.SignedOut, session.state.value)
    }

    @Test fun refreshWhileOfflineKeepsCredentials() = runBlocking<Unit> {
        signedIn("expired", "r1")
        server.shutdown()
        val r = repo.overview()
        assertIs<ApiResult.Failure>(r); assertIs<ApiFailure.Offline>(r.failure)
        assertEquals("r1", tokens.refreshToken) // transient outage must not log the user out
    }

    @Test fun raceOnRefreshRetriesInsteadOfLoggingOut() = runBlocking<Unit> {
        signedIn("expired", "r1")
        val n = AtomicInteger()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse = when {
                request.path!!.endsWith("/auth/refresh") ->
                    if (n.getAndIncrement() == 0) err(401, "refresh_conflict", "retry") else json(200, """{"access_token":"new","expires_in":900,"refresh_token":"r2","username":"admin"}""")
                request.getHeader("Authorization") == "Bearer new" -> json(200, Fixtures.text("services"))
                else -> err(401, "unauthorized", "expired")
            }
        }
        assertIs<ApiResult.Success<*>>(repo.services())
        assertEquals("r2", tokens.refreshToken)
    }

    @Test fun httpErrorsMapToDistinctFailures() = runBlocking<Unit> {
        signedIn("tok")
        server.enqueue(err(403, "not_permitted", "This container is not permitted for remote control."))
        (repo.containerAction("abc", ContainerAction.Restart) as ApiResult.Failure).also {
            val f = assertIs<ApiFailure.Forbidden>(it.failure)
            assertEquals("not_permitted", f.code); assertTrue(f.message.contains("not permitted"))
        }
        server.enqueue(err(404, "not_found", "gone")); assertIs<ApiFailure.NotFound>((repo.service(9) as ApiResult.Failure).failure)
        server.enqueue(err(409, "conflict", "busy")); assertIs<ApiFailure.Conflict>((repo.containerAction("a", ContainerAction.Stop) as ApiResult.Failure).failure)
        server.enqueue(err(503, "docker_unavailable", "Docker down")); assertIs<ApiFailure.Unavailable>((repo.containers() as ApiResult.Failure).failure)
        server.enqueue(err(500, "internal_error", "boom")); assertIs<ApiFailure.Server>((repo.backups() as ApiResult.Failure).failure)
        server.enqueue(err(429, "rate_limited", "slow down")); assertIs<ApiFailure.RateLimited>((repo.settings() as ApiResult.Failure).failure)
        server.enqueue(MockResponse().setResponseCode(502).setBody("<html>bad gateway</html>")) // non-JSON body from a proxy
        assertIs<ApiFailure.Server>((repo.events() as ApiResult.Failure).failure)
    }

    @Test fun validationErrorsCarryFieldDetails() = runBlocking<Unit> {
        signedIn("tok")
        server.enqueue(json(422, Fixtures.text("error_validation")))
        val f = (repo.checkService(1) as ApiResult.Failure).failure
        val v = assertIs<ApiFailure.Validation>(f)
        assertEquals("url", v.fields.single().field)
    }

    @Test fun containerActionsHitOnlyTheThreeWhitelistedEndpoints() = runBlocking<Unit> {
        signedIn("tok")
        repeat(3) { server.enqueue(json(200, Fixtures.text("action"))) }
        ContainerAction.entries.forEach { repo.containerAction("abc123", it) }
        val paths = (1..3).map { server.takeRequest().let { r -> "${r.method} ${r.path}" } }
        assertEquals(listOf("POST /api/v1/containers/abc123/start", "POST /api/v1/containers/abc123/stop", "POST /api/v1/containers/abc123/restart"), paths)
    }

    @Test fun loginStoresTokensAndNeverLogsInBody() = runBlocking<Unit> {
        server.enqueue(json(200, Fixtures.text("login")))
        val r = session.login("admin", "pw")
        assertIs<ApiResult.Success<*>>(r)
        assertEquals("ACCESS-TOKEN-PLACEHOLDER", tokens.accessToken); assertEquals("REFRESH-TOKEN-PLACEHOLDER", tokens.refreshToken)
        assertEquals(AuthState.SignedIn("admin"), session.state.value)
        val req = server.takeRequest()
        assertTrue(req.body.readUtf8().contains("\"client\":\"mobile\""))
    }

    @Test fun badLoginDoesNotStoreAnything() = runBlocking<Unit> {
        server.enqueue(err(401, "invalid_credentials", "Invalid username or password"))
        val r = session.login("admin", "nope")
        assertIs<ApiFailure.Unauthorized>((r as ApiResult.Failure).failure)
        assertNull(tokens.accessToken)
    }

    @Test fun bootstrapRoutesToSetupLoginOrApp() = runBlocking<Unit> {
        server.enqueue(json(200, """{"setup_required":true,"setup_token_required":true}"""))
        session.bootstrap(); assertEquals(AuthState.SetupRequired(true), session.state.value)

        server.enqueue(json(200, """{"setup_required":false}"""))
        session.bootstrap(); assertEquals(AuthState.SignedOut, session.state.value) // no stored refresh token

        signedIn("old", "r1")
        server.enqueue(json(200, """{"setup_required":false}"""))
        server.enqueue(json(200, """{"access_token":"fresh","expires_in":900,"refresh_token":"r2","username":"admin"}"""))
        session.bootstrap(); assertEquals(AuthState.SignedIn("admin"), session.state.value)
    }

    @Test fun offlineStartWithStoredSessionStaysSignedInButWithoutSessionShowsUnreachable() = runBlocking<Unit> {
        server.shutdown()
        session.bootstrap(); assertEquals(AuthState.Unreachable, session.state.value)
        signedIn("old", "r1")
        session.bootstrap(); assertEquals(AuthState.SignedIn("admin"), session.state.value)
        assertEquals("r1", tokens.refreshToken)
    }

    @Test fun logoutClearsTokensEvenIfServerUnreachable() = runBlocking<Unit> {
        signedIn()
        server.shutdown()
        session.logout()
        assertNull(tokens.accessToken); assertNull(tokens.refreshToken)
        assertEquals(AuthState.SignedOut, session.state.value)
    }

    @Test fun redirectsAreNotFollowedSoTokensCannotLeak() = runBlocking<Unit> {
        signedIn("tok")
        server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "http://evil.example/"))
        val r = repo.overview()
        assertTrue(r is ApiResult.Failure)
        assertEquals(1, server.requestCount)
        assertFalse(server.requestCount > 1)
    }
}
