package com.abhi.startuplaw.data

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** A source link. Only https links are ever opened. */
@Serializable
data class Link(val t: String = "", val u: String = "") {
    val isSafe: Boolean get() = u.startsWith("https://") && u.length < 2048
}

@Serializable
data class Module(
    val id: String,
    val title: String = "",
    val vol: String = "",
    val order: Int = 0,
    val blurb: String = "",
)

@Serializable
data class Lesson(
    val id: String,
    val module: String = "",
    val order: Int = 0,
    val title: String = "",
    val summary: String = "",
    val body: List<String> = emptyList(),
    val keyPoints: List<String> = emptyList(),
    val sources: List<Link> = emptyList(),
    val updated: String = "",
)

@Serializable
data class LawCase(
    val id: String,
    val name: String = "",
    val court: String = "",
    val date: String = "",
    val year: Int = 0,
    val citation: String = "",
    val module: String = "",
    val status: String = "",
    val tags: List<String> = emptyList(),
    val facts: String = "",
    val held: String = "",
    val why: String = "",
    val src: Link? = null,
)

@Serializable
data class TimelineItem(val y: String = "", val e: String = "")

@Serializable
data class Gap(
    val id: String,
    val order: Int = 0,
    val module: String = "",
    val title: String = "",
    val status: String = "",
    val gap: String = "",
    val used: String = "",
    val closed: String = "",
    val timeline: List<TimelineItem> = emptyList(),
    val today: String = "",
    val src: List<Link> = emptyList(),
)

@Serializable
data class Story(
    val id: String,
    val order: Int = 0,
    val short: String = "",
    val name: String = "",
    val who: String = "",
    val country: String = "",
    val year: Int = 0,
    val kind: String = "",
    val outcome: String = "",
    val what: String = "",
    val move: String = "",
    val lesson: String = "",
    val apply: String = "",
    val status: String = "",
    val checked: String = "",
    val src: List<Link> = emptyList(),
)

@Serializable
data class Trap(
    val id: String,
    val order: Int = 0,
    val clause: String = "",
    val looks: String = "",
    val risk: String = "",
    val ask: String = "",
    val india: String = "",
    val seen: String = "",
)

@Serializable
data class QuizQ(
    val id: String,
    val module: String = "",
    val q: String = "",
    val opts: List<String> = emptyList(),
    val a: Int = -1,
    val why: String = "",
)

@Serializable
data class LawUpdate(
    val id: String,
    val date: String = "",
    val kind: String = "",
    val module: String = "",
    val title: String = "",
    val summary: String = "",
    val src: Link? = null,
)

@Serializable
data class Meta(val lastChecked: String = "", val note: String = "")

@Serializable
data class Library(
    val schema: Int = 1,
    /** Publish revision, stamped by the signing pipeline. Higher always wins; older is never accepted. */
    val rev: Long = 0,
    val modules: List<Module> = emptyList(),
    val lessons: List<Lesson> = emptyList(),
    val cases: List<LawCase> = emptyList(),
    val gaps: List<Gap> = emptyList(),
    val stories: List<Story> = emptyList(),
    val traps: List<Trap> = emptyList(),
    val quiz: List<QuizQ> = emptyList(),
    val updates: List<LawUpdate> = emptyList(),
    val meta: Meta = Meta(),
) {
    // Pre-sorted views, computed once per library instance.
    val modulesSorted: List<Module> by lazy { modules.sortedBy { it.order } }
    val lessonsByModule: Map<String, List<Lesson>> by lazy { lessons.groupBy { it.module }.mapValues { (_, v) -> v.sortedBy { it.order } } }
    val lessonById: Map<String, Lesson> by lazy { lessons.associateBy { it.id } }
    val moduleById: Map<String, Module> by lazy { modules.associateBy { it.id } }
    val caseById: Map<String, LawCase> by lazy { cases.associateBy { it.id } }
    val storyById: Map<String, Story> by lazy { stories.associateBy { it.id } }
    val casesSorted: List<LawCase> by lazy { cases.sortedWith(compareByDescending<LawCase> { it.year }.thenBy { it.name }) }
    val gapsSorted: List<Gap> by lazy { gaps.sortedBy { it.order } }
    val storiesSorted: List<Story> by lazy { stories.sortedBy { it.order } }
    val trapsSorted: List<Trap> by lazy { traps.sortedBy { it.order } }
    val updatesSorted: List<LawUpdate> by lazy { updates.sortedByDescending { it.date } }
    val latestUpdateDate: String by lazy { updates.maxOfOrNull { it.date } ?: "" }

    fun moduleTitle(id: String): String = moduleById[id]?.title ?: ""

    companion object {
        const val SCHEMA = 1
        val json = Json { ignoreUnknownKeys = true; isLenient = false; coerceInputValues = true }

        /** Parses and cleans content. Returns null if it is not a usable library. */
        fun parse(text: String): Library? = runCatching { json.decodeFromString(serializer(), text) }
            .getOrNull()?.sanitized()?.takeIf { it.isUsable() }
    }

    fun isUsable(): Boolean = schema <= SCHEMA && modules.isNotEmpty() && lessons.isNotEmpty()

    /** Drops malformed items so one bad record can never break a screen. */
    fun sanitized(): Library {
        fun safeOne(l: Link?) = l?.takeIf { it.isSafe }
        fun safeAll(l: List<Link>) = l.filter { it.isSafe }
        fun <T> uniq(list: List<T>, id: (T) -> String) = list.filter { id(it).isNotBlank() }.distinctBy(id)
        return copy(
            modules = uniq(modules) { it.id },
            lessons = uniq(lessons) { it.id }.filter { it.title.isNotBlank() }.map { it.copy(sources = safeAll(it.sources)) },
            cases = uniq(cases) { it.id }.filter { it.name.isNotBlank() }.map { it.copy(src = safeOne(it.src)) },
            gaps = uniq(gaps) { it.id }.filter { it.title.isNotBlank() }.map { it.copy(src = safeAll(it.src)) },
            stories = uniq(stories) { it.id }.filter { it.name.isNotBlank() }.map { it.copy(src = safeAll(it.src)) },
            traps = uniq(traps) { it.id }.filter { it.clause.isNotBlank() },
            quiz = uniq(quiz) { it.id }.filter { it.q.isNotBlank() && it.opts.size >= 2 && it.a in it.opts.indices },
            updates = uniq(updates) { it.id }.filter { it.title.isNotBlank() }.map { it.copy(src = safeOne(it.src)) },
        )
    }
}
