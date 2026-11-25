package com.abhi.startuplaw.data

import java.time.LocalDate

data class Level(val index: Int, val name: String, val from: Int, val to: Int?) {
    fun progress(xp: Int): Float = if (to == null) 1f else ((xp - from).toFloat() / (to - from)).coerceIn(0f, 1f)
}

data class Badge(val id: String, val title: String, val how: String)

/** What a single action earned, used for the +XP pop and level-up / badge celebrations. */
data class Reward(val xp: Int, val levelUp: Level? = null, val badges: List<Badge> = emptyList(), val id: Long = System.nanoTime())

/**
 * XP is worked out from what you have learned (so it can never drift or double-count):
 * lesson 20 · founder story 15 · quiz answered right 10 · flashcard known 5 · term looked up 2.
 * Levels follow a startup's funding journey.
 */
object Game {
    const val LESSON = 20
    const val STORY = 15
    const val QUIZ = 10
    const val CARD = 5
    const val TERM = 2
    const val DAILY_GOAL = 40

    private val ladder = listOf(
        "Idea" to 0, "Pre-seed" to 60, "Seed" to 160, "Series A" to 320,
        "Series B" to 560, "Series C" to 900, "Pre-IPO" to 1350, "Unicorn" to 1900,
    )

    fun xp(p: Progress, lib: Library): Int {
        val lessons = lib.lessons.count { it.id in p.lessons }
        val stories = lib.stories.count { it.id in p.stories }
        val quiz = lib.quiz.count { p.quiz[it.id] == 1 }
        val cards = p.cards.count { it.value == "k" }
        val terms = lib.glossary.count { it.id in p.terms }
        return lessons * LESSON + stories * STORY + quiz * QUIZ + cards * CARD + terms * TERM
    }

    fun level(xp: Int): Level {
        val i = ladder.indexOfLast { xp >= it.second }.coerceAtLeast(0)
        return Level(i, ladder[i].first, ladder[i].second, ladder.getOrNull(i + 1)?.second)
    }

    fun nextLevelName(l: Level): String? = ladder.getOrNull(l.index + 1)?.first

    fun today(): String = LocalDate.now().toString()

    /** Consecutive days with XP, ending today (or yesterday, so a streak isn't lost before you open the app). */
    fun streak(p: Progress, today: LocalDate = LocalDate.now()): Int {
        var d = if ((p.days[today.toString()] ?: 0) > 0) today else today.minusDays(1)
        var n = 0
        while ((p.days[d.toString()] ?: 0) > 0) { n++; d = d.minusDays(1) }
        return n
    }

    fun todayXp(p: Progress, today: LocalDate = LocalDate.now()) = p.days[today.toString()] ?: 0

    private fun volumeDone(p: Progress, lib: Library, id: String) =
        lib.lessonsByModule[id].orEmpty().let { ls -> ls.isNotEmpty() && ls.all { it.id in p.lessons } }

    private val badges: List<Pair<Badge, (Progress, Library) -> Boolean>> = listOf(
        Badge("first", "First step", "Learn your first lesson") to { p, l -> l.lessons.any { it.id in p.lessons } },
        Badge("basics", "Foundations laid", "Finish Volume 0: Start Here") to { p, l -> volumeDone(p, l, "basics") },
        Badge("volume", "Volume closed", "Finish any volume I–VII") to { p, l -> l.modules.any { it.id != "basics" && volumeDone(p, l, it.id) } },
        Badge("curious", "Curious mind", "Look up 25 words") to { p, l -> l.glossary.count { it.id in p.terms } >= 25 },
        Badge("quiz10", "Sharp", "Get 10 quiz questions right") to { p, l -> l.quiz.count { p.quiz[it.id] == 1 } >= 10 },
        Badge("stories5", "Learns from others", "Study 5 founder stories") to { p, l -> l.stories.count { it.id in p.stories } >= 5 },
        Badge("cards25", "Memory bank", "Know 25 flashcards") to { p, _ -> p.cards.count { it.value == "k" } >= 25 },
        Badge("streak3", "On a roll", "Learn 3 days in a row") to { p, _ -> streak(p) >= 3 },
        Badge("streak7", "Habit formed", "Learn 7 days in a row") to { p, _ -> streak(p) >= 7 },
        Badge("seriesA", "Series A", "Reach 320 XP") to { p, l -> xp(p, l) >= 320 },
        Badge("unicorn", "Unicorn", "Reach 1,900 XP") to { p, l -> xp(p, l) >= 1900 },
    )

    val allBadges: List<Badge> get() = badges.map { it.first }

    fun earned(p: Progress, lib: Library): Set<String> = badges.filter { it.second(p, lib) }.map { it.first.id }.toSet()

    /** Compares before/after an action. Null when nothing was earned. */
    fun reward(before: Progress, after: Progress, lib: Library): Reward? {
        val gained = xp(after, lib) - xp(before, lib)
        if (gained <= 0) return null
        val lb = level(xp(before, lib)); val la = level(xp(after, lib))
        val newBadges = earned(after, lib) - earned(before, lib)
        return Reward(gained, if (la.index > lb.index) la else null, badges.map { it.first }.filter { it.id in newBadges })
    }
}
