package com.abhi.startuplaw

import android.app.Application
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import com.abhi.startuplaw.data.Connectivity
import com.abhi.startuplaw.data.ContentStore
import com.abhi.startuplaw.data.ProgressStore
import com.abhi.startuplaw.data.Updater
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.launch

/** App-wide singletons. Content loads from the phone first; the network only ever adds. */
class LawApp : Application() {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    lateinit var content: ContentStore; private set
    lateinit var progress: ProgressStore; private set
    lateinit var connectivity: Connectivity; private set
    lateinit var updater: Updater; private set

    override fun onCreate() {
        super.onCreate()
        content = ContentStore(this)
        progress = ProgressStore(this, scope)
        connectivity = Connectivity(this)
        updater = Updater(this)
        scope.launch(Dispatchers.IO) { progress.load() }
        scope.launch { content.load(); refresh(false) }
        // Back online -> fetch anything published while we were offline.
        scope.launch { connectivity.online.drop(1).filter { it }.collect { refresh(true) } }
        // Coming back to the app -> quietly check (rate-limited inside).
        ProcessLifecycleOwner.get().lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onStart(owner: LifecycleOwner) { scope.launch { refresh(false) } }
        })
    }

    fun refresh(force: Boolean) {
        if (!connectivity.online.value) return
        scope.launch { content.load(); content.sync(force) }
        scope.launch { updater.check(force) }
    }
}
