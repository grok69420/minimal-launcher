package com.abhi.startuplaw.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameMillis
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.abhi.startuplaw.ui.theme.Ice
import com.abhi.startuplaw.ui.theme.LocalReducedMotion
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** Night-ice backdrop: deep gradient, a cold glow, and slow drifting ice motes. */
@Composable
fun IceBackground(particles: Boolean = false, content: @Composable BoxScope.() -> Unit) {
    Box(
        Modifier.fillMaxSize().background(
            Brush.verticalGradient(0f to Color(0xFF07101A), 0.45f to Ice.Night, 1f to Color(0xFF04060A))
        )
    ) {
        Canvas(Modifier.fillMaxSize()) {
            drawCircle(
                Brush.radialGradient(listOf(Ice.CyanDeep.copy(alpha = 0.16f), Color.Transparent), center = Offset(size.width * 0.85f, -size.height * 0.02f), radius = size.width * 0.9f),
                radius = size.width * 0.9f, center = Offset(size.width * 0.85f, -size.height * 0.02f),
            )
            drawCircle(
                Brush.radialGradient(listOf(Ice.Aurora.copy(alpha = 0.07f), Color.Transparent), center = Offset(0f, size.height * 0.55f), radius = size.width * 0.8f),
                radius = size.width * 0.8f, center = Offset(0f, size.height * 0.55f),
            )
        }
        if (particles && !LocalReducedMotion.current) Motes()
        content()
    }
}

private class Mote(val x: Float, val y: Float, val r: Float, val speed: Float, val phase: Float, val a: Float)

@Composable
private fun Motes() {
    val motes = remember {
        val rnd = kotlin.random.Random(7)
        List(46) { Mote(rnd.nextFloat(), rnd.nextFloat(), 0.6f + rnd.nextFloat() * 1.8f, 0.004f + rnd.nextFloat() * 0.012f, rnd.nextFloat() * 6.28f, 0.15f + rnd.nextFloat() * 0.45f) }
    }
    var t by remember { mutableLongStateOf(0L) }
    LaunchedEffect(Unit) { while (true) withFrameMillis { t = it } }
    Canvas(Modifier.fillMaxSize().graphicsLayer()) {
        val sec = t / 1000f
        motes.forEach { m ->
            val y = ((m.y - sec * m.speed) % 1f + 1f) % 1f
            val x = m.x + sin(sec * 0.3f + m.phase) * 0.01f
            val tw = 0.6f + 0.4f * sin(sec * 1.3f + m.phase)
            drawCircle(Ice.Frost.copy(alpha = m.a * tw), m.r.dp.toPx(), Offset(x * size.width, y * size.height))
        }
    }
}

