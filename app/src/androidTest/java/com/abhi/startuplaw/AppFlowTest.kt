package com.abhi.startuplaw

import android.content.pm.ActivityInfo
import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.SemanticsNodeInteraction
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.click
import androidx.compose.ui.geometry.Offset
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Walks every screen like a person would, checks the important behaviour, and saves a
 * screenshot of each step (pulled by tests/emulator-test.sh for review).
 */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class AppFlowTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    private val shots by lazy {
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, "shots").apply { mkdirs() }
    }

    private fun shot(name: String) {
        rule.waitForIdle()
        Thread.sleep(250)
        rule.waitForIdle()
        val bmp = rule.onRoot().captureToImage().asAndroidBitmap()
        File(shots, "$name.png").outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private fun waitTag(tag: String, ms: Long = 15_000) =
        rule.waitUntil(ms) { rule.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }

    private fun waitText(text: String, ms: Long = 15_000, substring: Boolean = false) =
        rule.waitUntil(ms) { rule.onAllNodes(hasText(text, substring = substring)).fetchSemanticsNodes().isNotEmpty() }

    private fun scrollTo(m: SemanticsMatcher) {
        rule.waitForIdle()
        rule.onNodeWithTag("list").performScrollToNode(m)
    }

    // Taps via the accessibility click action, so a node partly under the floating bottom bar still works.
    private fun SemanticsNodeInteraction.tap() = performSemanticsAction(SemanticsActions.OnClick)

    private fun tapTag(tag: String) { scrollTo(hasTestTag(tag)); rule.onNodeWithTag(tag).tap(); rule.waitForIdle() }
    private fun tapText(text: String) { scrollTo(hasText(text)); rule.onNodeWithText(text).tap(); rule.waitForIdle() }
    private fun tab(route: String) { rule.onNodeWithTag("tab_$route").tap(); rule.waitForIdle() }
    private fun back() { rule.onNodeWithTag("back").tap(); rule.waitForIdle() }

    @Test
    fun everyScreenWorks() {
        waitTag("open_search", 30_000)
        shot("01-home")

        // Start here: the first lesson of Volume 0 from the Continue card
        tapTag("continue"); waitTag("plain"); shot("01b-first-lesson")
        tapTag("mark_learned"); waitText("✓ LEARNED — TAP TO UNDO"); shot("01c-learned")
        assertTrue("no XP or levels anywhere", rule.onAllNodes(hasText(" XP", substring = true)).fetchSemanticsNodes().isEmpty())
        back(); waitTag("open_search"); shot("01d-home-after")

        // Library -> volume -> lesson -> mark learned -> next lesson
        tapTag("vol_foundations"); waitTag("lesson_f1"); shot("02-volume")
        tapTag("lesson_f1"); waitText("Recognition is the gateway to most startup-specific benefits, and its definition changed on 4 February 2026."); shot("03-lesson-top")
        // Tap an everyday word: explains it isn't a legal term
        scrollTo(hasTestTag("kp_0")); rule.onNodeWithTag("kp_0").performTouchInput { click(Offset(10f, 20f)) }
        waitTag("term_popup"); shot("03b-word-popup")
        rule.onNodeWithTag("term_close").tap(); rule.waitForIdle()
        tapTag("mark_learned"); waitText("✓ LEARNED — TAP TO UNDO")
        shot("04-lesson-learned")
        tapTag("next_lesson"); waitText("Choosing the entity: private company, LLP or OPC"); shot("05-next-lesson")
        // Tap a legal term ("LLPs") and get its plain meaning
        scrollTo(hasTestTag("kp_1")); rule.onNodeWithTag("kp_1").performTouchInput { click(Offset(10f, 20f)) }
        waitText("LLP (limited liability partnership)"); shot("05b-term-popup")
        rule.onNodeWithTag("term_scrim").tap(); rule.waitForIdle()
        back(); waitTag("lesson_f1")
        back(); waitTag("open_search")

        // New volumes: GTM, IP, marketing, sales
        tapTag("vol_gtm"); waitTag("lesson_gtm2"); shot("05c-volume-gtm")
        tapTag("lesson_gtm2"); waitText("Pricing, discounts and competition law"); shot("05d-lesson-pricing")
        back(); waitTag("lesson_gtm2"); back(); waitTag("open_search")
        tapTag("vol_ip"); waitTag("lesson_ip2"); tapTag("lesson_ip2"); waitText("Patents for software, AI and medicines"); shot("05e-lesson-patents")
        back(); waitTag("lesson_ip2"); back(); waitTag("open_search")

        // Cases
        tab("cases"); waitTag("case_tiger-global-2026"); shot("06-cases")
        tapTag("case_tiger-global-2026"); waitText("HELD"); shot("07-case")
        back(); waitTag("case_tiger-global-2026")
        tapTag("case_google-drs-2023"); waitText("Google LLC v DRS Logistics (P) Ltd"); shot("07b-case-keywords")
        back()

        // Playbook: story + trap
        tab("playbook"); waitTag("story_anthropic-ltbt"); shot("08-playbook")
        tapTag("story_byjus"); waitText("WHAT HAPPENED"); shot("09-story")
        tapTag("mark_studied"); waitText("✓ STUDIED — TAP TO UNDO")
        back(); waitTag("tab_playbook")
        scrollTo(hasText("Term-sheet traps ·", substring = true)); rule.onNodeWithText("Term-sheet traps ·", substring = true).tap(); rule.waitForIdle()
        tapTag("trap_participating-pref"); waitText("ASK FOR INSTEAD"); shot("10-trap-open")
        // Mood boards: open one, see the preview, copy a colour
        scrollTo(hasText("Mood boards ·", substring = true)); rule.onNodeWithText("Mood boards ·", substring = true).tap(); rule.waitForIdle()
        waitTag("palette_rolls-royce"); shot("10b-mood-boards")
        tapTag("palette_rolex"); waitTag("preview_rolex"); shot("10c-mood-board-open")
        tapTag("swatch_006039"); waitText("COPIED"); shot("10d-colour-copied")
        scrollTo(hasText("LEGAL GUARDRAIL")); shot("10e-mood-board-guardrail")

        // Practice: quiz + flashcards
        tab("practice"); waitTag("quiz_question"); shot("11-quiz")
        rule.onNodeWithTag("opt_0").tap(); rule.waitForIdle()
        waitTag("quiz_next"); shot("12-quiz-answered")
        tapTag("quiz_next"); waitTag("quiz_question")
        scrollTo(hasText("Flashcards ·", substring = true)); rule.onNodeWithText("Flashcards ·", substring = true).tap(); rule.waitForIdle()
        waitTag("flashcard"); shot("13-card-front")
        rule.onNodeWithTag("flashcard").tap(); rule.waitForIdle(); Thread.sleep(600)
        waitText("ANSWER"); shot("14-card-back")
        tapTag("card_know")

        // Progress map shows the learned lesson
        tab("map"); waitTag("progress_card"); shot("15-map")
        scrollTo(hasTestTag("constellation"))
        scrollTo(hasTestTag("branch_foundations"))
        assertTrue(rule.onAllNodes(hasText("✓ What counts as a ‘startup’: the DPIIT 2026 framework")).fetchSemanticsNodes().isNotEmpty())
        shot("16-map-branches")

        // Home tiles
        tab("home"); waitTag("open_search")
        tapText("Loopholes"); waitTag("gap_mauritius-route")
        tapTag("gap_mauritius-route"); waitText("HOW IT WAS CLOSED"); shot("17-loophole-open")
        back(); waitTag("open_search")
        tapText("Updates"); waitText("Updates"); shot("18-updates")
        back(); waitTag("open_search")

        // Search
        tapTag("open_search"); waitTag("search_field")
        rule.onNodeWithTag("search_field").performTextInput("dark patterns")
        waitText("MATCHES", substring = true); shot("19-search")
        back(); waitTag("open_search")

        // Tutor
        tapTag("chip_glossary"); waitTag("glossary_field"); shot("20a-glossary")
        rule.onNodeWithTag("glossary_field").performTextInput("sweat")
        waitTag("term_sweat-equity"); rule.onNodeWithTag("term_sweat-equity").tap(); waitTag("term_popup"); shot("20b-glossary-term")
        rule.onNodeWithTag("term_close").tap(); rule.waitForIdle()
        back(); waitTag("open_search")
        tapText("Tutor"); waitTag("tutor_field")
        rule.onNodeWithTag("tutor_field").performTextInput("Can investors stop me starting another company?")
        tapTag("tutor_find"); waitText("FROM THE LIBRARY", substring = true); shot("20-tutor")
        back(); waitTag("open_search")

        // Sync & app screen
        rule.onNodeWithTag("status_chip").tap(); rule.waitForIdle()
        waitTag("sync_now"); shot("21-about")
        back(); waitTag("open_search")

        // Rotation keeps the app working
        rule.activityRule.scenario.onActivity { it.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE }
        Thread.sleep(1500); waitTag("open_search"); shot("22-landscape")
        rule.activityRule.scenario.onActivity { it.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT }
        Thread.sleep(1500); waitTag("open_search")

        // Progress survives the activity being recreated
        rule.activityRule.scenario.recreate()
        waitTag("open_search")
        tab("map"); waitTag("list")
        scrollTo(hasTestTag("branch_foundations"))
        assertTrue(rule.onAllNodes(hasText("✓ What counts as a ‘startup’: the DPIIT 2026 framework")).fetchSemanticsNodes().isNotEmpty())
    }
}
