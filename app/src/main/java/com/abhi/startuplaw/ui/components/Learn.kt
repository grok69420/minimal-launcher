package com.abhi.startuplaw.ui.components

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.abhi.startuplaw.data.Glossary
import com.abhi.startuplaw.data.Study
import com.abhi.startuplaw.data.Term
import com.abhi.startuplaw.ui.theme.Ice
import com.abhi.startuplaw.ui.theme.LocalReducedMotion
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.cos
import kotlin.math.sin

/** Glossary + "a word was tapped" handler, provided once at the app root. */
class WordLookup(val glossary: Glossary, val open: (word: String, term: Term?, context: String) -> Unit)

val LocalWordLookup = staticCompositionLocalOf<WordLookup?> { null }

/**
 * Reading text where every word is tappable. Glossary terms get a faint dotted underline;
 * tapping (or long-pressing) any word opens its plain-English meaning.
 */
@Composable
fun LawText(text: String, style: TextStyle, color: Color, modifier: Modifier = Modifier) {
    val lookup = LocalWordLookup.current
    if (lookup == null) { Text(text, modifier, style = style, color = color); return }
    val spans = remember(text, lookup.glossary) { lookup.glossary.find(text) }
    val marked = remember(spans) { spans.filter { it.term.hl } }
    val tint = Ice.Cyan
    val annotated = remember(text, marked) {
        buildAnnotatedString {
            append(text)
            marked.forEach { addStyle(SpanStyle(color = Color(0xFFD4F6FF)), it.start, it.end) }
        }
    }
    var layout by remember { mutableStateOf<TextLayoutResult?>(null) }
    var flash by remember { mutableStateOf<IntRange?>(null) }
    val haptic = LocalHapticFeedback.current
    fun hit(pos: Offset) {
        val l = layout ?: return
        val off = l.getOffsetForPosition(pos)
        val span = spans.firstOrNull { off in it.start until it.end }
        val range = span?.let { it.start until it.end } ?: Glossary.wordAt(text, off) ?: return
        val word = text.substring(range.first, range.last + 1)
        flash = range
        haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
        lookup.open(word, span?.term ?: lookup.glossary.lookup(word), Glossary.sentenceAt(text, off))
    }
    LaunchedEffect(flash) { if (flash != null) { delay(700); flash = null } }
    Text(
        annotated,
        modifier
            .pointerInput(text) { detectTapGestures(onTap = { hit(it) }, onLongPress = { hit(it) }) }
            .drawBehind {
                val l = layout ?: return@drawBehind
                val dash = PathEffect.dashPathEffect(floatArrayOf(2.dp.toPx(), 2.5.dp.toPx()))
                fun underline(start: Int, end: Int, c: Color, fill: Boolean) {
                    if (end <= start || end > l.layoutInput.text.length) return
                    val first = l.getLineForOffset(start); val last = l.getLineForOffset(end - 1)
                    for (line in first..last) {
                        val x1 = if (line == first) l.getHorizontalPosition(start, true) else l.getLineLeft(line)
                        val x2 = if (line == last) l.getHorizontalPosition(end, true) else l.getLineRight(line)
                        if (fill) drawRoundRect(c, Offset(minOf(x1, x2) - 2.dp.toPx(), l.getLineTop(line)),
                            androidx.compose.ui.geometry.Size(kotlin.math.abs(x2 - x1) + 4.dp.toPx(), l.getLineBottom(line) - l.getLineTop(line)),
                            androidx.compose.ui.geometry.CornerRadius(4.dp.toPx()))
                        else { val y = l.getLineBaseline(line) + 3.dp.toPx(); drawLine(c, Offset(x1, y), Offset(x2, y), 1.2.dp.toPx(), pathEffect = dash) }
                    }
                }
                flash?.let { underline(it.first, it.last + 1, tint.copy(alpha = 0.22f), true) }
                marked.forEach { underline(it.start, it.end, tint.copy(alpha = 0.55f), false) }
            },
        style = style, color = color, onTextLayout = { layout = it },
    )
}

/**
 * Bottom card explaining a tapped word. Slides up on a spring over a fading scrim; tap outside or
 * press back to close. [visible] drives the animation; the word stays on screen while it slides away.
 */
@Composable
fun BoxScope.LookupCard(visible: Boolean, word: String, term: Term?, context: String, online: Boolean, onClose: () -> Unit, onOpenGlossary: (() -> Unit)?) {
    val ctx = LocalContext.current
    val reduced = LocalReducedMotion.current
    BackHandler(enabled = visible, onBack = onClose)
    AnimatedVisibility(visible, Modifier.matchParentSize(), enter = fadeIn(tween(Motion.SHORT)), exit = fadeOut(tween(180))) {
        Box(
            Modifier.fillMaxSize().background(Color(0x99000000))
                .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null, onClick = onClose)
                .testTag("term_scrim")
        )
    }
    AnimatedVisibility(
        visible, Modifier.align(Alignment.BottomCenter),
        enter = if (reduced) fadeIn(tween(0)) else slideInVertically(Motion.settle()) { it } + fadeIn(tween(Motion.SHORT)),
        exit = if (reduced) fadeOut(tween(0)) else slideOutVertically(tween(220, easing = Motion.Accelerate)) { it } + fadeOut(tween(180)),
    ) {
        Column(
            Modifier.fillMaxWidth()
                .windowInsetsPadding(WindowInsets.navigationBars)
                .padding(12.dp)
                .clip(RoundedCornerShape(24.dp))
                .background(Color(0xFA0D1824))
                .border(1.dp, Ice.Cyan.copy(alpha = 0.45f), RoundedCornerShape(24.dp))
                .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) {}
                .padding(20.dp)
                .testTag("term_popup"),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Hud(if (term != null) "Meaning" else "Word", modifier = Modifier.weight(1f))
                Text("✕", color = Ice.Mist, style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.clip(RoundedCornerShape(50)).clickable(onClick = onClose).padding(horizontal = 12.dp, vertical = 4.dp).testTag("term_close"))
            }
            Spacer(Modifier.height(4.dp))
            Text(term?.term ?: word, style = MaterialTheme.typography.headlineSmall, color = Ice.Frost)
            Spacer(Modifier.height(10.dp))
            if (term != null) {
                Text(term.plain, style = MaterialTheme.typography.bodyLarge, color = Ice.Frost.copy(alpha = 0.92f))
                Spacer(Modifier.height(6.dp))
                Text("Simplified for learning. The lessons give the exact legal detail.", style = MaterialTheme.typography.bodyMedium, color = Ice.Dim)
            } else {
                Text("This isn't in the glossary, so it's most likely everyday English rather than a legal or business term.", style = MaterialTheme.typography.bodyLarge, color = Ice.Mist)
            }
            Spacer(Modifier.height(14.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (term == null) IceButton(
                    if (online) "Ask Claude" else "Offline", enabled = online, color = Ice.Aurora, modifier = Modifier.weight(1f).testTag("term_ask"),
                    onClick = { openExternal(ctx, Study.claudeUrl("Explain in very simple words, for someone with zero background in law or business, what \"$word\" means here: \"$context\"")) },
                )
                if (term != null && onOpenGlossary != null) IceButton("All terms", onClick = onOpenGlossary, primary = false, modifier = Modifier.weight(1f))
                IceButton("Got it", onClick = onClose, modifier = Modifier.weight(1f))
            }
        }
    }
}
