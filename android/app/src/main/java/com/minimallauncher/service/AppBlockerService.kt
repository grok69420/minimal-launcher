package com.minimallauncher.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.app.NotificationCompat
import com.minimallauncher.MainActivity

class AppBlockerService : Service() {

    companion object {
        private const val CHANNEL_ID = "launcher_blocker"
        private const val NOTIFICATION_ID = 1
        private const val POLL_INTERVAL_MS = 400L
        private const val PREFS_NAME = "AppBlocker"
        private const val BLOCKED_APPS_KEY = "blockedApps"
        private const val BLOCKING_ENABLED_KEY = "blockingEnabled"

        private const val ACCENT = "#7C5CFF"
        private const val BG = "#0B0B10"
        private const val TEXT_DIM = "#8A8A99"
    }

    private lateinit var handler: Handler
    private lateinit var usageStatsManager: UsageStatsManager
    private lateinit var windowManager: WindowManager
    private var myPackageName: String = ""

    private var overlayView: View? = null
    private var overlayPackage: String? = null

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
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        myPackageName = packageName
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification())
        handler.removeCallbacks(pollRunnable)
        handler.post(pollRunnable)
        return START_STICKY
    }

    private fun checkAndBlock() {
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        if (!prefs.getBoolean(BLOCKING_ENABLED_KEY, true)) {
            removeOverlay()
            return
        }

        val foregroundPackage = getForegroundPackage() ?: return
        if (foregroundPackage == myPackageName) {
            removeOverlay()
            return
        }

        val blocked = prefs.getStringSet(BLOCKED_APPS_KEY, emptySet()) ?: emptySet()
        if (blocked.contains(foregroundPackage)) {
            showBlockOverlay(foregroundPackage)
        } else {
            removeOverlay()
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

    // ---- Block overlay ----------------------------------------------------

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()

    private fun labelFor(pkg: String): String {
        return try {
            val pm = packageManager
            pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
        } catch (e: Exception) {
            "This app"
        }
    }

    private fun showBlockOverlay(blockedPackage: String) {
        // Already covering this app — leave the existing overlay in place.
        if (overlayView != null && overlayPackage == blockedPackage) return
        if (overlayView != null) removeOverlay()

        val label = labelFor(blockedPackage)

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.parseColor(BG))
            setPadding(dp(40), 0, dp(40), 0)
        }

        val icon = TextView(this).apply {
            text = "🔒" // lock
            textSize = 60f
            gravity = Gravity.CENTER
        }

        val title = TextView(this).apply {
            text = "Stay Focused"
            setTextColor(Color.WHITE)
            textSize = 30f
            setTypeface(Typeface.create("sans-serif-light", Typeface.NORMAL))
            gravity = Gravity.CENTER
            setPadding(0, dp(28), 0, 0)
        }

        val subtitle = TextView(this).apply {
            text = "$label is blocked"
            setTextColor(Color.parseColor(TEXT_DIM))
            textSize = 16f
            gravity = Gravity.CENTER
            setPadding(0, dp(10), 0, 0)
        }

        val message = TextView(this).apply {
            text = "You set this app aside to protect your attention. Take a breath and get back to what matters."
            setTextColor(Color.parseColor(TEXT_DIM))
            textSize = 14f
            gravity = Gravity.CENTER
            setPadding(0, dp(16), 0, dp(40))
        }

        val button = TextView(this).apply {
            text = "Return Home"
            setTextColor(Color.WHITE)
            textSize = 16f
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER
            background = GradientDrawable().apply {
                cornerRadius = dp(16).toFloat()
                setColor(Color.parseColor(ACCENT))
            }
            setPadding(dp(48), dp(16), dp(48), dp(16))
            setOnClickListener { goHomeAndClear() }
        }

        container.addView(icon)
        container.addView(title)
        container.addView(subtitle)
        container.addView(message)
        container.addView(button)

        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            type,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.OPAQUE
        )

        try {
            windowManager.addView(container, params)
            overlayView = container
            overlayPackage = blockedPackage
        } catch (e: Exception) {
            // Overlay permission not granted — fall back to bouncing home.
            overlayView = null
            overlayPackage = null
            bringLauncherToFront()
        }
    }

    private fun removeOverlay() {
        overlayView?.let {
            try {
                windowManager.removeView(it)
            } catch (e: Exception) {
                // already detached
            }
        }
        overlayView = null
        overlayPackage = null
    }

    private fun goHomeAndClear() {
        removeOverlay()
        bringLauncherToFront()
    }

    private fun bringLauncherToFront() {
        val intent = Intent(this, MainActivity::class.java).apply {
            addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or
                    Intent.FLAG_ACTIVITY_SINGLE_TOP
            )
        }
        try {
            startActivity(intent)
        } catch (e: Exception) {
            // ignore — overlay already covers the blocked app
        }
    }

    // ---- Notification -----------------------------------------------------

    private fun buildNotification() =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Focus mode active")
            .setContentText("Distracting apps are being blocked")
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setOngoing(true)
            .setContentIntent(
                PendingIntent.getActivity(
                    this,
                    0,
                    Intent(this, MainActivity::class.java),
                    PendingIntent.FLAG_IMMUTABLE
                )
            )
            .build()

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Focus Mode",
                NotificationManager.IMPORTANCE_MIN
            ).apply {
                description = "Keeps distracting-app blocking active"
                setShowBadge(false)
            }
            getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        handler.removeCallbacks(pollRunnable)
        removeOverlay()
        super.onDestroy()
    }
}
