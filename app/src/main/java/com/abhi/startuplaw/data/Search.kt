package com.abhi.startuplaw.data

import java.text.Normalizer
import kotlin.math.ln

enum class Kind(val label: String) { Lesson("Lesson"), Case("Case"), Loophole("Loophole"), Story("Founder story"), Trap("Term-sheet trap"), Update("Update"), Quiz("Quiz") }

data class Hit(val kind: Kind, val id: String, val title: String, val snippet: String, val module: String, val score: Double, val text: String)

/** Local full-text search over the whole library. Works offline; also feeds the tutor. */
class SearchIndex(lib: Library) {
    private class Doc(val kind: Kind, val id: String, val title: String, val module: String, val snippet: String, val text: String) {
        val nTitle = norm(title)
        val nText = norm(text)
    }

    private val docs: List<Doc> = buildList {
        lib.lessons.forEach { add(Doc(Kind.Lesson, it.id, it.title, it.module, it.summary,
            listOf(it.summary, it.body.joinToString(" "), it.keyPoints.joinToString(". ")).joinToString(" "))) }
        lib.cases.forEach { add(Doc(Kind.Case, it.id, it.name, it.module, it.held,
            listOf(it.court, it.date, it.citation, it.status, it.tags.joinToString(" "), it.facts, it.held, it.why).joinToString(" "))) }
        lib.gaps.forEach { add(Doc(Kind.Loophole, it.id, it.title, it.module, it.gap,
            listOf(it.status, it.gap, it.used, it.closed, it.today, it.timeline.joinToString(" ") { t -> t.y + " " + t.e }).joinToString(" "))) }
        lib.stories.forEach { add(Doc(Kind.Story, it.id, it.name, "founders", it.lesson,
            listOf(it.who, it.country, it.kind, it.outcome, it.what, it.move, it.lesson, it.apply, it.status).joinToString(" "))) }
        lib.traps.forEach { add(Doc(Kind.Trap, it.id, it.clause, "founders", it.risk,
            listOf(it.looks, it.risk, it.ask, it.india, it.seen).joinToString(" "))) }
        lib.updates.forEach { add(Doc(Kind.Update, it.id, it.title, it.module, it.summary, it.date + " " + it.kind + " " + it.summary)) }
    }

    /** Ranks by rare-word matches (IDF), with extra weight for title hits and full-phrase hits. */
    fun search(query: String, limit: Int = 30): List<Hit> {
        val terms = tokens(query).map(::stem).distinct()
        if (terms.isEmpty()) return emptyList()
        val phrase = norm(query).trim()
        val n = docs.size.toDouble()
        val idf = terms.associateWith { t -> ln(1.0 + n / (docs.count { it.nText.contains(t) || it.nTitle.contains(t) } + 0.5)) }
        return docs.asSequence().mapNotNull { d ->
            var score = 0.0
            var matched = 0
            for (t in terms) {
                val inTitle = d.nTitle.contains(t)
                val inText = d.nText.contains(t)
                if (!inTitle && !inText) continue
                matched++
                val w = idf.getValue(t)
                score += w * ((if (inTitle) 2.5 else 0.0) + (if (inText) 1.0 else 0.0) + 0.25 * minOf(3, count(d.nText, t)))
            }
            if (matched == 0) return@mapNotNull null
            score *= 0.5 + 0.5 * matched / terms.size
            if (phrase.length > 3 && d.nTitle.contains(phrase)) score += 6.0
            else if (phrase.length > 3 && d.nText.contains(phrase)) score += 3.0
            Hit(d.kind, d.id, d.title, d.snippet, d.module, score, d.text)
        }.sortedWith(compareByDescending<Hit> { it.score }.thenBy { it.title }).take(limit).toList()
    }

    companion object {
        private val STOP = setOf("the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "is", "are", "what", "how", "my", "i", "do",
            "does", "can", "it", "if", "with", "be", "by", "at", "as", "from", "that", "this", "when", "why", "which", "who", "me", "under",
            "another", "other", "still", "worth", "will", "should", "would", "could", "about", "there", "their", "your", "you", "we", "our",
            "they", "has", "have", "was", "were", "any", "all", "not", "no", "get", "into", "than", "then", "them", "its", "after", "before")

        fun norm(s: String): String = Normalizer.normalize(s.lowercase(), Normalizer.Form.NFD)
            .replace(Regex("\\p{Mn}+"), "")
            .replace('’', '\'').replace('‘', '\'')

        fun tokens(q: String): List<String> = norm(q).split(Regex("[^\\p{L}\\p{N}.]+"))
            .map { it.trim('.') }.filter { it.length >= 2 && it !in STOP }.distinct().take(12)

        /** Light English stemming so "starting" finds "start", "investors" finds "investor". */
        fun stem(t: String): String = when {
            t.length > 5 && t.endsWith("ing") -> t.dropLast(3)
            t.length > 4 && t.endsWith("ies") -> t.dropLast(3) + "y"
            t.length > 5 && t.endsWith("ed") -> t.dropLast(2)
            t.length > 3 && t.endsWith("s") && !t.endsWith("ss") -> t.dropLast(1)
            else -> t
        }

        private fun count(hay: String, needle: String): Int {
            var i = 0; var n = 0
            while (true) { i = hay.indexOf(needle, i); if (i < 0) return n; n++; i += needle.length }
        }
    }
}
