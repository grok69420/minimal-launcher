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
import com.abhi.startuplaw.data.Badge
import com.abhi.startuplaw.data.Glossary
import com.abhi.startuplaw.data.Level
import com.abhi.startuplaw.data.Reward
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

/** Bottom card explaining a tapped word. Tap outside or press back to close. */
@Composable
fun BoxScope.LookupCard(word: String, term: Term?, context: String, online: Boolean, onClose: () -> Unit, onOpenGlossary: (() -> Unit)?) {
    val ctx = LocalContext.current
    BackHandler(onBack = onClose)
    Box(
        Modifier.fillMaxSize().background(Color(0x99000000))
            .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null, onClick = onClose)
            .testTag("term_scrim")
    )
    Column(
        Modifier.align(Alignment.BottomCenter).fillMaxWidth()
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

/** Floating "+20 XP", badge toasts and a level-up burst. Never blocks touches. */
@Composable
fun BoxScope.Celebrations(rewards: kotlinx.coroutines.flow.SharedFlow<Reward>) {
    val haptic = LocalHapticFeedback.current
    val reduced = LocalReducedMotion.current
    val pops = remember { mutableStateListOf<Reward>() }
    var levelUp by remember { mutableStateOf<Level?>(null) }
    val badges = remember { mutableStateListOf<Badge>() }
    LaunchedEffect(rewards) {
        rewards.collect { r ->
            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
            pops += r
            r.levelUp?.let { levelUp = it }
            badges += r.badges
            launch { delay(1400); pops.remove(r) }
        }
    }
    LaunchedEffect(levelUp) { if (levelUp != null) { delay(2400); levelUp = null } }
    LaunchedEffect(badges.size) { if (badges.isNotEmpty()) { delay(2600); badges.removeAt(0) } }

    Column(Modifier.align(Alignment.TopCenter).windowInsetsPadding(WindowInsets.statusBars).padding(top = 60.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        pops.takeLast(2).forEach { r -> key(r.id) { XpPop(r.xp, reduced) } }
        AnimatedVisibility(badges.isNotEmpty(), enter = fadeIn() + slideInVertically { -it }, exit = fadeOut() + slideOutVertically { -it }) {
            badges.firstOrNull()?.let { b ->
                Row(
                    Modifier.padding(top = 8.dp).clip(RoundedCornerShape(50)).background(Color(0xF01A1430)).border(1.dp, Ice.Aurora, RoundedCornerShape(50))
                        .padding(horizontal = 16.dp, vertical = 10.dp).testTag("badge_toast"),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Glyph.Spark, Ice.Aurora, 18.dp)
                    Spacer(Modifier.width(10.dp))
                    Column {
                        Hud("Badge unlocked", color = Ice.Aurora, style = MaterialTheme.typography.labelSmall)
                        Text(b.title, style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
                    }
                }
            }
        }
    }
    levelUp?.let { lv -> key(lv.index) { LevelUpBurst(lv, reduced) } }
}

@Composable
private fun XpPop(xp: Int, reduced: Boolean) {
    val a = remember { Animatable(0f) }
    LaunchedEffect(Unit) { a.animateTo(1f, tween(if (reduced) 1 else 1300, easing = FastOutSlowInEasing)) }
    Box(
        Modifier.padding(top = 4.dp)
            .graphicsLayer { translationY = -40.dp.toPx() * a.value; alpha = if (a.value < 0.7f) 1f else (1f - (a.value - 0.7f) / 0.3f); val s = 0.85f + 0.15f * minOf(1f, a.value * 4); scaleX = s; scaleY = s }
            .clip(RoundedCornerShape(50)).background(Ice.Cyan).padding(horizontal = 16.dp, vertical = 8.dp)
            .testTag("xp_pop"),
    ) { Text("+$xp XP", style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold), color = Ice.OnCyan) }
}

@Composable
private fun BoxScope.LevelUpBurst(lv: Level, reduced: Boolean) {
    val t = remember { Animatable(0f) }
    LaunchedEffect(Unit) { t.animateTo(1f, tween(if (reduced) 1 else 1800, easing = FastOutSlowInEasing)) }
    val shards = remember { List(48) { i -> Triple(i * 7.5f + (i % 3) * 2f, 0.55f + (i * 37 % 45) / 100f, i % 4) } }
    Canvas(Modifier.fillMaxSize()) {
        if (reduced) return@Canvas
        val c = Offset(size.width / 2, size.height * 0.42f)
        val p = t.value
        val alpha = (1f - p).coerceIn(0f, 1f)
        drawCircle(Ice.Cyan.copy(alpha = 0.18f * alpha), size.minDimension * 0.6f * p, c)
        shards.forEach { (deg, speed, kind) ->
            val r = Math.toRadians(deg.toDouble())
            val d = size.minDimension * 0.55f * speed * p
            val pos = c + Offset((cos(r) * d).toFloat(), (sin(r) * d).toFloat())
            val col = listOf(Ice.Cyan, Ice.Frost, Ice.Aurora, Ice.Mint)[kind].copy(alpha = alpha)
            val tail = c + Offset((cos(r) * d * 0.82f).toFloat(), (sin(r) * d * 0.82f).toFloat())
            drawLine(col, tail, pos, 3.dp.toPx())
        }
    }
    Column(
        Modifier.align(Alignment.Center).graphicsLayer { alpha = if (t.value < 0.85f) 1f else (1f - t.value) / 0.15f }
            .clip(RoundedCornerShape(24.dp)).background(Color(0xF00A1520)).border(1.dp, Ice.Cyan, RoundedCornerShape(24.dp))
            .padding(horizontal = 28.dp, vertical = 20.dp).testTag("level_up"),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Hud("Level up")
        Text(lv.name, style = MaterialTheme.typography.displaySmall, color = Ice.Frost)
    }
}
