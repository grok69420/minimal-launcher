package com.abhi.startuplaw.data

import java.net.URLEncoder
import java.time.LocalDate

data class Card(val id: String, val kind: Kind, val module: String, val front: String, val back: String, val points: List<String> = emptyList())

object Study {
    fun deck(lib: Library): List<Card> = buildList {
        lib.modulesSorted.forEach { m ->
            lib.lessonsByModule[m.id].orEmpty().forEach { add(Card("l:" + it.id, Kind.Lesson, it.module, it.title, it.summary, it.keyPoints)) }
        }
        lib.casesSorted.forEach { add(Card("c:" + it.id, Kind.Case, it.module, it.name, it.held, listOfNotNull(it.why.takeIf(String::isNotBlank)))) }
        lib.gapsSorted.forEach { add(Card("g:" + it.id, Kind.Loophole, it.module, it.title, it.closed, listOfNotNull(it.today.takeIf(String::isNotBlank)))) }
        lib.trapsSorted.forEach { add(Card("t:" + it.id, Kind.Trap, "founders", it.clause, it.ask, listOfNotNull(it.risk.takeIf(String::isNotBlank)))) }
    }

    /** Stable shuffle so the quiz order survives recomposition but differs per round. */
    fun quizOrder(lib: Library, module: String?, seed: Long): List<String> =
        lib.quiz.filter { module == null || it.module == module }.map { it.id }.shuffled(kotlin.random.Random(seed))

    // ---- tutor ----

    data class TutorAnswer(val notes: List<Hit>, val prompt: String)

    fun tutor(lib: Library, index: SearchIndex, question: String, today: LocalDate = LocalDate.now()): TutorAnswer {
        val top = index.search(question, 6)
        val recent = lib.updatesSorted.take(3)
        val notes = buildString {
            top.forEach { h -> append("[").append(h.kind.label).append("] ").append(h.title).append('\n').append(h.text.take(1100)).append("\n\n") }
            recent.filter { r -> top.none { it.kind == Kind.Update && it.id == r.id } }
                .forEach { append("[Update] ").append(it.title).append('\n').append(it.date).append(' ').append(it.summary).append("\n\n") }
        }.take(5200)
        val prompt = """
You are my tutor on Indian startup law: company law, court cases and precedents, loopholes and how they were closed, foreign law and offshore structures used by Indian startups, and tax planning, plus founder failures, control fights and term-sheet traps. Today is $today. My library was last checked for new developments on ${lib.meta.lastChecked.ifBlank { "unknown" }}.
Rules:
1. Base the answer on the LIBRARY NOTES below. End with one line "From the library:" naming the note titles you used.
2. If the notes do not cover part of the question, say "Not covered in the library notes" for that part. You may add general background only if you label it "General background (verify)". Never invent case names, citations, section numbers, dates, rates or amounts.
3. The Income-tax Act, 2025 replaced the 1961 Act from 1 April 2026; mention both section numbers only when the notes give them.
4. Explain lawful planning and the anti-avoidance consequences; do not help conceal income or evade tax.
5. Educational, not legal or tax advice; for a real decision suggest a CA or lawyer in one short sentence.
6. Under 220 words unless I ask for more.

QUESTION: $question

LIBRARY NOTES:
$notes
""".trim()
        return TutorAnswer(top, prompt)
    }

    /** Opens a new Claude chat with the prompt filled in (Claude app if installed, else browser). */
    fun claudeUrl(prompt: String): String =
        "https://claude.ai/new?q=" + URLEncoder.encode(prompt.take(MAX_PROMPT), "UTF-8").replace("+", "%20")

    private const val MAX_PROMPT = 7000
}
