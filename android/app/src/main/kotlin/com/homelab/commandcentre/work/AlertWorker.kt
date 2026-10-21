package com.homelab.commandcentre.work

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.app.PendingIntent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.homelab.commandcentre.HomeLabApp
import com.homelab.commandcentre.MainActivity
import com.homelab.commandcentre.core.auth.AuthState
import com.homelab.commandcentre.core.data.ApiResult
import java.util.concurrent.TimeUnit

/**
 * Background check (WorkManager's 15-minute minimum) that raises a system notification for each
 * newly seen, unacknowledged *critical* alert. It only reads the alert feed; for instant push
 * the server's Telegram integration is the better channel. This is best-effort, not real-time.
 */
class AlertWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val app = applicationContext as HomeLabApp
        val c = app.container
        if (!c.prefs.alertNotifications || c.baseUrl.value == null) return Result.success()
        if (c.tokens.refreshToken == null) return Result.success()
        if (c.session.state.value is AuthState.Unknown) c.session.bootstrap()

        val open = when (val r = c.repository.alerts("open")) {
            is ApiResult.Success -> r.value
            is ApiResult.Failure -> return Result.retry()
        }
        val known = c.prefs.notifiedAlertIds
        val fresh = open.filter { it.severity == "critical" && it.acknowledgedAt == null && it.id.toString() !in known }
        if (canNotify(applicationContext)) {
            fresh.forEach { notify(applicationContext, it.id, it.title, it.message) }
        }
        // Remember only currently-open alerts so a re-opened alert can notify again later.
        c.prefs.notifiedAlertIds = open.map { it.id.toString() }.toSet()
        return Result.success()
    }

    companion object {
        private const val CHANNEL = "alerts"
        private const val UNIQUE = "alert-check"

        fun createChannel(ctx: Context) {
            val nm = ctx.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "Critical alerts", NotificationManager.IMPORTANCE_HIGH)
                    .apply { description = "Critical problems detected in your homelab" },
            )
        }

        fun schedule(ctx: Context) {
            val req = PeriodicWorkRequestBuilder<AlertWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(UNIQUE, ExistingPeriodicWorkPolicy.UPDATE, req)
        }

        fun cancel(ctx: Context) = WorkManager.getInstance(ctx).cancelUniqueWork(UNIQUE)

        fun canNotify(ctx: Context): Boolean =
            android.os.Build.VERSION.SDK_INT < 33 ||
                ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

        @android.annotation.SuppressLint("MissingPermission") // guarded by canNotify()
        private fun notify(ctx: Context, id: Int, title: String, text: String) {
            val open = PendingIntent.getActivity(
                ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            val n = NotificationCompat.Builder(ctx, CHANNEL)
                .setSmallIcon(android.R.drawable.stat_sys_warning)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                .setContentIntent(open)
                .setAutoCancel(true)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .build()
            NotificationManagerCompat.from(ctx).notify(id, n)
        }
    }
}
