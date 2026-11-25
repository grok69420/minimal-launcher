package com.abhi.startuplaw.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animate
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculateCentroid
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.geometry.isSpecified
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathMeasure
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChanged
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.abhi.startuplaw.ui.components.Conceal
import com.abhi.startuplaw.ui.components.FrostCard
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.IceButton
import com.abhi.startuplaw.ui.components.Motion
import com.abhi.startuplaw.ui.components.Reveal
import com.abhi.startuplaw.ui.theme.Ice
import com.abhi.startuplaw.ui.theme.LocalReducedMotion
import com.abhi.startuplaw.ui.theme.Mono
import kotlinx.coroutines.launch
import kotlin.math.PI
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

/** One dew drop on the web: a lesson, story or quiz question. */
private class Drop(val b: Int, val j: Int, val pos: Offset, val r: Float, val leaf: Leaf, val order: Float)

/** The web's fixed geometry for one canvas size; motion is applied on top while drawing. */
private class Geo(
    val c: Offset, val rMin: Float, val rMax: Float, val step: Float,
    val angles: FloatArray, val drops: List<Drop>,
    val spiral: List<Offset>, val spiralSpoke: IntArray, val ends: List<Offset>,
)

private const val TURNS = 7

private fun buildGeo(bs: List<Branch>, w: Float, h: Float, dp: Float): Geo {
    val c = Offset(w / 2f, h / 2f)
    val rMax = minOf(w, h) * 0.41f
    val rMin = minOf(w, h) * 0.13f
    val n = bs.size.coerceAtLeast(1)
    val step = (2.0 * PI / n).toFloat()
    val angles = FloatArray(n) { -PI.toFloat() / 2f + step * it }
    val spiral = ArrayList<Offset>()
    val spokeOf = ArrayList<Int>()
    val r0 = rMin * 1.18f
    for (k in 0 until TURNS) for (i in 0 until n) {
        val f = (k + i / n.toFloat()) / TURNS
        val r = r0 + (rMax - r0) * f
        spiral += c + Offset(cos(angles[i]), sin(angles[i])) * r
        spokeOf += i
    }
    val drops = ArrayList<Drop>()
    bs.forEachIndexed { i, b ->
        val m = b.leaves.size
        b.leaves.forEachIndexed { j, l ->
            val t = (j + 1f) / (m + 1f)
            val r = rMin * 1.3f + (rMax - rMin * 1.3f) * t
            drops += Drop(i, j, c + Offset(cos(angles[i]), sin(angles[i])) * r, (if (b.small) 1.6f else 3.3f) * dp, l, t)
        }
    }
    val ends = angles.map { c + Offset(cos(it), sin(it)) * (rMax * 1.07f) }
    return Geo(c, rMin, rMax, step, angles, drops, spiral, spokeOf.toIntArray(), ends)
}

private fun back(x: Float): Float { val c1 = 1.70158f; val y = x - 1f; return 1f + (c1 + 1f) * y * y * y + c1 * y * y }

private fun Offset.unit(): Offset { val d = getDistance(); return if (d < 0.001f) Offset.Zero else this / d }

private fun clampOff(o: Offset, s: Float, w: Float, h: Float) = Offset(o.x.coerceIn(w - w * s, 0f), o.y.coerceIn(h - h * s, 0f))

/**
 * Progress drawn as a spider's web. One radial thread per volume, a capture spiral that catches light where you have
 * learned things, and a dew drop for every lesson, story and quiz question. It weaves itself in, sways in a soft breeze,
 * and trembles from wherever you touch it. Tap a drop or a thread, pinch to zoom, double-tap to zoom in or out.
 */
