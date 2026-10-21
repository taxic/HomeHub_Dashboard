package com.homelab.commandcentre.core.api

import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/** Unauthenticated endpoints, used by the session manager (no auth interceptor => no recursion). */
interface AuthApi {
    @GET("api/v1/health") suspend fun health(): HealthOut
    @GET("api/v1/auth/status") suspend fun status(): AuthStatus
    @POST("api/v1/auth/setup") suspend fun setup(@Body body: SetupRequest): UserOut
    @POST("api/v1/auth/login") suspend fun login(@Body body: LoginRequest): TokenResponse
    @POST("api/v1/auth/refresh") suspend fun refresh(@Body body: RefreshRequest): TokenResponse
    @POST("api/v1/auth/logout") suspend fun logout(@Body body: RefreshRequest): MessageResponse
}

/** Authenticated endpoints. The same /api/v1 routes the web dashboard uses. */
interface HomeLabApi {
    @GET("api/v1/overview") suspend fun overview(): Overview
    @GET("api/v1/metrics/history") suspend fun history(@Query("range") range: String): HistoryResponse
    @GET("api/v1/storage") suspend fun storage(): StorageResponse

    @GET("api/v1/services") suspend fun services(@Query("limit") limit: Int = 200): Page<ServiceView>
    @GET("api/v1/services/{id}") suspend fun service(@Path("id") id: Int): ServiceView
    @POST("api/v1/services/{id}/check") suspend fun checkService(@Path("id") id: Int): ServiceView

    @GET("api/v1/containers") suspend fun containers(): ContainerList
    @GET("api/v1/containers/{id}") suspend fun container(@Path("id") id: String): ContainerOut
    @GET("api/v1/containers/{id}/logs") suspend fun containerLogs(@Path("id") id: String, @Query("tail") tail: Int = 100): ContainerLogs
    @POST("api/v1/containers/{id}/start") suspend fun startContainer(@Path("id") id: String): ContainerActionResult
    @POST("api/v1/containers/{id}/stop") suspend fun stopContainer(@Path("id") id: String): ContainerActionResult
    @POST("api/v1/containers/{id}/restart") suspend fun restartContainer(@Path("id") id: String): ContainerActionResult

    @GET("api/v1/alerts") suspend fun alerts(@Query("status") status: String = "open", @Query("limit") limit: Int = 100): Page<AlertOut>
    @POST("api/v1/alerts/{id}/acknowledge") suspend fun acknowledge(@Path("id") id: Int): AlertOut
    @GET("api/v1/events") suspend fun events(@Query("limit") limit: Int = 100): Page<EventOut>

    @GET("api/v1/backups") suspend fun backups(): List<BackupJob>

    @GET("api/v1/settings") suspend fun settings(): SettingsResponse
    @retrofit2.http.PATCH("api/v1/settings") suspend fun patchSettings(@Body body: SettingsPatch): SettingsResponse

    @GET("api/v1/auth/sessions") suspend fun sessions(): List<SessionOut>
    @DELETE("api/v1/auth/sessions/{id}") suspend fun revokeSession(@Path("id") id: Int): MessageResponse
    @POST("api/v1/auth/change-password") suspend fun changePassword(@Body body: ChangePasswordRequest): MessageResponse
}
