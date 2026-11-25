package com.abhi.startuplaw

import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.data.Progress
import com.abhi.startuplaw.data.SearchIndex
import com.abhi.startuplaw.data.Signing
import com.abhi.startuplaw.data.Study
import com.abhi.startuplaw.ui.screens.caseKey
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.security.KeyPairGenerator
import java.security.Signature
import java.time.LocalDate

class CoreTest {
    private val text = File("src/main/assets/content.json").readText()
    private val lib = Library.parse(text)!!

    @Test fun bundledLibraryIsComplete() {
        assertEquals(12, lib.modules.size)
        assertTrue(listOf("gtm", "ip", "marketing", "sales").all { m -> lib.lessonsByModule[m].orEmpty().size >= 3 })
        assertTrue(lib.glossary.size >= 150)
        assertEquals("basics", lib.lessonsInOrder.first().module)
        assertTrue(lib.lessons.all { it.plain.isNotBlank() })
        assertTrue(lib.lessons.size >= 35)
        assertTrue(lib.cases.size >= 22)
        assertTrue(lib.gaps.size >= 8)
        assertTrue(lib.stories.size >= 13)
        assertTrue(lib.traps.size >= 12)
        assertTrue(lib.quiz.size >= 30)
        assertTrue(lib.updates.isNotEmpty())
        assertTrue(lib.meta.lastChecked.matches(Regex("\\d{4}-\\d{2}-\\d{2}")))
    }

    @Test fun everyReferenceResolves() {
        val mods = lib.modules.map { it.id }.toSet()
        lib.lessons.forEach { assertTrue("lesson ${it.id}", it.module in mods) }
        lib.cases.forEach { assertTrue("case ${it.id}", it.module in mods) }
        lib.quiz.forEach { assertTrue("quiz ${it.id}", it.a in it.opts.indices && it.module in mods) }
        lib.updates.forEach { assertTrue("update ${it.id}", it.module in mods) }
        // Every lesson body and key point is non-empty
        lib.lessons.forEach { assertTrue(it.body.isNotEmpty() && it.summary.isNotBlank()) }
    }

    @Test fun onlyHttpsLinksSurvive() {
        val bad = text.replace("https://pib.gov.in", "javascript:alert(1)//")
        val l = Library.parse(bad)!!
        val all = l.lessons.flatMap { it.sources } + l.cases.mapNotNull { it.src } + l.gaps.flatMap { it.src } + l.stories.flatMap { it.src } + l.updates.mapNotNull { it.src }
        assertTrue(all.isNotEmpty())
        assertTrue(all.all { it.u.startsWith("https://") })
    }

    @Test fun rejectsGarbageAndFutureSchema() {
        assertNull(Library.parse("not json"))
        assertNull(Library.parse("{}"))
        assertNull(Library.parse(text.replaceFirst("\"schema\":1", "\"schema\":99")))
        assertNotNull(Library.parse(text.replaceFirst("\"schema\":1", "\"schema\":1,\"futureField\":[1,2]")))
    }

    @Test fun malformedQuizIsDropped() {
        val l = Library.parse(text.replaceFirst("\"a\":2,", "\"a\":9,"))!!
        assertEquals(lib.quiz.size - 1, l.quiz.size)
    }

    @Test fun signatureVerification() {
        val kp = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
        val data = text.toByteArray()
        val sig = Signature.getInstance("SHA256withRSA").apply { initSign(kp.private); update(data) }.sign()
        assertTrue(Signing.verify(data, sig, listOf(kp.public)))
        val tampered = text.replace("Supreme Court", "Supreme Cort").toByteArray()
        assertFalse(Signing.verify(tampered, sig, listOf(kp.public)))
        val other = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
        assertFalse(Signing.verify(data, sig, listOf(other.public)))
        assertFalse(Signing.verify(data, sig, emptyList()))
        val ec = KeyPairGenerator.getInstance("EC").apply { initialize(256) }.generateKeyPair()
        val esig = Signature.getInstance("SHA256withECDSA").apply { initSign(ec.private); update(data) }.sign()
        assertTrue(Signing.verify(data, esig, listOf(other.public, ec.public)))
    }

    @Test fun searchFindsTheRightThings() {
        val idx = SearchIndex(lib)
        assertEquals("tiger-global-2026", idx.search("Tiger Global").first { it.kind.name == "Case" }.id)
        assertTrue(idx.search("non-compete").take(5).any { it.id == "c2" || it.id == "percept-2006" })
        assertTrue(idx.search("liquidation preference").take(3).any { it.id == "participating-pref" })
        assertTrue(idx.search("   ").isEmpty())
        assertTrue(idx.search("zzzzqqq").isEmpty())
        assertTrue(idx.search("Byju’s").isNotEmpty())
        val other = idx.search("Can investors stop me starting another company?", 20).filter { it.kind.name != "Term" }.take(3).map { it.id }
        assertTrue(other.toString(), "fp5" in other || "founder-exclusivity" in other)
    }

