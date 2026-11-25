package com.abhi.startuplaw

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.abhi.startuplaw.data.Card
import com.abhi.startuplaw.data.ContentState
import com.abhi.startuplaw.data.Game
import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.data.Progress
import com.abhi.startuplaw.data.QuizQ
import com.abhi.startuplaw.data.Reward
import com.abhi.startuplaw.data.Term
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import com.abhi.startuplaw.data.SearchIndex
import com.abhi.startuplaw.data.Study
import com.abhi.startuplaw.data.UpdateState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class QuizSession(
    val module: String? = null,
    val order: List<String> = emptyList(),
    val index: Int = 0,
    val picked: Int? = null,
    val right: Int = 0,
    val answered: Int = 0,
) { val done get() = order.isNotEmpty() && index >= order.size }

/** A tapped word: its glossary entry if there is one, plus the sentence it came from. */
data class Lookup(val word: String, val term: Term?, val context: String)

data class CardSession(val unknownOnly: Boolean = false, val index: Int = 0, val flipped: Boolean = false)

class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val la = app as LawApp

    val content: StateFlow<ContentState> = la.content.state
    val progress: StateFlow<Progress> = la.progress.state
    val online: StateFlow<Boolean> = la.connectivity.online
    val update: StateFlow<UpdateState> = la.updater.state

    val library: StateFlow<Library?> = content.map { it.library }
        .stateIn(viewModelScope, SharingStarted.Eagerly, content.value.library)

    private var indexFor: Library? = null
    private var indexCache: SearchIndex? = null
    fun index(lib: Library): SearchIndex = indexCache?.takeIf { indexFor === lib } ?: SearchIndex(lib).also { indexCache = it; indexFor = lib }

    private var deckFor: Library? = null
    private var deckCache: List<Card> = emptyList()
    fun deck(lib: Library): List<Card> = if (deckFor === lib) deckCache else Study.deck(lib).also { deckCache = it; deckFor = lib }

    // ---- progress, XP and celebrations ----
    private val _rewards = MutableSharedFlow<Reward>(extraBufferCapacity = 8)
    val rewards: SharedFlow<Reward> = _rewards.asSharedFlow()

    /** Applies a progress change, logs XP for today's streak/goal, and emits any reward. */
    private fun award(change: (Progress) -> Progress) {
        val lib = library.value ?: return la.progress.edit(change)
        val before = progress.value
        la.progress.edit { p ->
            val next = change(p)
            next.addDayXp(Game.today(), Game.xp(next, lib) - Game.xp(p, lib))
        }
        Game.reward(before, progress.value, lib)?.let { _rewards.tryEmit(it) }
    }

    fun toggleLesson(id: String) = award { it.toggleLesson(id) }
    fun toggleStory(id: String) = award { it.toggleStory(id) }

    // ---- tap-a-word ----
    private val _lookup = MutableStateFlow<Lookup?>(null)
    val lookup: StateFlow<Lookup?> = _lookup.asStateFlow()
    fun openLookup(word: String, term: Term?, context: String) {
        _lookup.value = Lookup(word, term, context)
        if (term != null) award { it.lookedUp(term.id) }
    }
    fun closeLookup() { _lookup.value = null }

    /** One-question check at the end of a lesson. Returns true if right. */
    fun quickCheck(q: QuizQ, option: Int): Boolean {
        val right = option == q.a
        award { it.answer(q.id, right) }
        return right
    }
    fun markUpdatesSeen(date: String) { if (date > progress.value.seen) la.progress.edit { it.markSeen(date) } }
    fun resetProgress() = la.progress.edit { Progress() }

    // ---- sync & updates ----
    fun syncNow() = la.refresh(true)


    // ---- quiz ----
    private val _quiz = MutableStateFlow(QuizSession())
    val quiz: StateFlow<QuizSession> = _quiz.asStateFlow()

    fun startQuiz(lib: Library, module: String?, onlyMissed: Boolean = false) {
        var order = Study.quizOrder(lib, module, System.nanoTime())
        if (onlyMissed) order = order.filter { progress.value.quiz[it] != 1 }.ifEmpty { order }
        _quiz.value = QuizSession(module = module, order = order)
    }

    fun ensureQuiz(lib: Library) { if (_quiz.value.order.isEmpty()) startQuiz(lib, null) }

    fun pick(lib: Library, option: Int) {
        val s = _quiz.value
        if (s.picked != null || s.done) return
        val q = lib.quiz.firstOrNull { it.id == s.order.getOrNull(s.index) } ?: return
        val right = option == q.a
        award { it.answer(q.id, right) }
        _quiz.value = s.copy(picked = option, answered = s.answered + 1, right = s.right + if (right) 1 else 0)
    }

    fun nextQuestion() = _quiz.update { if (it.picked == null) it else it.copy(index = it.index + 1, picked = null) }

    // ---- flashcards ----
    private val _cards = MutableStateFlow(CardSession())
    val cards: StateFlow<CardSession> = _cards.asStateFlow()
    fun flip() = _cards.update { it.copy(flipped = !it.flipped) }
    fun setUnknownOnly(v: Boolean) = _cards.update { CardSession(unknownOnly = v) }
    fun restartCards() = _cards.update { it.copy(index = 0, flipped = false) }
    fun answerCard(id: String, known: Boolean) {
        award { it.knowCard(id, known) }
        // In "still learning" mode a known card drops out of the list, so the index stays put.
        _cards.update { if (it.unknownOnly && known) it.copy(flipped = false) else it.copy(index = it.index + 1, flipped = false) }
    }
}
