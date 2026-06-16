package com.minimallauncher.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import com.minimallauncher.MainActivity

class AppBlockerService : Service() {

    companion object {
        private const val CHANNEL_ID = "launcher_blocker"
        private const val NOTIFICATION_ID = 1
        private const val POLL_INTERVAL_MS = 500L
        private const val PREFS_NAME = "AppBlocker"
        private const val BLOCKED_APPS_KEY = "blockedApps"
        private const val BLOCKING_ENABLED_KEY = "blockingEnabled"
    }

    private lateinit var handler: Handler
    private lateinit var usageStatsManager: UsageStatsManager
    private var myPackageName: String = ""

    private val pollRunnable = object : Runnable {
        override fun run() {
            checkAndBlock()
            handler.postDelayed(this, POLL_INTERVAL_MS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        handler = Handler(Looper.getMainLooper())
        usageStatsManager = getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        myPackageName = packageName
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Focus Mode Active")
            .setContentText("Blocking distracting apps")
            .setSmallIcon(android.R.drawable.ic_lock_silent_mode)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setOngoing(true)
            .build()

        startForeground(NOTIFICATION_ID, notification)
        handler.post(pollRunnable)
        return START_STICKY
    }

    private fun checkAndBlock() {
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        if (!prefs.getBoolean(BLOCKING_ENABLED_KEY, true)) return

        val foregroundPackage = getForegroundPackage() ?: return
        if (foregroundPackage == myPackageName) return

        val blocked = prefs.getStringSet(BLOCKED_APPS_KEY, emptySet()) ?: return
        if (blocked.contains(foregroundPackage)) {
            bringLauncherToFront()
        }
    }

    private fun getForegroundPackage(): String? {
        val now = System.currentTimeMillis()
        val events = usageStatsManager.queryEvents(now - 5000, now)
        val event = UsageEvents.Event()
        var lastPackage: String? = null
        var lastTime = 0L

        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            if (event.eventType == UsageEvents.Event.ACTIVITY_RESUMED &&
                event.timeStamp > lastTime
            ) {
                lastTime = event.timeStamp
                lastPackage = event.packageName
            }
        }
        return lastPackage
    }

    private fun bringLauncherToFront() {
        val intent = Intent(this, MainActivity::class.java).apply {
            addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or
                Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or
                Intent.FLAG_ACTIVITY_SINGLE_TOP
            )
        }
        startActivity(intent)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Focus Mode",
                NotificationManager.IMPORTANCE_MIN
            ).apply {
                description = "Keeps distracting app blocking active"
                setShowBadge(false)
            }
            getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        handler.removeCallbacks(pollRunnable)
        super.onDestroy()
    }
}
