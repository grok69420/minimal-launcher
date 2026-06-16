package com.minimallauncher.modules

import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.provider.Settings
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableArray

class AppBlockerModule(reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    companion object {
        const val PREFS_NAME = "AppBlocker"
        const val BLOCKED_APPS_KEY = "blockedApps"
        const val BLOCKING_ENABLED_KEY = "blockingEnabled"
    }

    override fun getName(): String = "AppBlockerModule"

    private fun prefs() =
        reactApplicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

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
        promise.resolve(null)
    }

    @ReactMethod
    fun hasUsageStatsPermission(promise: Promise) {
        val appOps = reactApplicationContext
            .getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            android.os.Process.myUid(),
            reactApplicationContext.packageName
        )
        promise.resolve(mode == AppOpsManager.MODE_ALLOWED)
    }

    @ReactMethod
    fun openUsageStatsSettings(promise: Promise) {
        try {
            val intent = Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            reactApplicationContext.startActivity(intent)
            promise.resolve(null)
        } catch (e: Exception) {
            promise.reject("ERR_SETTINGS", e)
        }
    }

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
