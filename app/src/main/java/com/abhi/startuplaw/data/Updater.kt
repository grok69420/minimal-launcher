package com.abhi.startuplaw.data

import android.content.Context
import android.util.Log
import com.abhi.startuplaw.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

data class UpdateState(
    val available: Int = 0,          // versionCode of a newer published build, 0 if none
    val lastCheck: Long = 0L,
)

/**
 * Checks whether a newer build is published. The app never downloads or installs APKs itself:
 * the update opens in the browser and Android's own installer handles it (and only accepts it
 * over this app if it is signed with the same key).
 */
class Updater(context: Context) {
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

    companion object { private const val TAG = "StartupLaw" }
}
