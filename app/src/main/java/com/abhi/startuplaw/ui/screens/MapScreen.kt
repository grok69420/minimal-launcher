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
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.abhi.startuplaw.AppViewModel
import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.data.Progress
import com.abhi.startuplaw.ui.components.Bar
import com.abhi.startuplaw.ui.components.FrostCard
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.Screen
import com.abhi.startuplaw.ui.components.Stat
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
    Screen(title = "Progress", hud = "$on of ${all.size} learned · $pct%", onBack = null) {
        item(key = "overview") {
            FrostCard(Modifier.fillMaxWidth().testTag("progress_card"), accent = Ice.Cyan) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    com.abhi.startuplaw.ui.components.ProgressRing(pct / 100f, 72.dp) {
                        Text("$pct%", style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
                    }
                    Spacer(Modifier.width(16.dp))
                    Row(Modifier.weight(1f)) {
                        Stat("${lib.lessons.count { it.id in prog.lessons }}/${lib.lessons.size}", "Lessons")
                        Stat("${lib.stories.count { it.id in prog.stories }}/${lib.stories.size}", "Stories")
                        Stat("${lib.quiz.count { prog.quiz[it.id] == 1 }}/${lib.quiz.size}", "Quiz right")
                    }
                }
            }
        }
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