@Composable
fun SpiderWeb(bs: List<Branch>, pct: Int, go: (String) -> Unit) {
    val reduced = LocalReducedMotion.current
    val density = LocalDensity.current
    val scope = rememberCoroutineScope()
    val tm = rememberTextMeasurer()

    var box by remember { mutableStateOf(IntSize.Zero) }
    val geo = remember(bs, box) { if (box.width == 0) null else buildGeo(bs, box.width.toFloat(), box.height.toFloat(), density.density) }
    val frac = remember(bs) { FloatArray(bs.size) { i -> bs[i].leaves.let { l -> if (l.isEmpty()) 0f else l.count { it.on } / l.size.toFloat() } } }

    var sel by remember { mutableStateOf<Pair<Int, Int>?>(null) }
    if (sel?.let { (i, j) -> i >= bs.size || j >= bs[i].leaves.size } == true) sel = null
    var sc by remember { mutableFloatStateOf(1f) }
    var off by remember { mutableStateOf(Offset.Zero) }
    var pluckAt by remember { mutableStateOf(Offset.Zero) }

    val weave = remember { Animatable(if (reduced) 1f else 0f) }
    LaunchedEffect(Unit) { if (!reduced) weave.animateTo(1f, tween(2600, easing = LinearEasing)) }
    val woven by remember { derivedStateOf { weave.value >= 1f } }
    val pluck = remember { Animatable(1f) }
    val time = if (reduced) null else rememberInfiniteTransition(label = "web")
        .animateFloat(0f, 600f, infiniteRepeatable(tween(600_000, easing = LinearEasing)), label = "t")

    fun pluckFrom(p: Offset) {
        pluckAt = p
        if (!reduced) scope.launch { pluck.snapTo(0f); pluck.animateTo(1f, tween(1700, easing = LinearEasing)) }
    }
    fun zoomTo(ts: Float, to: Offset) {
        val s0 = sc; val o0 = off
        scope.launch {
            animate(0f, 1f, animationSpec = if (reduced) snap() else tween(420, easing = Motion.Emphasized)) { v, _ ->
                sc = s0 + (ts - s0) * v
                off = androidx.compose.ui.geometry.lerp(o0, to, v)
            }
        }
    }
    fun select(i: Int, j: Int) {
        val g = geo ?: return
        sel = i to j
        pluckFrom(if (j >= 0) g.drops.first { it.b == i && it.j == j }.pos else g.ends[i])
    }

    val labelStyle = remember { TextStyle(fontFamily = Mono, fontSize = 11.sp, letterSpacing = 1.sp) }
    val labels: List<TextLayoutResult> = remember(bs, tm) {
        bs.map { b -> tm.measure(if (b.vol.isNotBlank()) b.vol else if (b.small) "Q" else "★", labelStyle) }
    }
    val pctText = remember(pct, tm) { tm.measure("$pct%", TextStyle(fontSize = 19.sp, fontWeight = FontWeight.Light)) }
    val learnedText = remember(tm) { tm.measure("LEARNED", TextStyle(fontFamily = Mono, fontSize = 7.sp, letterSpacing = 1.2.sp)) }

    Column(Modifier.fillMaxWidth()) {
        Box(
            Modifier.fillMaxWidth().aspectRatio(1f).testTag("constellation")
                .clip(RoundedCornerShape(24.dp))
                .semantics {
                    contentDescription = "Progress web, $pct percent learned. Use the volume buttons below to explore it."
                    stateDescription = if (woven) "ready" else "weaving"
                }
                .onSizeChanged { box = it }
                .pointerInput(box) {
                    // Pinch with two fingers to zoom; once zoomed, one finger pans. Unzoomed, one finger scrolls the page.
                    awaitEachGesture {
                        awaitFirstDown(requireUnconsumed = false)
                        var acc = Offset.Zero
                        var panning = false
                        do {
                            val ev = awaitPointerEvent()
                            val fingers = ev.changes.count { it.pressed }
                            if (fingers >= 2 || sc > 1.02f) {
                                val z = ev.calculateZoom()
                                val p = ev.calculatePan()
                                if (fingers >= 2) panning = true
                                acc += p
                                if (acc.getDistance() > viewConfiguration.touchSlop) panning = true
                                if (panning && (z != 1f || p != Offset.Zero)) {
                                    val cen = ev.calculateCentroid(useCurrent = false)
                                    val ns = (sc * z).coerceIn(1f, 3.5f)
                                    val no = if (cen.isSpecified) cen - (cen - off) * (ns / sc) + p else off + p
                                    sc = ns
                                    off = clampOff(no, ns, size.width.toFloat(), size.height.toFloat())
                                    ev.changes.forEach { if (it.positionChanged()) it.consume() }
                                }
                            }
                        } while (ev.changes.any { it.pressed })
                    }
                }
                .pointerInput(geo) {
                    detectTapGestures(
                        onDoubleTap = { pos ->
                            if (sc > 1.05f) zoomTo(1f, Offset.Zero)
                            else zoomTo(2.4f, clampOff(pos - (pos - off) * (2.4f / sc), 2.4f, size.width.toFloat(), size.height.toFloat()))
                        },
                        onTap = { pos ->
                            val g = geo ?: return@detectTapGestures
                            val world = (pos - off) / sc
                            val hit = g.drops.minByOrNull { (it.pos - world).getDistanceSquared() }
                            val tol = 22.dp.toPx() / sc
                            val d = world - g.c
                            val dist = d.getDistance()
                            when {
                                hit != null && (hit.pos - world).getDistance() < tol -> { sel = hit.b to hit.j; pluckFrom(hit.pos) }
                                dist < g.rMin * 0.9f -> { sel = null; pluckFrom(g.c) }
                                dist < g.rMax * 1.2f && bs.isNotEmpty() -> {
                                    val a = atan2(d.y, d.x) + PI.toFloat() / 2f
                                    val i = ((a / g.step).roundToInt() % bs.size + bs.size) % bs.size
                                    sel = i to -1
                                    pluckFrom(world)
                                }
                                else -> sel = null
                            }
                        },
                    )
                },
        ) {
            Canvas(Modifier.fillMaxSize()) {
                val g = geo ?: return@Canvas
                val w = weave.value
                val t = time?.value ?: 0f
                val pl = pluck.value
                withTransform({ translate(off.x, off.y); scale(sc, sc, pivot = Offset.Zero) }) {
                    drawWeb(g, bs, frac, sel, w, t, pl, pluckAt, reduced, sc, labels, pctText, learnedText, pct)
                }
            }
        }
        Spacer(Modifier.height(10.dp))
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            bs.forEachIndexed { i, b ->
                val on = sel?.first == i
                val shape = RoundedCornerShape(50)
                Row(
                    Modifier.testTag("web_chip_${b.id}")
                        .clip(shape)
                        .background(if (on) b.color.copy(alpha = 0.18f) else Color.Transparent)
                        .border(1.dp, if (on) b.color else Ice.Edge, shape)
                        .clickable(role = Role.Button) { select(i, -1) }
                        .semantics { contentDescription = b.title }
                        .padding(horizontal = 10.dp, vertical = 7.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(Modifier.size(7.dp).clip(CircleShape).background(b.color.copy(alpha = 0.35f + 0.65f * frac.getOrElse(i) { 0f })))
                    Spacer(Modifier.width(6.dp))
                    Text(
                        if (b.vol.isNotBlank()) "Vol. ${b.vol}" else if (b.small) "Quiz" else "Stories",
                        style = MaterialTheme.typography.labelMedium, color = if (on) Ice.Frost else Ice.Mist,
                    )
                }
            }
        }
        Spacer(Modifier.height(6.dp))
        Hud("Tap a drop · pinch to zoom · double-tap to zoom", color = Ice.Dim, style = MaterialTheme.typography.labelSmall)

        var shown by remember { mutableStateOf<Pair<Int, Int>?>(null) }
        if (sel != null && shown != sel) shown = sel
        AnimatedVisibility(visible = sel != null, enter = Reveal, exit = Conceal) {
            val s = shown
            if (s != null && s.first < bs.size) {
                val b = bs[s.first]
                val leaf = b.leaves.getOrNull(s.second)
                val done = b.leaves.count { it.on }
                Column {
                    Spacer(Modifier.height(10.dp))
                    FrostCard(Modifier.fillMaxWidth().testTag("web_info"), accent = b.color) {
                        Hud(if (b.vol.isNotBlank()) "Vol. ${b.vol} · ${b.title}" else b.title, color = b.color, style = MaterialTheme.typography.labelSmall)
                        Spacer(Modifier.height(6.dp))
                        Text(leaf?.title ?: "$done of ${b.leaves.size} learned", style = MaterialTheme.typography.titleMedium, color = Ice.Frost,
                            maxLines = 3, overflow = TextOverflow.Ellipsis)
                        Spacer(Modifier.height(4.dp))
                        Text(
                            when {
                                leaf == null -> "Every glowing drop on this thread is something you have learned."
                                leaf.on -> "Learned. This drop is glowing."
                                else -> "Not learned yet. Open it to light up this drop."
                            },
                            style = MaterialTheme.typography.bodyMedium, color = Ice.Mist,
                        )
                        Spacer(Modifier.height(12.dp))
                        IceButton(if (leaf != null) "Open" else if (b.vol.isNotBlank()) "Open volume" else "Open section", { go(leaf?.route ?: b.route) }, Modifier.testTag("web_open"), color = b.color)
                    }
                }
            }
        }
    }
}

