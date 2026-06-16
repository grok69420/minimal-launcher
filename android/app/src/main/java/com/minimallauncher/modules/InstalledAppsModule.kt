package com.minimallauncher.modules

import android.content.Intent
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod

class InstalledAppsModule(reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    override fun getName(): String = "InstalledAppsModule"

    @ReactMethod
    fun getInstalledApps(promise: Promise) {
        try {
            val pm = reactApplicationContext.packageManager
            val intent = Intent(Intent.ACTION_MAIN, null).apply {
                addCategory(Intent.CATEGORY_LAUNCHER)
            }
            val resolvedApps = pm.queryIntentActivities(intent, 0)
            val myPackage = reactApplicationContext.packageName
            val result = Arguments.createArray()

            for (info in resolvedApps) {
                val packageName = info.activityInfo.packageName
                if (packageName == myPackage) continue

                val app = Arguments.createMap().apply {
                    putString("packageName", packageName)
                    putString("appName", info.loadLabel(pm).toString())
                }
                result.pushMap(app)
            }
            promise.resolve(result)
        } catch (e: Exception) {
            promise.reject("ERR_APPS", e)
        }
    }
}
