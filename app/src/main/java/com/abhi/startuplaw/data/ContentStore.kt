package com.abhi.startuplaw.data

import android.content.Context
import android.util.AtomicFile
import android.util.Log
import com.abhi.startuplaw.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.util.Base64

enum class Source { Bundled, Saved, Synced }

data class ContentState(
    val library: Library? = null,
    val source: Source = Source.Bundled,
    val syncing: Boolean = false,
    val lastSyncAt: Long = 0L,
    val lastResult: String = "",
)

/**
 * Offline-first content. The app always opens from what is on the phone: the newest of the
 * copy shipped inside the APK and the last verified download. When online it fetches the
 * signed library; it is accepted only if the signature matches this app's signing key, it
 * parses cleanly, and its revision is newer than what we already have.
 */
class ContentStore(private val context: Context) {
    private val file = AtomicFile(File(context.filesDir, "content.json"))
    private val prefs = context.getSharedPreferences("sync", Context.MODE_PRIVATE)
    private val lock = Mutex()
    private val _state = MutableStateFlow(ContentState(lastSyncAt = prefs.getLong("lastSyncAt", 0L)))
    val state: StateFlow<ContentState> = _state.asStateFlow()

    suspend fun load() = withContext(Dispatchers.IO) {
        lock.withLock {
            if (_state.value.library != null) return@withLock
            val bundled = runCatching {
                context.assets.open("content.json").use { Library.parse(it.readBytes().decodeToString()) }
            }.getOrNull()
            val saved = runCatching {
                if (file.baseFile.exists()) Library.parse(file.readFully().decodeToString()) else null
            }.getOrNull()
            val (lib, src) = when {
                saved != null && (bundled == null || saved.rev > bundled.rev) -> saved to Source.Saved
                else -> bundled to Source.Bundled
            }
            if (saved != null && src == Source.Bundled) runCatching { file.delete() } // stale copy
            Log.i(TAG, "loaded ${src.name} rev=${lib?.rev} lessons=${lib?.lessons?.size}")
            _state.update { it.copy(library = lib, source = src) }
        }
    }

    /** Returns true if newer content was installed. Never throws. */
    suspend fun sync(force: Boolean = false): Boolean = withContext(Dispatchers.IO) {
        if (!lock.tryLock()) return@withContext false
        try {
            val now = System.currentTimeMillis()
            if (!force && now - _state.value.lastSyncAt < MIN_INTERVAL_MS) return@withContext false
            _state.update { it.copy(syncing = true) }
            val result = runCatching { fetchVerified() }
            val installed = result.getOrNull()
            val msg = when {
                result.isFailure -> "Could not reach the update server"
                installed != null -> "Updated to the latest library"
                else -> "Library is up to date"
            }
            result.exceptionOrNull()?.let { Log.w(TAG, "sync failed: ${it.javaClass.simpleName}: ${it.message}") }
            if (result.isSuccess) prefs.edit().putLong("lastSyncAt", now).apply()
            _state.update {
                it.copy(
                    syncing = false,
                    lastResult = msg,
                    lastSyncAt = if (result.isSuccess) now else it.lastSyncAt,
                    library = installed ?: it.library,
                    source = if (installed != null) Source.Synced else it.source,
                )
            }
            installed != null
        } finally {
            lock.unlock()
        }
    }

    private fun fetchVerified(): Library? {
        val current = _state.value.library
        val sigText = Net.get(BuildConfig.CONTENT_SIG_URL, 8 * 1024).decodeToString().trim()
        val sig = Base64.getDecoder().decode(sigText)
        val body = Net.get(BuildConfig.CONTENT_URL, MAX_BYTES, "application/json")
        val keys = Signing.appKeys(context)
        if (!Signing.verify(body, sig, keys)) {
            Log.w(TAG, "sync rejected: signature does not match this app's key")
            return null
        }
        val lib = Library.parse(body.decodeToString())
        if (lib == null) { Log.w(TAG, "sync rejected: content did not validate"); return null }
        if (current != null && lib.rev <= current.rev) { Log.i(TAG, "sync: up to date rev=${current.rev}"); return null }
        val out = file.startWrite()
        try { out.write(body); file.finishWrite(out) } catch (e: Exception) { file.failWrite(out); throw e }
        Log.i(TAG, "sync: installed rev=${lib.rev} lessons=${lib.lessons.size} cases=${lib.cases.size}")
        return lib
    }

    companion object {
        const val TAG = "StartupLaw"
        private const val MAX_BYTES = 5 * 1024 * 1024
        private const val MIN_INTERVAL_MS = 20 * 60 * 1000L
    }
}
