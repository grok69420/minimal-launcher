package com.abhi.startuplaw.data

/** Where a glossary term occurs inside a piece of text. */
data class TermSpan(val start: Int, val end: Int, val term: Term)

/**
 * Finds glossary terms in text (longest match wins, whole words only, plural "s"/"es" allowed)
 * and looks up any single tapped word. All-caps aliases (ESOP, SHA, NCLT) match case-sensitively.
 */
class Glossary(terms: List<Term>) {
    private class Alias(val text: String, val caseSensitive: Boolean, val term: Term)

    private val byFirst: Map<Char, List<Alias>> = terms.flatMap { t ->
        (t.aliases + t.term).filter { it.length >= 2 }.map { a ->
            val norm = a.replace('’', '\'')
            Alias(norm, norm.any(Char::isLetter) && norm.filter(Char::isLetter).all(Char::isUpperCase) && norm.length <= 6, t)
        }
    }.distinctBy { it.text.lowercase() + it.caseSensitive }
        .groupBy { it.text[0].lowercaseChar() }
        .mapValues { (_, v) -> v.sortedByDescending { it.text.length } }

    private val exact: Map<String, Term> = terms.flatMap { t -> (t.aliases + t.term).map { it.replace('’', '\'').lowercase() to t } }.toMap()

    val isEmpty get() = byFirst.isEmpty()

    fun find(raw: String): List<TermSpan> {
        if (byFirst.isEmpty() || raw.isEmpty()) return emptyList()
        val text = raw.replace('’', '\'')
        val out = ArrayList<TermSpan>()
        var i = 0
        while (i < text.length) {
            if ((i == 0 || !isWordChar(text[i - 1])) && isWordChar(text[i])) {
                val cands = byFirst[text[i].lowercaseChar()]
                var hit: TermSpan? = null
                if (cands != null) for (a in cands) {
                    if (!text.regionMatches(i, a.text, 0, a.text.length, ignoreCase = !a.caseSensitive)) continue
                    var end = i + a.text.length
                    if (end < text.length && text[end] == 's' && (end + 1 == text.length || !isWordChar(text[end + 1]))) end += 1
                    else if (end + 1 < text.length && text[end] == 'e' && text[end + 1] == 's' && (end + 2 == text.length || !isWordChar(text[end + 2]))) end += 2
                    if (end < text.length && isWordChar(text[end])) continue
                    hit = TermSpan(i, end, a.term); break
                }
                if (hit != null) { out += hit; i = hit.end; continue }
            }
            i++
        }
        return out
    }

    /** Looks up one tapped word (or phrase): exact alias first, then a simple singular/stem form. */
    fun lookup(word: String): Term? {
        val w = word.replace('’', '\'').trim().trim('.', ',', ';', ':', '(', ')', '\'', '"', '“', '”').lowercase()
        if (w.isEmpty()) return null
        exact[w]?.let { return it }
        val stems = listOf(w.removeSuffix("'s"), w.removeSuffix("es"), w.removeSuffix("s"), w.removeSuffix("ing"), w.removeSuffix("ed"), w.removeSuffix("d"))
        return stems.firstNotNullOfOrNull { exact[it] }
    }

    companion object {
        fun isWordChar(c: Char) = c.isLetterOrDigit()

        /** The word under [offset], with hyphens kept inside words ("non-compete"). */
        fun wordAt(text: String, offset: Int): IntRange? {
            if (text.isEmpty()) return null
            var o = offset.coerceIn(0, text.length - 1)
            if (!isWordChar(text[o]) && o > 0 && isWordChar(text[o - 1])) o -= 1
            if (!isWordChar(text[o])) return null
            fun part(c: Char, i: Int) = isWordChar(c) || ((c == '-' || c == '\'' || c == '’') && i > 0 && i < text.length - 1 && isWordChar(text[i - 1]) && isWordChar(text[i + 1]))
            var s = o; while (s > 0 && part(text[s - 1], s - 1)) s--
            var e = o; while (e < text.length - 1 && part(text[e + 1], e + 1)) e++
            return s..e
        }

        /** The sentence around [offset], for context when asking Claude. */
        fun sentenceAt(text: String, offset: Int): String {
            val o = offset.coerceIn(0, maxOf(0, text.length - 1))
            val s = text.lastIndexOfAny(charArrayOf('.', '!', '?'), o - 1).let { if (it < 0) 0 else it + 1 }
            val e = text.indexOfAny(charArrayOf('.', '!', '?'), o).let { if (it < 0) text.length else it + 1 }
            return text.substring(s, e).trim().take(400)
        }
    }
}