    @Test fun progressRoundTripAndToggles() {
        var p = Progress()
        p = p.toggleLesson("f1").toggleLesson("f2").toggleLesson("f1").toggleStory("byjus").answer("q01", true).answer("q02", false).knowCard("l:f1", true).markSeen("2026-11-18")
        val back = Progress.parse(Progress.encode(p))
        assertEquals(setOf("f2"), back.lessons)
        assertEquals(mapOf("q01" to 1, "q02" to 0), back.quiz)
        assertEquals("2026-11-18", back.markSeen("2026-01-01").seen)
        assertEquals(Progress(), Progress.parse("{broken"))
    }

    @Test fun tutorPromptIsGroundedAndBounded() {
        val a = Study.tutor(lib, SearchIndex(lib), "What happens to my ESOPs in a reverse flip?", LocalDate.of(2026, 11, 25))
        assertTrue(a.notes.isNotEmpty())
        assertTrue(a.prompt.contains("QUESTION: What happens to my ESOPs in a reverse flip?"))
        assertTrue(a.prompt.contains("Never invent case names"))
        val url = Study.claudeUrl(a.prompt)
        assertTrue(url.startsWith("https://claude.ai/new?q="))
        assertTrue(url.length < 30000)
    }

    @Test fun deckAndQuizOrder() {
        val d = Study.deck(lib)
        assertEquals(lib.lessons.size + lib.cases.size + lib.gaps.size + lib.traps.size, d.size)
        assertEquals(d.size, d.map { it.id }.toSet().size)
        val o = Study.quizOrder(lib, "tax", 42)
        assertEquals(lib.quiz.count { it.module == "tax" }, o.size)
        assertEquals(o, Study.quizOrder(lib, "tax", 42))
    }

    @Test fun glossaryFindsTermsInText() {
        val g = lib.glossaryIndex
        val text = "Founders got sweat equity and ESOPs under the SHA; LLPs cannot issue shares. The shareholders’ agreement was copied."
        val ids = g.find(text).map { it.term.id }
        assertTrue(ids.toString(), ids.containsAll(listOf("sweat-equity", "esop", "sha", "llp")))
        val span = g.find(text).first { it.term.id == "esop" }
        assertEquals("ESOPs", text.substring(span.start, span.end))
        assertTrue(g.find(text).any { it.term.id == "sha" && text.substring(it.start, it.end).startsWith("shareholders") })
        // whole words only, longest match wins
        assertTrue(g.find("The reverse flip happened.").single().term.id == "reverse-flip")
        assertTrue(g.find("ip address mishap").none { it.term.id == "ip" })
        assertEquals("vesting", g.lookup("vested")?.id)
        assertEquals("esop", g.lookup("ESOPs")?.id)
        assertNull(g.lookup("banana"))
        assertEquals("non-compete", g.find("A non-compete clause").single().term.id)
        // every lesson has at least one underlined term
        lib.lessons.forEach { l -> assertTrue(l.id, g.find(l.body.joinToString(" ")).any { it.term.hl }) }
    }

    @Test fun wordAndSentenceAtOffset() {
        val t = "Founders hold sweat-equity shares. Investors want vetoes."
        val r = com.abhi.startuplaw.data.Glossary.wordAt(t, 16)!!
        assertEquals("sweat-equity", t.substring(r.first, r.last + 1))
        assertEquals("Investors want vetoes.", com.abhi.startuplaw.data.Glossary.sentenceAt(t, 40))
        assertNull(com.abhi.startuplaw.data.Glossary.wordAt(t, 34))
    }

    @Test fun moodBoardsAreHonestAndValid() {
        assertTrue(lib.palettes.size >= 5)
        lib.palettes.forEach { p ->
            assertTrue(p.id, p.basis.isNotBlank() && p.guardrail.isNotBlank() && p.swatches.size >= 3)
            p.swatches.forEach { s -> assertTrue("${p.id}/${s.name}", s.argb != null && s.basis.isNotBlank()) }
        }
        // Malformed colours are dropped, never crash a screen.
        val bad = Library.parse(text.replaceFirst("\"#006039\"", "\"green\""))!!
        assertTrue(bad.palettes.first { it.id == "rolex" }.swatches.none { it.name == "Rolex green" })
        assertEquals(0xFF006039L, lib.palettes.first { it.id == "rolex" }.swatches.first().argb)
        // Mood boards are searchable.
        assertTrue(SearchIndex(lib).search("Purple Spirit").any { it.kind == com.abhi.startuplaw.data.Kind.Palette && it.id == "rolls-royce" })
    }

    @Test fun oldProgressWithGameFieldsStillLoads() {
        // Older builds stored XP per day; that field is now ignored and everything else survives.
        val p = Progress.parse("""{"lessons":["b1"],"quiz":{"q00a":1},"terms":["esop"],"days":{"2026-11-24":40}}""")
        assertEquals(setOf("b1"), p.lessons); assertEquals(1, p.quiz["q00a"]); assertEquals(setOf("esop"), p.terms)
        assertFalse(Progress.encode(p).contains("days"))
    }

    @Test fun caseKeysAreDistinctive() {
        assertEquals("V.B. Rangaraj", caseKey("V.B. Rangaraj v V.B. Gopalakrishnan"))
        assertEquals("Biocon", caseKey("CIT v Biocon Ltd"))
        lib.cases.forEach { assertTrue(it.id, caseKey(it.name).length >= 4) }
    }
}
