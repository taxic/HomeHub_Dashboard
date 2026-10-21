package com.homelab.commandcentre.core.api

import com.homelab.commandcentre.core.auth.SessionManager
import com.homelab.commandcentre.core.auth.TokenStore
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Response
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit

val ApiJson = Json {
    ignoreUnknownKeys = true   // newer servers may add fields
    encodeDefaults = true      // e.g. LoginRequest.client="mobile" must be sent, not omitted
    explicitNulls = false
    coerceInputValues = true
}

/**
 * Builds the two Retrofit stacks for one backend base URL:
 *  - [authApi]: no auth interceptor (login/refresh/status);
 *  - [api]: adds the bearer token, and on 401 refreshes once through [SessionManager] and retries.
 * Request/response bodies are deliberately never logged (they contain credentials).
 */
class ApiClient(
    private val baseUrl: String,
    private val tokens: TokenStore,
    private val session: SessionManager,
    baseClient: OkHttpClient = OkHttpClient(),
) {
    private val converter = ApiJson.asConverterFactory("application/json".toMediaType())

    private val plain: OkHttpClient = baseClient.newBuilder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .callTimeout(30, TimeUnit.SECONDS)
        .followRedirects(false) // never forward credentials to a redirect target
        .followSslRedirects(false)
        .build()

    private val authed: OkHttpClient = plain.newBuilder()
        .addInterceptor(Interceptor { chain ->
            val req = chain.request()
            val token = tokens.accessToken
            chain.proceed(if (token != null) req.newBuilder().header("Authorization", "Bearer $token").build() else req)
        })
        .authenticator(Authenticator { _, response -> retryWithFreshToken(response) })
        .build()

    private fun retryWithFreshToken(response: Response): okhttp3.Request? {
        if (generateSequence(response) { it.priorResponse }.count() > 2) return null // already retried
        val used = response.request.header("Authorization")?.removePrefix("Bearer ")
        val fresh = runBlocking { session.refreshIfStale(used) } ?: return null
        return response.request.newBuilder().header("Authorization", "Bearer $fresh").build()
    }

    private fun retrofit(client: OkHttpClient) =
        Retrofit.Builder().baseUrl(baseUrl).client(client).addConverterFactory(converter).build()

    val authApi: AuthApi = retrofit(plain).create(AuthApi::class.java)
    val api: HomeLabApi = retrofit(authed).create(HomeLabApi::class.java)
}
