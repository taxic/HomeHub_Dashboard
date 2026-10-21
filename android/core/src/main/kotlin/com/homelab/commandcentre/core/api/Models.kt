package com.homelab.commandcentre.core.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Wire models. Field names mirror the backend's OpenAPI (docs/openapi.json). Everything optional
// on the server is nullable here: null means "unavailable", never "zero".

@Serializable data class ApiErrorEnvelope(val error: ApiErrorBody)

@Serializable
data class ApiErrorBody(
    val code: String = "error",
    val message: String = "",
    val details: List<FieldError>? = null,
    @SerialName("request_id") val requestId: String? = null,
)

@Serializable data class FieldError(val field: String = "", val message: String = "")

@Serializable data class Page<T>(val items: List<T>, val total: Int, val limit: Int, val offset: Int)

@Serializable data class MessageResponse(val message: String)

// ---- auth ----
@Serializable data class AuthStatus(
    @SerialName("setup_required") val setupRequired: Boolean,
    @SerialName("setup_token_required") val setupTokenRequired: Boolean = false,
)

@Serializable data class SetupRequest(val username: String, val password: String, @SerialName("setup_token") val setupToken: String? = null)
@Serializable data class LoginRequest(val username: String, val password: String, val client: String = "mobile")
@Serializable data class RefreshRequest(@SerialName("refresh_token") val refreshToken: String)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("expires_in") val expiresIn: Int,
    @SerialName("refresh_token") val refreshToken: String? = null,
    val username: String = "",
)

@Serializable data class UserOut(val id: Int, val username: String)
@Serializable data class ChangePasswordRequest(
    @SerialName("current_password") val currentPassword: String,
    @SerialName("new_password") val newPassword: String,
)

@Serializable
data class SessionOut(
    val id: Int,
    val client: String,
    @SerialName("user_agent") val userAgent: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("last_used_at") val lastUsedAt: String? = null,
    val current: Boolean = false,
)

// ---- health ----
@Serializable data class HealthOut(val status: String, val version: String, val time: String, @SerialName("public_url") val publicUrl: String? = null)

// ---- metrics ----
@Serializable data class MemoryMetrics(
    @SerialName("total_bytes") val totalBytes: Long,
    @SerialName("used_bytes") val usedBytes: Long,
    @SerialName("available_bytes") val availableBytes: Long,
    val percent: Double,
)

@Serializable data class SwapMetrics(
    @SerialName("total_bytes") val totalBytes: Long,
    @SerialName("used_bytes") val usedBytes: Long,
    val percent: Double,
)

@Serializable data class NetworkMetrics(
    @SerialName("rx_bps") val rxBps: Double? = null,
    @SerialName("tx_bps") val txBps: Double? = null,
    @SerialName("rx_total_bytes") val rxTotalBytes: Long = 0,
    @SerialName("tx_total_bytes") val txTotalBytes: Long = 0,
    val interfaces: List<String> = emptyList(),
)

@Serializable data class DiskIo(
    @SerialName("read_bps") val readBps: Double? = null,
    @SerialName("write_bps") val writeBps: Double? = null,
)

@Serializable
data class HostMetrics(
    @SerialName("sampled_at") val sampledAt: String,
    @SerialName("cpu_percent") val cpuPercent: Double? = null,
    @SerialName("cpu_count") val cpuCount: Int? = null,
    @SerialName("load_avg") val loadAvg: List<Double>? = null,
    val memory: MemoryMetrics? = null,
    val swap: SwapMetrics? = null,
    @SerialName("uptime_seconds") val uptimeSeconds: Double? = null,
    @SerialName("temperature_c") val temperatureC: Double? = null,
    val network: NetworkMetrics? = null,
    @SerialName("disk_io") val diskIo: DiskIo? = null,
)

@Serializable
data class VolumeStatus(
    val id: Int? = null,
    val name: String,
    val path: String,
    val kind: String,
    val required: Boolean = true,
    val state: String,
    val message: String? = null,
    @SerialName("total_bytes") val totalBytes: Long? = null,
    @SerialName("used_bytes") val usedBytes: Long? = null,
    @SerialName("free_bytes") val freeBytes: Long? = null,
    val percent: Double? = null,
    @SerialName("checked_at") val checkedAt: String,
)