private fun DrawScope.drawWeb(
    g: Geo, bs: List<Branch>, frac: FloatArray, sel: Pair<Int, Int>?,
    w: Float, t: Float, pl: Float, pluckAt: Offset, reduced: Boolean, sc: Float,
    labels: List<TextLayoutResult>, pctText: TextLayoutResult, learnedText: TextLayoutResult, pct: Int,
) {
    val dp = density
    val thin = 1f * dp / sqrt(sc)
    val n = bs.size
    if (n == 0) return
    val c = g.c
    val swayAmp = if (reduced) 0f else 2.4f * dp
    val pluckAmp = 8f * dp
    val tau = pl * 1.7f
    val plucking = !reduced && pl < 1f

    // Soft breeze plus a ripple travelling out from the last touch, stronger towards the rim.
    fun m(p: Offset): Offset {
        var q = p
        if (swayAmp > 0f) {
            val k = ((p - c).getDistance() / g.rMax).coerceAtMost(1.2f)
            q += Offset(sin(t * 0.8f + p.y * 0.011f), cos(t * 0.65f + p.x * 0.013f)) * (swayAmp * k)
        }
        if (plucking) {
            val v = p - pluckAt
            val dist = v.getDistance().coerceAtLeast(1f)
            val a = pluckAmp * exp(-3f * tau) * sin(dist * 0.045f - tau * 16f) * exp(-dist / (g.rMax * 0.9f))
            q += (v / dist) * a
        }
        return q
    }

    val spokeP = Motion.Decelerate.transform((w / 0.30f).coerceIn(0f, 1f))
    val spiralP = ((w - 0.22f) / 0.50f).coerceIn(0f, 1f)
    val dewP = ((w - 0.62f) / 0.38f).coerceIn(0f, 1f)
    val focus = sel?.first
    fun dim(i: Int) = if (focus == null || focus == i) 1f else 0.38f

    // Faint glow behind the web.
    drawCircle(Brush.radialGradient(listOf(Ice.Cyan.copy(alpha = 0.10f), Color.Transparent), c, g.rMax * 1.3f), g.rMax * 1.3f, c)

    // Anchor threads tying the web to the corners of the frame.
    val corners = listOf(Offset(0f, 0f), Offset(size.width, 0f), Offset(0f, size.height), Offset(size.width, size.height))
    corners.forEach { k ->
        val ang = atan2(k.y - c.y, k.x - c.x)
        val i = g.angles.indices.minByOrNull { idx -> val d = ((g.angles[idx] - ang + 3f * PI.toFloat()) % (2f * PI.toFloat())) - PI.toFloat(); d * d } ?: 0
        val from = m(g.ends[i])
        val to = from + (k - from) * spokeP
        drawLine(Ice.Frost.copy(alpha = 0.09f), from, to, thin)
    }

    // Radial threads, one per volume, spun out from the hub.
    val pm = PathMeasure()
    for (i in 0 until n) {
        val path = Path().apply {
            val s = m(c); moveTo(s.x, s.y)
            for (q in g.spiral.indices) if (g.spiralSpoke[q] == i) { val p = m(g.spiral[q]); lineTo(p.x, p.y) }
            val e = m(g.ends[i]); lineTo(e.x, e.y)
        }
        val drawn = if (spokeP >= 1f) path else Path().also { seg -> pm.setPath(path, false); pm.getSegment(0f, pm.length * spokeP, seg, true) }
        val col = bs[i].color
        val a = (0.28f + 0.55f * frac[i]) * dim(i)
        drawPath(drawn, Brush.linearGradient(listOf(Ice.Cyan.copy(alpha = 0.10f), col.copy(alpha = a)), c, g.ends[i]),
            style = Stroke(if (focus == i) thin * 2f else thin * 1.3f))
    }

    // Capture spiral, spun from the outside in. Sectors you have learned in catch the light in that volume's colour.
    val segs = g.spiral.size - 1
    val first = (segs * (1f - spiralP)).toInt()
    for (q in first until segs) {
        val a = m(g.spiral[q]); val b = m(g.spiral[q + 1])
        val mid = (a + b) / 2f
        val ctrl = mid + (c - mid).unit() * ((b - a).getDistance() * 0.16f)
        val i = g.spiralSpoke[q]
        val col = lerp(Ice.Mist.copy(alpha = 0.16f), bs[i].color.copy(alpha = 0.62f), frac[i])
        val p = Path().apply { moveTo(a.x, a.y); quadraticBezierTo(ctrl.x, ctrl.y, b.x, b.y) }
        drawPath(p, col.copy(alpha = col.alpha * dim(i)), style = Stroke(thin))
    }

    // A glint of light running along the spiral.
    if (!reduced && w >= 1f && segs > 0) {
        val f = (t * 2.2f) % segs
        val q = f.toInt().coerceIn(0, segs - 1)
        val p = androidx.compose.ui.geometry.lerp(m(g.spiral[q]), m(g.spiral[q + 1]), f - q)
        drawCircle(Brush.radialGradient(listOf(Color.White.copy(alpha = 0.55f), Color.Transparent), p, 7f * dp), 7f * dp, p)
    }

    // The hub: a tight free spiral that slowly turns.
    if (spokeP > 0f) {
        val hub = Path()
        val steps = 90
        for (s in 0..steps) {
            val u = s / steps.toFloat()
            val ang = u * 3f * 2f * PI.toFloat() + t * 0.05f
            val r = g.rMin * (0.70f + 0.42f * u)
            val p = m(c + Offset(cos(ang), sin(ang)) * r)
            if (s == 0) hub.moveTo(p.x, p.y) else hub.lineTo(p.x, p.y)
        }
        drawPath(hub, Ice.Frost.copy(alpha = 0.16f * spokeP), style = Stroke(thin))
    }

    // Dew drops: lit ones glow with a highlight, unlearned ones are hollow beads.
    g.drops.forEach { d ->
        val local = ((dewP - d.order * 0.55f) / 0.45f).coerceIn(0f, 1f)
        if (local <= 0f) return@forEach
        val s = if (reduced) 1f else back(local)
        val p = m(d.pos)
        val r = d.r * s
        val col = bs[d.b].color
        val k = dim(d.b)
        if (d.leaf.on) {
            val shimmer = if (reduced) 0.5f else 0.5f + 0.5f * sin(t * 2.1f + d.pos.x * 0.07f + d.pos.y * 0.05f)
            drawCircle(Brush.radialGradient(listOf(col.copy(alpha = (0.42f + 0.28f * shimmer) * k), Color.Transparent), p, r * 3.4f), r * 3.4f, p)
            drawCircle(lerp(col, Ice.Frost, 0.55f).copy(alpha = k), r * 0.8f, p)
            drawCircle(Color.White.copy(alpha = 0.9f * k), r * 0.26f, p + Offset(-r * 0.28f, -r * 0.28f))
        } else {
            drawCircle(Ice.Night.copy(alpha = 0.9f), r * 0.75f, p)
            drawCircle(col.copy(alpha = 0.55f * k), r * 0.75f, p, style = Stroke(thin))
        }
        if (sel != null && sel.first == d.b && sel.second == d.j) {
            val beat = if (reduced) 0f else sin(t * 4f)
            drawCircle(Ice.Frost.copy(alpha = 0.85f), r * (2.4f + 0.4f * beat) + 3f * dp, p, style = Stroke(thin * 1.4f))
        }
    }

    // Volume numerals at the end of each thread.
    for (i in 0 until n) {
        val lay = labels.getOrNull(i) ?: continue
        val dir = (g.ends[i] - c).unit()
        val p = m(g.ends[i]) + dir * (12f * dp)
        drawText(lay, color = bs[i].color.copy(alpha = (0.45f + 0.55f * frac[i]) * dim(i) * spokeP),
            topLeft = p - Offset(lay.size.width / 2f, lay.size.height / 2f))
    }

    // Centre: how much of the whole web is lit.
    val hc = m(c)
    val hr = g.rMin * 0.62f
    drawCircle(Brush.radialGradient(listOf(Ice.Cyan.copy(alpha = 0.22f), Color.Transparent), hc, hr * 2f), hr * 2f, hc)
    drawCircle(Ice.Night, hr, hc)
    drawCircle(Ice.Cyan.copy(alpha = 0.45f), hr, hc, style = Stroke(thin))
    val sweep = 360f * pct / 100f * Motion.Decelerate.transform((w / 0.6f).coerceIn(0f, 1f))
    drawArc(Ice.Cyan, -90f, sweep, false, topLeft = hc - Offset(hr, hr), size = Size(hr * 2f, hr * 2f), style = Stroke(2.5f * dp))
    drawText(pctText, color = Ice.Frost, topLeft = hc - Offset(pctText.size.width / 2f, pctText.size.height * 0.62f))
    drawText(learnedText, color = Ice.Dim, topLeft = hc + Offset(-learnedText.size.width / 2f, pctText.size.height * 0.30f))
}
