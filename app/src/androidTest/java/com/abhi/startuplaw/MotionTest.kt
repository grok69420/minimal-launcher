package com.abhi.startuplaw

import android.graphics.Bitmap
import android.provider.Settings
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsNodeInteraction
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.click
import androidx.compose.ui.test.getBoundsInRoot
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Runs with the phone's animations switched ON. Freezes the app's clock mid-animation to prove each
 * animation actually plays (two screens on screen during a slide, a pop-up still travelling, etc.),
 * saves a frame from the middle of every animation, then checks everything settles correctly.
 */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class MotionTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private val clock get() = rule.mainClock

    private val shots by lazy {
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, "shots").apply { mkdirs() }
    }

    /** Captures exactly the current frame (no waiting, so mid-animation frames are kept). */
    private fun frame(name: String) {
        val bmp = rule.onRoot().captureToImage().asAndroidBitmap()
        File(shots, "$name.png").outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private fun count(tag: String) = rule.onAllNodesWithTag(tag).fetchSemanticsNodes().size
    private fun SemanticsNodeInteraction.tap() = performSemanticsAction(SemanticsActions.OnClick)
    private fun settle() { clock.autoAdvance = true; rule.waitForIdle() }
    private fun freeze() { rule.waitForIdle(); clock.autoAdvance = false }
    private fun waitTag(tag: String) { settle(); rule.waitUntil(15_000) { count(tag) > 0 } }

    @Test
    fun animationsPlay() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        val scale = Settings.Global.getFloat(ctx.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f)
        assertTrue("This test needs animations switched on (animator scale is $scale)", scale > 0f)
        waitTag("open_search")

        // 1. Opening a lesson slides forward: mid-way both screens are present, at the end only one.
        freeze()
        rule.onNodeWithTag("continue").tap()
        clock.advanceTimeBy(150)
        frame("m01-open-lesson-mid")
        assertEquals("both screens should be on screen mid-transition", 2, count("list"))
        clock.advanceTimeBy(1200)
        assertEquals(1, count("list"))
        frame("m02-open-lesson-end")

        // 2. The word pop-up springs up from below and slides away when closed.
        settle()
        rule.onNodeWithTag("list").performScrollToNode(hasTestTag("kp_0"))
        freeze()
        rule.onNodeWithTag("kp_0").performTouchInput { click(Offset(10f, 20f)) }
        clock.advanceTimeBy(70)
        val midTop = rule.onNodeWithTag("term_popup").getBoundsInRoot().top
        frame("m03-popup-mid")
        clock.advanceTimeBy(1500)
        val endTop = rule.onNodeWithTag("term_popup").getBoundsInRoot().top
        frame("m04-popup-end")
        assertTrue("pop-up should travel upward into place ($midTop -> $endTop)", midTop > endTop + 8.dp)
        rule.onNodeWithTag("term_close").tap()
        clock.advanceTimeBy(80)
        assertEquals("pop-up should still be sliding away", 1, count("term_popup"))
        frame("m05-popup-closing")
        clock.advanceTimeBy(1200)
        assertEquals(0, count("term_popup"))

        // 3. Back reverses the slide.
        rule.onNodeWithTag("back").tap()
        clock.advanceTimeBy(150)
        frame("m06-back-mid")
        assertEquals(2, count("list"))
        clock.advanceTimeBy(1200)
        assertEquals(1, count("list"))

        // 4. Switching tabs: the highlight glides along the bar while the screens fade through.
        rule.onNodeWithTag("tab_practice").tap()
        clock.advanceTimeBy(90)
        frame("m07-tab-glide-mid")
        clock.advanceTimeBy(1500)
        frame("m08-tab-glide-end")

        // 5. Flashcards slide in and the card flips in 3D.
        settle()
        rule.onNodeWithTag("list").performScrollToNode(hasText("Flashcards ·", substring = true))
        rule.onNodeWithText("Flashcards ·", substring = true).tap()
        waitTag("flashcard")
        freeze()
        rule.onNodeWithTag("flashcard").tap()
        clock.advanceTimeBy(160)
        frame("m09-card-flip-mid")
        clock.advanceTimeBy(1000)
        frame("m10-card-flip-end")
        assertTrue(rule.onAllNodes(hasText("ANSWER")).fetchSemanticsNodes().isNotEmpty())

        // 6. Pressing a button visibly sinks it (spring press feedback).
        rule.onNodeWithTag("card_know").performTouchInput { down(center) }
        clock.advanceTimeBy(120)
        frame("m11-button-pressed")
        rule.onNodeWithTag("card_know").performTouchInput { up() }
        clock.advanceTimeBy(160)
        frame("m12-next-card-sliding")
        clock.advanceTimeBy(1200)

        // 7. Mood boards: colours rise into place, the card opens on a spring, a copied colour flips its label.
        settle()
        rule.onNodeWithTag("tab_playbook").tap()
        waitTag("list")
        rule.onNodeWithTag("list").performScrollToNode(hasText("Mood boards ·", substring = true))
        freeze()
        rule.onNodeWithText("Mood boards ·", substring = true).tap()
        clock.advanceTimeBy(200)
        frame("m13-swatches-rising")
        clock.advanceTimeBy(1500)
        rule.onNodeWithTag("palette_blank-street").tap()
        clock.advanceTimeBy(140)
        frame("m14-mood-board-opening")
        clock.advanceTimeBy(1500)
        assertTrue(rule.onAllNodes(hasText("A headline in this mood")).fetchSemanticsNodes().isNotEmpty())
        frame("m15-mood-board-open")
        settle()
        rule.onNodeWithTag("list").performScrollToNode(hasTestTag("swatch_fffdfc"))
        freeze()
        rule.onNodeWithTag("swatch_fffdfc").tap()
        clock.advanceTimeBy(100)
        frame("m16-copied-mid")
        clock.advanceTimeBy(600)
        assertTrue(rule.onAllNodes(hasText("COPIED")).fetchSemanticsNodes().isNotEmpty())
        frame("m17-copied")
        settle()

        settle()
    }
}