@Serializable data class StorageResponse(
    val root: VolumeStatus? = null,
    val volumes: List<VolumeStatus> = emptyList(),
    @SerialName("disk_io") val diskIo: DiskIo? = null,
    @SerialName("sampled_at") val sampledAt: String? = null,
)

@Serializable
data class HistoryPoint(
    val ts: String,
    @SerialName("cpu_percent") val cpuPercent: Double? = null,
    @SerialName("mem_percent") val memPercent: Double? = null,
    @SerialName("swap_percent") val swapPercent: Double? = null,
    val load1: Double? = null,
    @SerialName("disk_root_percent") val diskRootPercent: Double? = null,
    @SerialName("storage_max_percent") val storageMaxPercent: Double? = null,
    @SerialName("net_rx_bps") val netRxBps: Double? = null,
    @SerialName("net_tx_bps") val netTxBps: Double? = null,
    @SerialName("temp_c") val tempC: Double? = null,
)

@Serializable data class HistoryResponse(
    val range: String,
    val start: String,
    val end: String,
    @SerialName("bucket_seconds") val bucketSeconds: Int,
    val points: List<HistoryPoint>,
)

// ---- overview ----
@Serializable data class ContainerCounts(
    val available: Boolean,
    val running: Int = 0, val stopped: Int = 0, val unhealthy: Int = 0, val total: Int = 0,
    val error: String? = null,
)

@Serializable data class ServiceCounts(
    val healthy: Int = 0, val unhealthy: Int = 0, val unknown: Int = 0,
    val degraded: Int = 0, val disabled: Int = 0, val total: Int = 0,
)

@Serializable data class BackupCounts(val total: Int = 0, val ok: Int = 0, val problem: Int = 0)

@Serializable data class AlertCounts(
    val open: Int = 0, val critical: Int = 0, val warning: Int = 0, val unacknowledged: Int = 0,
)

@Serializable
data class AlertOut(
    val id: Int,
    val key: String,
    val type: String,
    val severity: String,
    val status: String,
    val title: String,
    val message: String,
    val subject: String? = null,
    val occurrences: Int = 1,
    @SerialName("first_seen_at") val firstSeenAt: String,
    @SerialName("last_seen_at") val lastSeenAt: String,
    @SerialName("resolved_at") val resolvedAt: String? = null,
    @SerialName("acknowledged_at") val acknowledgedAt: String? = null,
    @SerialName("acknowledged_by") val acknowledgedBy: String? = null,
)

@Serializable
data class EventOut(
    val id: Int,
    val ts: String,
    val type: String,
    val severity: String,
    val message: String,
    val actor: String? = null,
)

@Serializable
data class Overview(
    val status: String,
    @SerialName("status_reason") val statusReason: String? = null,
    @SerialName("generated_at") val generatedAt: String,
    @SerialName("last_update") val lastUpdate: String? = null,
    val stale: Boolean = false,
    @SerialName("refresh_seconds") val refreshSeconds: Int = 10,
    val host: HostMetrics? = null,
    @SerialName("root_volume") val rootVolume: VolumeStatus? = null,
    val volumes: List<VolumeStatus> = emptyList(),
    val containers: ContainerCounts,
    val services: ServiceCounts,
    val backups: BackupCounts,
    val alerts: AlertCounts,
    @SerialName("recent_alerts") val recentAlerts: List<AlertOut> = emptyList(),
    @SerialName("recent_events") val recentEvents: List<EventOut> = emptyList(),
)

// ---- services ----
@Serializable
data class ServiceView(
    val id: Int,
    val name: String,
    val description: String? = null,
    val category: String = "other",
    @SerialName("container_name") val containerName: String? = null,
    val url: String? = null,
    @SerialName("expected_status") val expectedStatus: String = "200-399",
    @SerialName("verify_tls") val verifyTls: Boolean = true,
    @SerialName("interval_seconds") val intervalSeconds: Int = 60,
    @SerialName("timeout_seconds") val timeoutSeconds: Double = 5.0,
    val enabled: Boolean = true,
    @SerialName("allow_control") val allowControl: Boolean = false,
    @SerialName("allowed_actions") val allowedActions: List<String> = emptyList(),
    @SerialName("health_status") val healthStatus: String = "unknown",
    @SerialName("last_checked_at") val lastCheckedAt: String? = null,
    @SerialName("last_success_at") val lastSuccessAt: String? = null,
    @SerialName("last_response_ms") val lastResponseMs: Double? = null,
    @SerialName("last_status_code") val lastStatusCode: Int? = null,
    @SerialName("last_error") val lastError: String? = null,
    @SerialName("consecutive_failures") val consecutiveFailures: Int = 0,
    @SerialName("container_state") val containerState: String? = null,
    @SerialName("container_health") val containerHealth: String? = null,
    @SerialName("effective_status") val effectiveStatus: String = "unknown",
    @SerialName("effective_reason") val effectiveReason: String? = null,
)

