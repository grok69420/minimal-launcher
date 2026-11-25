package com.abhi.startuplaw.data

import android.content.Context
import android.util.AtomicFile
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable
import java.io.File

@Serializable
data class Progress(
    val lessons: Set<String> = emptySet(),
    val stories: Set<String> = emptySet(),
    /** quiz id -> 1 answered right, 0 answered wrong */
    val quiz: Map<String, Int> = emptyMap(),
    /** card id -> "k" known */
    val cards: Map<String, String> = emptyMap(),
    /** newest update date the user has seen */
    val seen: String = "",
    /** glossary terms the user has looked up */
    val terms: Set<String> = emptySet(),
    /** yyyy-MM-dd -> XP earned that day (streaks and the daily goal) */
    val days: Map<String, Int> = emptyMap(),
) {
    fun toggleLesson(id: String) = copy(lessons = lessons.toggle(id))
    fun toggleStory(id: String) = copy(stories = stories.toggle(id))
    fun answer(id: String, right: Boolean) = copy(quiz = quiz + (id to if (right) 1 else 0))
    fun knowCard(id: String, known: Boolean) = copy(cards = if (known) cards + (id to "k") else cards - id)
    fun markSeen(date: String) = if (date > seen) copy(seen = date) else this
    fun lookedUp(termId: String) = if (termId in terms) this else copy(terms = terms + termId)
    fun addDayXp(day: String, xp: Int): Progress {
        if (xp <= 0) return this
        val d = days + (day to (days[day] ?: 0) + xp)
        return copy(days = if (d.size > 400) d.toSortedMap().entries.drop(d.size - 400).associate { it.key to it.value } else d)
    }

    private fun Set<String>.toggle(id: String) = if (id in this) this - id else this + id

    companion object {
        fun parse(text: String): Progress =
            runCatching { Library.json.decodeFromString(serializer(), text) }.getOrDefault(Progress())
        fun encode(p: Progress): String = Library.json.encodeToString(serializer(), p)
    }
}

/** Progress lives only on this phone (and in Android's own backup). Writes are atomic. */
class ProgressStore(context: Context, private val scope: CoroutineScope) {
    private val file = AtomicFile(File(context.filesDir, "progress.json"))
    private val writeLock = Mutex()
    private val _state = MutableStateFlow(Progress())
    val state: StateFlow<Progress> = _state.asStateFlow()

    fun load() {
        val p = runCatching { if (file.baseFile.exists()) Progress.parse(file.readFully().decodeToString()) else Progress() }
            .getOrDefault(Progress())
        _state.value = p
    }

    fun edit(change: (Progress) -> Progress) {
        _state.update(change)
        val snapshot = _state.value
        scope.launch(Dispatchers.IO) {
            writeLock.withLock {
                if (snapshot !== _state.value) return@withLock // a newer write is queued
                val out = file.startWrite()
                try {
                    out.write(Progress.encode(snapshot).encodeToByteArray()); file.finishWrite(out)
                } catch (e: Exception) { file.failWrite(out) }
            }
        }
    }
}
