package com.minimallauncher.modules

import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableArray
import com.minimallauncher.service.AppBlockerService
import java.security.MessageDigest

class AppBlockerModule(reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    companion object {
        const val PREFS_NAME = "AppBlocker"
        const val BLOCKED_APPS_KEY = "blockedApps"
        const val BLOCKING_ENABLED_KEY = "blockingEnabled"
        const val PIN_HASH_KEY = "pinHash"
    }

    override fun getName(): String = "AppBlockerModule"

    private fun prefs() =
        reactApplicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    // Prefer launching from the current activity; fall back to the app context
    // with NEW_TASK so settings screens still open if no activity is attached.
    private fun launchIntent(intent: Intent) {
        val activity = currentActivity
        if (activity != null) {
            activity.startActivity(intent)
        } else {
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            reactApplicationContext.startActivity(intent)
        }
    }

    // ---- Blocklist --------------------------------------------------------

    @ReactMethod
    fun getBlockedApps(promise: Promise) {
        val blocked = prefs().getStringSet(BLOCKED_APPS_KEY, emptySet()) ?: emptySet()
        val arr = Arguments.createArray()
        blocked.forEach { arr.pushString(it) }
        promise.resolve(arr)
    }

    @ReactMethod
    fun setBlockedApps(packages: ReadableArray, promise: Promise) {
        val toBlock = mutableSetOf<String>()
        for (i in 0 until packages.size()) {
            toBlock.add(packages.getString(i))
        }
        prefs().edit().putStringSet(BLOCKED_APPS_KEY, toBlock).apply()
        promise.resolve(null)
    }

    @ReactMethod
    fun isBlockingEnabled(promise: Promise) {
        promise.resolve(prefs().getBoolean(BLOCKING_ENABLED_KEY, true))
    }

    @ReactMethod
    fun setBlockingEnabled(enabled: Boolean, promise: Promise) {
        prefs().edit().putBoolean(BLOCKING_ENABLED_KEY, enabled).apply()
        if (enabled) startService()
        promise.resolve(null)
    }

    // ---- Service control --------------------------------------------------

    private fun startService() {
        val intent = Intent(reactApplicationContext, AppBlockerService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            reactApplicationContext.startForegroundService(intent)
        } else {
            reactApplicationContext.startService(intent)
        }
    }

    @ReactMethod
    fun startBlockerService(promise: Promise) {
        try {
            startService()
            promise.resolve(true)
        } catch (e: Exception) {
            promise.reject("ERR_SERVICE", e)
        }
    }

    // ---- Permission: Usage Access ----------------------------------------

    private fun usageStatsGranted(): Boolean {
        val appOps = reactApplicationContext
            .getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            android.os.Process.myUid(),
            reactApplicationContext.packageName
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }

    @ReactMethod
    fun hasUsageStatsPermission(promise: Promise) {
        promise.resolve(usageStatsGranted())
    }

    @ReactMethod
    fun openUsageStatsSettings(promise: Promise) {
        try {
            launchIntent(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
            promise.resolve(null)
        } catch (e: Exception) {
            promise.reject("ERR_SETTINGS", e)
        }
    }

    // ---- Permission: Display over other apps (overlay) -------------------

    private fun overlayGranted(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(reactApplicationContext)
        } else {
            true
        }
    }

    @ReactMethod
    fun hasOverlayPermission(promise: Promise) {
        promise.resolve(overlayGranted())
    }

    @ReactMethod
    fun openOverlaySettings(promise: Promise) {
        try {
            val intent = Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:${reactApplicationContext.packageName}")
            )
            launchIntent(intent)
            promise.resolve(null)
        } catch (e: Exception) {
            promise.reject("ERR_SETTINGS", e)
        }
    }

    // ---- Permission: Notifications (Android 13+) -------------------------

    private fun notificationsGranted(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(
                reactApplicationContext,
                android.Manifest.permission.POST_NOTIFICATIONS
            ) == android.content.pm.PackageManager.PERMISSION_GRANTED
        } else {
            true
        }
    }

    @ReactMethod
    fun hasNotificationPermission(promise: Promise) {
        promise.resolve(notificationsGranted())
    }

    @ReactMethod
    fun requestNotificationPermission(promise: Promise) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val activity = currentActivity
                if (activity != null) {
                    ActivityCompat.requestPermissions(
                        activity,
                        arrayOf(android.Manifest.permission.POST_NOTIFICATIONS),
                        1001
                    )
                } else {
                    // No activity — open the app's notification settings instead.
                    val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(Settings.EXTRA_APP_PACKAGE, reactApplicationContext.packageName)
                    launchIntent(intent)
                }
            }
            promise.resolve(null)
        } catch (e: Exception) {
            promise.reject("ERR_NOTIF", e)
        }
    }

    // ---- Permission: Battery optimization exemption ----------------------

    private fun batteryOptIgnored(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val pm = reactApplicationContext.getSystemService(Context.POWER_SERVICE) as PowerManager
            pm.isIgnoringBatteryOptimizations(reactApplicationContext.packageName)
        } else {
            true
        }
    }

    @ReactMethod
    fun isBatteryOptimizationIgnored(promise: Promise) {
        promise.resolve(batteryOptIgnored())
    }

    @ReactMethod
    @android.annotation.SuppressLint("BatteryLife")
    fun requestIgnoreBatteryOptimization(promise: Promise) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                val intent = Intent(
                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.parse("package:${reactApplicationContext.packageName}")
                )
                launchIntent(intent)
            }
            promise.resolve(null)
        } catch (e: Exception) {
            promise.reject("ERR_BATTERY", e)
        }
    }

    // ---- Permission: Default launcher ------------------------------------

    private fun defaultLauncherGranted(): Boolean {
        val intent = Intent(Intent.ACTION_MAIN).apply { addCategory(Intent.CATEGORY_HOME) }
        val res = reactApplicationContext.packageManager
            .resolveActivity(intent, android.content.pm.PackageManager.MATCH_DEFAULT_ONLY)
        return res?.activityInfo?.packageName == reactApplicationContext.packageName
    }

    @ReactMethod
    fun isDefaultLauncher(promise: Promise) {
        promise.resolve(defaultLauncherGranted())
    }

    @ReactMethod
    fun openHomeSettings(promise: Promise) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                launchIntent(Intent(Settings.ACTION_HOME_SETTINGS))
            } else {
                launchIntent(Intent(Settings.ACTION_SETTINGS))
            }
            promise.resolve(null)
        } catch (e: Exception) {
            promise.reject("ERR_SETTINGS", e)
        }
    }

    // ---- Aggregate permission snapshot -----------------------------------

    @ReactMethod
    fun getPermissionStatus(promise: Promise) {
        val map = Arguments.createMap().apply {
            putBoolean("usageStats", usageStatsGranted())
            putBoolean("overlay", overlayGranted())
            putBoolean("notifications", notificationsGranted())
            putBoolean("batteryOptIgnored", batteryOptIgnored())
            putBoolean("defaultLauncher", defaultLauncherGranted())
        }
        promise.resolve(map)
    }

    // ---- Security PIN -----------------------------------------------------

    private fun sha256(input: String): String {
        val bytes = MessageDigest.getInstance("SHA-256").digest(input.toByteArray())
        return bytes.joinToString("") { "%02x".format(it) }
    }

    @ReactMethod
    fun hasPin(promise: Promise) {
        promise.resolve(!prefs().getString(PIN_HASH_KEY, null).isNullOrEmpty())
    }

    @ReactMethod
    fun setPin(pin: String, promise: Promise) {
        prefs().edit().putString(PIN_HASH_KEY, sha256(pin)).apply()
        promise.resolve(true)
    }

    @ReactMethod
    fun verifyPin(pin: String, promise: Promise) {
        val stored = prefs().getString(PIN_HASH_KEY, null)
        promise.resolve(stored != null && stored == sha256(pin))
    }

    @ReactMethod
    fun clearPin(promise: Promise) {
        prefs().edit().remove(PIN_HASH_KEY).apply()
        promise.resolve(true)
    }

    // ---- Launch an app ----------------------------------------------------

    @ReactMethod
    fun launchApp(packageName: String, promise: Promise) {
        try {
            val intent = reactApplicationContext.packageManager
                .getLaunchIntentForPackage(packageName)
                ?: return promise.reject("ERR_LAUNCH", "App not found: $packageName")
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            reactApplicationContext.startActivity(intent)
            promise.resolve(null)
        } catch (e: Exception) {
            promise.reject("ERR_LAUNCH", e)
        }
    }
}