// ---- containers ----
@Serializable data class ContainerStats(
    @SerialName("cpu_percent") val cpuPercent: Double? = null,
    @SerialName("memory_bytes") val memoryBytes: Long? = null,
    @SerialName("memory_limit_bytes") val memoryLimitBytes: Long? = null,
    @SerialName("memory_percent") val memoryPercent: Double? = null,
)

@Serializable
data class ContainerOut(
    val id: String,
    @SerialName("short_id") val shortId: String,
    val name: String,
    val image: String,
    val state: String,
    @SerialName("status_text") val statusText: String = "",
    val health: String = "none",
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("started_at") val startedAt: String? = null,
    @SerialName("restart_count") val restartCount: Int? = null,
    val stats: ContainerStats? = null,
    @SerialName("service_id") val serviceId: Int? = null,
    @SerialName("service_name") val serviceName: String? = null,
    @SerialName("can_control") val canControl: Boolean = false,
    @SerialName("allowed_actions") val allowedActions: List<String> = emptyList(),
    val protected: Boolean = false,
)

@Serializable data class ContainerList(
    @SerialName("docker_available") val dockerAvailable: Boolean,
    @SerialName("docker_error") val dockerError: String? = null,
    @SerialName("refreshed_at") val refreshedAt: String? = null,
    val containers: List<ContainerOut> = emptyList(),
)

@Serializable data class ContainerLogs(val id: String, val name: String, val lines: List<String>, val truncated: Boolean = false, val tail: Int = 0)

@Serializable data class ContainerActionResult(
    val id: String, val name: String, val action: String, val ok: Boolean, val state: String, val message: String,
)

// ---- backups ----
@Serializable
data class BackupJob(
    val id: Int,
    val name: String,
    val description: String? = null,
    @SerialName("schedule_text") val scheduleText: String? = null,
    @SerialName("max_age_hours") val maxAgeHours: Int = 36,
    val enabled: Boolean = true,
    @SerialName("last_attempt_at") val lastAttemptAt: String? = null,
    @SerialName("last_attempt_status") val lastAttemptStatus: String? = null,
    @SerialName("last_success_at") val lastSuccessAt: String? = null,
    @SerialName("last_restore_test_at") val lastRestoreTestAt: String? = null,
    @SerialName("last_restore_test_ok") val lastRestoreTestOk: Boolean? = null,
    val state: String = "never_run",
    @SerialName("state_reason") val stateReason: String? = null,
    @SerialName("age_hours") val ageHours: Double? = null,
)

// ---- settings ----
@Serializable
data class AppSettings(
    @SerialName("dashboard_refresh_seconds") val dashboardRefreshSeconds: Int = 10,
    @SerialName("cpu_warn_percent") val cpuWarnPercent: Double = 85.0,
    @SerialName("cpu_crit_percent") val cpuCritPercent: Double = 95.0,
    @SerialName("mem_warn_percent") val memWarnPercent: Double = 85.0,
    @SerialName("mem_crit_percent") val memCritPercent: Double = 95.0,
    @SerialName("storage_warn_percent") val storageWarnPercent: Double = 85.0,
    @SerialName("storage_crit_percent") val storageCritPercent: Double = 95.0,
    @SerialName("telegram_enabled") val telegramEnabled: Boolean = false,
)

@Serializable
data class SettingsResponse(
    val settings: AppSettings,
    @SerialName("telegram_configured") val telegramConfigured: Boolean = false,
    @SerialName("docker_control_enabled") val dockerControlEnabled: Boolean = false,
    val version: String = "",
    @SerialName("public_url") val publicUrl: String? = null,
)

@Serializable data class SettingsPatch(@SerialName("dashboard_refresh_seconds") val dashboardRefreshSeconds: Int? = null)
