package com.abhi.startuplaw.data

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.util.Log
import androidx.core.content.FileProvider
import com.abhi.startuplaw.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File

data class UpdateState(
    val available: Int = 0,          // versionCode of a newer published build, 0 if none
    val downloading: Boolean = false,
    val progress: Float = 0f,
    val error: String = "",
    val lastCheck: Long = 0L,
)

/**
 * App updates: checks the published release, downloads the APK, and installs it only if it
 * is the same app signed with the same key as the one installed (Android enforces this too).
 */
class Updater(private val context: Context) {
    private val prefs = context.getSharedPreferences("update", Context.MODE_PRIVATE)
    private val _state = MutableStateFlow(UpdateState(lastCheck = prefs.getLong("lastCheck", 0L), available = prefs.getInt("available", 0)))
    val state: StateFlow<UpdateState> = _state.asStateFlow()

    init {
        if (_state.value.available <= BuildConfig.VERSION_CODE) _state.update { it.copy(available = 0) }
    }

    suspend fun check(force: Boolean = false) = withContext(Dispatchers.IO) {
        val now = System.currentTimeMillis()
        if (!force && now - _state.value.lastCheck < 3 * 3600_000L) return@withContext
        runCatching {
            val body = Net.get(BuildConfig.RELEASE_API, 256 * 1024, "application/vnd.github+json").decodeToString()
            val notes = Library.json.parseToJsonElement(body).jsonObject["body"]?.jsonPrimitive?.content.orEmpty()
            val latest = Regex("versionCode:\\s*(\\d+)").find(notes)?.groupValues?.get(1)?.toIntOrNull() ?: 0
            Log.i(TAG, "latest build $latest (this ${BuildConfig.VERSION_CODE})")
            val avail = if (latest > BuildConfig.VERSION_CODE) latest else 0
            prefs.edit().putLong("lastCheck", now).putInt("available", avail).apply()
            _state.update { it.copy(available = avail, lastCheck = now) }
        }.onFailure { Log.w(TAG, "update check failed: ${it.message}") }
    }

    /** Downloads and verifies the update. Returns an install intent, or null with an error set. */
    suspend fun download(): Intent? = withContext(Dispatchers.IO) {
        if (_state.value.downloading) return@withContext null
        _state.update { it.copy(downloading = true, progress = 0f, error = "") }
        val dir = File(context.cacheDir, "updates").apply { mkdirs() }
        val apk = File(dir, "StartupLawLibrary.apk")
        apk.delete()
        val result = runCatching {
            Net.download(BuildConfig.APK_URL, apk, 80L * 1024 * 1024) { p -> _state.update { it.copy(progress = p) } }
            val (pkg, digests) = Signing.archiveCertDigests(context.packageManager, apk.path)
            val mine = Signing.appCertDigests(context)
            check(pkg == context.packageName) { "The download is not this app" }
            check(digests.isNotEmpty() && digests.any { it in mine }) { "The download is not signed with this app's key" }
            val uri: Uri = FileProvider.getUriForFile(context, "${context.packageName}.updates", apk)
            Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        result.exceptionOrNull()?.let { e ->
            apk.delete()
            Log.w(TAG, "update download failed: ${e.message}")
            _state.update { it.copy(error = e.message ?: "Download failed") }
        }
        _state.update { it.copy(downloading = false) }
        result.getOrNull()
    }

    fun canInstall(): Boolean = Build.VERSION.SDK_INT < 26 || context.packageManager.canRequestPackageInstalls()

    fun allowInstallsIntent(): Intent =
        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    companion object { private const val TAG = "StartupLaw" }
}
