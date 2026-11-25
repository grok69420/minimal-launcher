package com.abhi.startuplaw.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.abhi.startuplaw.ui.components.FrostCard
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.IceButton
import com.abhi.startuplaw.ui.theme.Ice
import com.abhi.startuplaw.ui.theme.Mono
import kotlin.math.PI
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

private class Dot(val b: Int, val j: Int, val pos: Offset, val r: Float, val leaf: Leaf)

private class Geo(val c: Offset, val rMin: Float, val rMax: Float, val step: Float, val angles: FloatArray, val dots: List<Dot>, val ends: List<Offset>)

private fun buildGeo(bs: List<Branch>, w: Float, h: Float, dp: Float): Geo {
    val c = Offset(w / 2f, h / 2f)
    val rMax = minOf(w, h) * 0.40f
    val rMin = minOf(w, h) * 0.13f
    val n = bs.size.coerceAtLeast(1)
    val step = (2.0 * PI / n).toFloat()
    val angles = FloatArray(n) { -PI.toFloat() / 2f + step * it }
    val dots = ArrayList<Dot>()
    bs.forEachIndexed { i, b ->
        val m = b.leaves.size
        val dir = Offset(cos(angles[i]), sin(angles[i]))
        b.leaves.forEachIndexed { j, l ->
            val r = rMin * 1.25f + (rMax - rMin * 1.25f) * (j + 1f) / (m + 1f)
            dots += Dot(i, j, c + dir * r, (if (b.small) 1.6f else 3.2f) * dp, l)
        }
    }
    return Geo(c, rMin, rMax, step, angles, dots, angles.map { c + Offset(cos(it), sin(it)) * rMax })
}

/**
 * Minimal, still mind map of progress: one line per volume, a dot per lesson, story or quiz question
 * (filled = learned). Tap a dot or a line to see what it is.
 */
@Composable
fun SpiderWeb(bs: List<Branch>, pct: Int, go: (String) -> Unit) {
    val density = LocalDensity.current.density
    val tm = rememberTextMeasurer()
    var box by remember { mutableStateOf(IntSize.Zero) }
    val geo = remember(bs, box) { if (box.width == 0) null else buildGeo(bs, box.width.toFloat(), box.height.toFloat(), density) }
    var sel by remember { mutableStateOf<Pair<Int, Int>?>(null) }
    if (sel?.let { (i, j) -> i >= bs.size || j >= bs[i].leaves.size } == true) sel = null

    val labelStyle = remember { TextStyle(fontFamily = Mono, fontSize = 10.sp, letterSpacing = 1.sp) }
    val labels = remember(bs, tm) { bs.map { b -> tm.measure(if (b.vol.isNotBlank()) b.vol else if (b.small) "Q" else "★", labelStyle) } }
    val pctText = remember(pct, tm) { tm.measure("$pct%", TextStyle(fontSize = 18.sp, fontWeight = FontWeight.Light)) }

    Column(Modifier.fillMaxWidth()) {
        Box(
            Modifier.fillMaxWidth().aspectRatio(1f).testTag("constellation")
                .semantics { contentDescription = "Progress map, $pct percent learned" }
                .onSizeChanged { box = it }
                .pointerInput(geo) {
                    detectTapGestures { pos ->
                        val g = geo ?: return@detectTapGestures
                        val hit = g.dots.minByOrNull { (it.pos - pos).getDistanceSquared() }
                        val d = pos - g.c
                        val dist = d.getDistance()
                        sel = when {
                            hit != null && (hit.pos - pos).getDistance() < 20.dp.toPx() -> hit.b to hit.j
                            dist > g.rMin && dist < g.rMax * 1.15f && bs.isNotEmpty() -> {
                                val a = atan2(d.y, d.x) + PI.toFloat() / 2f
                                ((a / g.step).roundToInt() % bs.size + bs.size) % bs.size to -1
                            }
                            else -> null
                        }
                    }
                },
        ) {
            Canvas(Modifier.fillMaxSize()) {
                val g = geo ?: return@Canvas
                val line = 1.dp.toPx()
                val s = sel
                for (i in bs.indices) {
                    val dir = Offset(cos(g.angles[i]), sin(g.angles[i]))
                    val on = s?.first == i
                    drawLine(if (on) bs[i].color else Ice.Edge, g.c + dir * g.rMin, g.ends[i], if (on) line * 1.5f else line)
                    val lay = labels[i]
                    val p = g.ends[i] + dir * 12.dp.toPx()
                    drawText(lay, color = if (on) bs[i].color else Ice.Dim, topLeft = p - Offset(lay.size.width / 2f, lay.size.height / 2f))
                }
                g.dots.forEach { d ->
                    if (d.leaf.on) drawCircle(bs[d.b].color, d.r, d.pos)
                    else drawCircle(Ice.Dim, d.r, d.pos, style = Stroke(line))
                    if (s != null && s.first == d.b && s.second == d.j) drawCircle(Ice.Frost, d.r + 4.dp.toPx(), d.pos, style = Stroke(line))
                }
                val hr = g.rMin * 0.78f
                drawCircle(Ice.Edge, hr, g.c, style = Stroke(line))
                drawArc(Ice.Cyan, -90f, 360f * pct / 100f, false, topLeft = g.c - Offset(hr, hr), size = Size(hr * 2f, hr * 2f), style = Stroke(2.dp.toPx()))
                drawText(pctText, color = Ice.Frost, topLeft = g.c - Offset(pctText.size.width / 2f, pctText.size.height / 2f))
            }
        }
        val s = sel
        if (s != null) {
            val b = bs[s.first]
            val leaf = b.leaves.getOrNull(s.second)
            Spacer(Modifier.height(8.dp))
            FrostCard(Modifier.fillMaxWidth().testTag("web_info"), accent = b.color) {
                Hud(if (b.vol.isNotBlank()) "Vol. ${b.vol} · ${b.title}" else b.title, color = b.color, style = MaterialTheme.typography.labelSmall)
                Spacer(Modifier.height(6.dp))
                Text(leaf?.title ?: "${b.leaves.count { it.on }} of ${b.leaves.size} learned", style = MaterialTheme.typography.titleMedium,
                    color = Ice.Frost, maxLines = 3, overflow = TextOverflow.Ellipsis)
                if (leaf != null) Text(if (leaf.on) "Learned" else "Not learned yet", style = MaterialTheme.typography.bodyMedium, color = Ice.Mist)
                Spacer(Modifier.height(12.dp))
                IceButton("Open", { go(leaf?.route ?: b.route) }, Modifier.testTag("web_open"), color = b.color)
            }
        }
    }
}