/** Standard screen: HUD top bar with back, then a lazily laid-out column. */
@Composable
fun Screen(
    title: String,
    hud: String,
    onBack: (() -> Unit)?,
    modifier: Modifier = Modifier,
    state: LazyListState = rememberLazyListState(),
    actions: @Composable () -> Unit = {},
    bottomPad: Int = 120,
    particles: Boolean = false,
    content: LazyListScope.() -> Unit,
) {
    IceBackground(particles) {
        Column(Modifier.fillMaxSize()) {
            TopBar(title, hud, onBack, actions)
            LazyColumn(
                modifier.fillMaxSize().testTag("list"),
                state = state,
                contentPadding = PaddingValues(start = 18.dp, end = 18.dp, top = 6.dp, bottom = bottomPad.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                content = content,
            )
        }
    }
}

@Composable
fun TopBar(title: String, hud: String, onBack: (() -> Unit)?, actions: @Composable () -> Unit = {}) {
    Row(
        Modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.statusBars).padding(start = 6.dp, end = 10.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (onBack != null) {
            Box(
                Modifier.size(48.dp).clip(CircleShape).clickable(role = Role.Button, onClick = onBack).semantics { contentDescription = "Back" }.testTag("back"),
                contentAlignment = Alignment.Center,
            ) { Icon(Glyph.Back, Ice.Frost) }
        } else Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f).padding(start = 4.dp)) {
            Hud(hud, color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
            Text(title, style = MaterialTheme.typography.titleLarge, color = Ice.Frost, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        actions()
    }
}

/** Hand-drawn line glyphs (no icon font needed, crisp at any size). */
enum class Glyph { Back, Library, Cases, Playbook, Practice, Map, Search, Sync, Check, Chevron, Spark, Info }

@Composable
fun Icon(g: Glyph, color: Color, size: androidx.compose.ui.unit.Dp = 22.dp) {
    Canvas(Modifier.size(size)) { drawGlyph(g, color) }
}

fun DrawScope.drawGlyph(g: Glyph, c: Color) {
    val w = size.width; val h = size.height
    val s = Stroke(width = w * 0.085f, cap = StrokeCap.Round, join = StrokeJoin.Round)
    fun p(vararg pts: Pair<Float, Float>, close: Boolean = false) = Path().apply {
        pts.forEachIndexed { i, (x, y) -> if (i == 0) moveTo(x * w, y * h) else lineTo(x * w, y * h) }
        if (close) close()
    }
    when (g) {
        Glyph.Back -> drawPath(p(0.62f to 0.2f, 0.32f to 0.5f, 0.62f to 0.8f), c, style = s)
        Glyph.Chevron -> drawPath(p(0.4f to 0.22f, 0.68f to 0.5f, 0.4f to 0.78f), c, style = s)
        Glyph.Library -> {
            drawPath(p(0.2f to 0.18f, 0.2f to 0.82f), c, style = s)
            drawPath(p(0.42f to 0.26f, 0.42f to 0.82f), c, style = s)
            drawPath(p(0.6f to 0.2f, 0.82f to 0.8f), c, style = s)
            drawPath(p(0.12f to 0.88f, 0.9f to 0.88f), c, style = s)
        }
        Glyph.Cases -> { // scales
            drawPath(p(0.5f to 0.14f, 0.5f to 0.86f), c, style = s)
            drawPath(p(0.18f to 0.28f, 0.82f to 0.28f), c, style = s)
            drawPath(p(0.18f to 0.28f, 0.08f to 0.56f, 0.3f to 0.56f, close = true), c, style = s)
            drawPath(p(0.82f to 0.28f, 0.72f to 0.56f, 0.94f to 0.56f, close = true), c, style = s)
            drawPath(p(0.32f to 0.86f, 0.68f to 0.86f), c, style = s)
        }
        Glyph.Playbook -> { // flag on a peak
            drawPath(p(0.08f to 0.86f, 0.4f to 0.36f, 0.6f to 0.62f, 0.72f to 0.5f, 0.94f to 0.86f), c, style = s)
            drawPath(p(0.4f to 0.36f, 0.4f to 0.1f, 0.62f to 0.18f, 0.4f to 0.26f), c, style = s)
        }
        Glyph.Practice -> { // two cards
            drawPath(p(0.14f to 0.3f, 0.62f to 0.3f, 0.62f to 0.86f, 0.14f to 0.86f, close = true), c, style = s)
            drawPath(p(0.32f to 0.14f, 0.86f to 0.14f, 0.86f to 0.7f), c, style = s)
        }
        Glyph.Map -> { // constellation
            val pts = listOf(0.5f to 0.5f, 0.18f to 0.22f, 0.84f to 0.2f, 0.2f to 0.82f, 0.82f to 0.8f)
            pts.drop(1).forEach { drawPath(p(pts[0], it), c, style = s) }
            pts.forEach { (x, y) -> drawCircle(c, w * 0.09f, Offset(x * w, y * h)) }
        }
        Glyph.Search -> {
            drawCircle(c, w * 0.26f, Offset(w * 0.44f, h * 0.44f), style = s)
            drawPath(p(0.64f to 0.64f, 0.88f to 0.88f), c, style = s)
        }
        Glyph.Sync -> {
            drawArc(c, 200f, 250f, false, topLeft = Offset(w * 0.18f, h * 0.18f), size = androidx.compose.ui.geometry.Size(w * 0.64f, h * 0.64f), style = s)
            drawPath(p(0.66f to 0.1f, 0.8f to 0.28f, 0.6f to 0.36f), c, style = s)
        }
        Glyph.Check -> drawPath(p(0.18f to 0.52f, 0.42f to 0.76f, 0.84f to 0.26f), c, style = s)
        Glyph.Spark -> { // six-point ice crystal
            for (i in 0 until 3) {
                val a = PI.toFloat() / 3f * i + PI.toFloat() / 2f
                drawLine(c, Offset(w / 2 + cos(a) * w * 0.4f, h / 2 + sin(a) * h * 0.4f), Offset(w / 2 - cos(a) * w * 0.4f, h / 2 - sin(a) * h * 0.4f), w * 0.08f, StrokeCap.Round)
            }
        }
        Glyph.Info -> {
            drawCircle(c, w * 0.4f, Offset(w / 2, h / 2), style = s)
            drawPath(p(0.5f to 0.46f, 0.5f to 0.72f), c, style = s)
            drawCircle(c, w * 0.05f, Offset(w / 2, h * 0.32f))
        }
    }
}
