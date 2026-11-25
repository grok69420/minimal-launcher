package com.abhi.startuplaw.ui.screens

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.abhi.startuplaw.AppViewModel
import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.data.Progress
import com.abhi.startuplaw.ui.components.Bar
import com.abhi.startuplaw.ui.components.FrostCard
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.Screen
import com.abhi.startuplaw.ui.components.ScrambleText
import com.abhi.startuplaw.ui.theme.Ice
import com.abhi.startuplaw.ui.theme.LocalReducedMotion
import kotlin.math.PI
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin

data class Leaf(val id: String, val title: String, val on: Boolean, val route: String)
data class Branch(val id: String, val title: String, val vol: String, val color: Color, val route: String, val leaves: List<Leaf>, val small: Boolean = false)

fun branches(lib: Library, p: Progress): List<Branch> = buildList {
    lib.modulesSorted.forEachIndexed { i, m ->
        add(Branch(m.id, m.title, m.vol, Ice.volume[i % Ice.volume.size], "volume/${m.id}",
            lib.lessonsByModule[m.id].orEmpty().map { Leaf(it.id, it.title, it.id in p.lessons, "lesson/${it.id}") }))
    }
    if (lib.stories.isNotEmpty()) add(Branch("_stories", "Founder stories", "", Ice.Amber, "playbook",
        lib.storiesSorted.map { Leaf(it.id, it.short.ifBlank { it.name }, it.id in p.stories, "story/${it.id}") }))
    if (lib.quiz.isNotEmpty()) add(Branch("_quiz", "Quiz answered right", "", Ice.Mint, "practice",
        lib.quiz.map { Leaf(it.id, "Q" + it.id.filter(Char::isDigit), p.quiz[it.id] == 1, "practice") }, small = true))
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MapScreen(vm: AppViewModel, lib: Library, go: (String) -> Unit) {
    val prog by vm.progress.collectAsStateWithLifecycle()
    val bs = remember(lib, prog) { branches(lib, prog) }
    val all = bs.flatMap { it.leaves }
    val on = all.count { it.on }
    val pct = if (all.isEmpty()) 0 else on * 100 / all.size
    Screen(title = "Progress map", hud = "$on of ${all.size} learned · $pct%", onBack = null) {
        item(key = "intro") {
            Column(Modifier.padding(top = 6.dp)) {
                ScrambleText("Your constellation", MaterialTheme.typography.headlineMedium)
                Text("Every lesson, founder story and quiz question is a star. Lit stars are done. Tap a spoke to open that volume.", style = MaterialTheme.typography.bodyMedium, color = Ice.Mist)
            }
        }
        item(key = "sky") { Constellation(bs, pct) { b -> go(b.route) } }
        val next = bs.filter { !it.small }.mapNotNull { b -> b.leaves.firstOrNull { !it.on }?.let { b to it } }.take(4)
        if (next.isNotEmpty()) item(key = "next") {
            FrostCard(Modifier.fillMaxWidth(), accent = Ice.Cyan) {
                Hud("Next up")
                next.forEach { (b, l) ->
                    Row(
                        Modifier.fillMaxWidth().heightIn(min = 48.dp).clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { go(l.route) }.padding(vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(Modifier.width(4.dp).height(30.dp).clip(RoundedCornerShape(2.dp)).background(b.color))
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Hud(b.title, color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
                            Text(l.title, style = MaterialTheme.typography.bodyMedium, color = Ice.Frost, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
            }
        } else item(key = "alldone") {
            FrostCard(Modifier.fillMaxWidth(), accent = Ice.Mint) { Text("Everything done. New items light up here as the library updates.", color = Ice.Frost) }
        }
        items(bs, key = { "b-" + it.id }) { b ->
            val d = b.leaves.count { it.on }
            FrostCard(Modifier.fillMaxWidth().testTag("branch_${b.id}"), accent = b.color.copy(alpha = 0.6f)) {
                Row(Modifier.fillMaxWidth().clickable(role = Role.Button) { go(b.route) }, verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        if (b.vol.isNotBlank()) Hud("Vol. ${b.vol}", color = b.color, style = MaterialTheme.typography.labelSmall)
                        Text(b.title, style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
                    }
                    Hud("$d/${b.leaves.size}", color = b.color)
                }
                Spacer(Modifier.height(8.dp))
                Bar(if (b.leaves.isEmpty()) 0f else d / b.leaves.size.toFloat(), b.color)
                Spacer(Modifier.height(10.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    b.leaves.forEach { l ->
                        val shape = RoundedCornerShape(50)
                        Box(
                            Modifier.clip(shape)
                                .background(if (l.on) b.color.copy(alpha = 0.18f) else Color.Transparent)
                                .border(1.dp, if (l.on) b.color else Ice.Edge, shape)
                                .then(if (b.small) Modifier else Modifier.clickable(role = Role.Button) { go(l.route) })
                                .semantics { contentDescription = l.title + if (l.on) ", done" else ", not yet" }
                                .padding(horizontal = 10.dp, vertical = if (b.small) 4.dp else 8.dp),
                        ) {
                            Text((if (l.on) "✓ " else "") + l.title, style = if (b.small) MaterialTheme.typography.labelSmall else MaterialTheme.typography.bodyMedium,
                                color = if (l.on) Ice.Frost else Ice.Mist, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
            }
        }
    }
}

/** Radial star map: one spoke per branch, one star per item; lit = done. */
@Composable
private fun Constellation(bs: List<Branch>, pct: Int, onBranch: (Branch) -> Unit) {
    val reduced = LocalReducedMotion.current
    val pulse = if (reduced) null else rememberInfiniteTransition(label = "pulse").animateFloat(0f, 1f, infiniteRepeatable(tween(2600, easing = LinearEasing), RepeatMode.Reverse), label = "p")
    Box(
        Modifier.fillMaxWidth().aspectRatio(1f).testTag("constellation")
            .semantics { contentDescription = "Progress constellation, $pct percent done" }
            .pointerInput(bs) {
                detectTapGestures { pos ->
                    if (bs.isEmpty()) return@detectTapGestures
                    val cx = size.width / 2f; val cy = size.height / 2f
                    val dx = pos.x - cx; val dy = pos.y - cy
                    if (dx * dx + dy * dy < (size.width * 0.12f) * (size.width * 0.12f)) return@detectTapGestures
                    var a = atan2(dy, dx) + PI.toFloat() / 2f
                    if (a < 0) a += 2f * PI.toFloat()
                    val step = 2f * PI.toFloat() / bs.size
                    val i = ((a + step / 2f) / step).toInt() % bs.size
                    onBranch(bs[i])
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.fillMaxWidth().aspectRatio(1f)) {
            val c = Offset(size.width / 2, size.height / 2)
            val rMax = size.minDimension * 0.47f
            val rMin = size.minDimension * 0.15f
            val glow = pulse?.value ?: 0.5f
            for (k in 1..3) drawCircle(Ice.Edge.copy(alpha = 0.55f), rMin + (rMax - rMin) * k / 3f, c, style = Stroke(1f))
            val step = 2f * PI.toFloat() / bs.size.coerceAtLeast(1)
            bs.forEachIndexed { i, b ->
                val ang = -PI.toFloat() / 2f + step * i
                val dir = Offset(cos(ang), sin(ang))
                val n = b.leaves.size.coerceAtLeast(1)
                drawLine(b.color.copy(alpha = 0.38f), c + dir * rMin, c + dir * rMax, 1.5f)
                b.leaves.forEachIndexed { j, l ->
                    val t = (j + 1f) / (n + 1f)
                    val wobble = if (b.small) ((j % 3) - 1) * 0.06f else 0f
                    val a2 = ang + wobble * step
                    val p = c + Offset(cos(a2), sin(a2)) * (rMin + (rMax - rMin) * t)
                    val r = (if (b.small) 2.2f else 3.6f).dp.toPx()
                    if (l.on) {
                        drawCircle(Brush.radialGradient(listOf(b.color.copy(alpha = 0.55f + 0.25f * glow), Color.Transparent), p, r * 2.6f), r * 2.6f, p)
                        drawCircle(Ice.Frost, r * 0.6f, p)
                    } else {
                        drawCircle(b.color.copy(alpha = 0.35f), r * 0.6f, p)
                        drawCircle(Ice.Mist.copy(alpha = 0.55f), r * 0.6f, p, style = Stroke(1f))
                    }
                }
            }
            drawCircle(Brush.radialGradient(listOf(Ice.Cyan.copy(alpha = 0.25f + 0.15f * glow), Color.Transparent), c, rMin * 1.6f), rMin * 1.6f, c)
            drawCircle(Ice.Night, rMin * 0.95f, c)
            drawCircle(Ice.Cyan.copy(alpha = 0.6f), rMin * 0.95f, c, style = Stroke(1.5f))
            drawArc(Ice.Cyan, -90f, 360f * pct / 100f, false, topLeft = c - Offset(rMin * 0.95f, rMin * 0.95f),
                size = androidx.compose.ui.geometry.Size(rMin * 1.9f, rMin * 1.9f), style = Stroke(4.dp.toPx()))
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("$pct%", style = MaterialTheme.typography.headlineMedium, color = Ice.Frost)
            Hud("learned", color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
        }
    }
}
