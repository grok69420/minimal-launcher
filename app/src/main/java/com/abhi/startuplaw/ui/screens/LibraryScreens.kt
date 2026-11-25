package com.abhi.startuplaw.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.abhi.startuplaw.AppViewModel
import com.abhi.startuplaw.data.Game
import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.data.QuizQ
import com.abhi.startuplaw.ui.components.LawText
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import com.abhi.startuplaw.ui.components.Bullet
import com.abhi.startuplaw.ui.components.EmptyNote
import com.abhi.startuplaw.ui.components.FrostCard
import com.abhi.startuplaw.ui.components.Glyph
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.IceButton
import com.abhi.startuplaw.ui.components.Icon
import com.abhi.startuplaw.ui.components.Pill
import com.abhi.startuplaw.ui.components.Screen
import com.abhi.startuplaw.ui.components.ScrambleText
import com.abhi.startuplaw.ui.components.SourceLinks
import com.abhi.startuplaw.ui.components.statusColor
import com.abhi.startuplaw.ui.theme.Ice

@Composable
fun VolumeScreen(vm: AppViewModel, lib: Library, id: String, go: (String) -> Unit, back: () -> Unit) {
    val prog by vm.progress.collectAsStateWithLifecycle()
    val m = lib.moduleById[id]
    val lessons = lib.lessonsByModule[id].orEmpty()
    val cases = lib.casesSorted.filter { it.module == id }
    val color = Ice.volume[((m?.order ?: 1) - 1).mod(Ice.volume.size)]
    Screen(title = m?.title ?: "Volume", hud = "Vol. ${m?.vol.orEmpty()} · ${lessons.size} lessons", onBack = back) {
        if (m == null) { item { EmptyNote("This volume is no longer in the library.") }; return@Screen }
        item(key = "head") {
            Text(m.blurb, style = MaterialTheme.typography.bodyLarge, color = Ice.Mist, modifier = Modifier.padding(vertical = 6.dp))
        }
        itemsIndexed(lessons, key = { _, l -> l.id }) { i, l ->
            val done = l.id in prog.lessons
            FrostCard(Modifier.fillMaxWidth().testTag("lesson_${l.id}"), onClick = { go("lesson/${l.id}") }, accent = if (done) color else null) {
                Row(verticalAlignment = Alignment.Top) {
                    Box(
                        Modifier.size(30.dp).clip(CircleShape).background(if (done) color else Ice.Glass).border(1.dp, if (done) color else Ice.Edge, CircleShape),
                        contentAlignment = Alignment.Center,
                    ) {
                        if (done) Icon(Glyph.Check, Ice.OnCyan, 16.dp) else Text("${i + 1}", style = MaterialTheme.typography.labelMedium, color = Ice.Mist)
                    }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text(l.title, style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
                        Spacer(Modifier.height(4.dp))
                        Text(l.summary, style = MaterialTheme.typography.bodyMedium, color = Ice.Mist, maxLines = 3, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
        if (cases.isNotEmpty()) {
            item(key = "caseshead") { Hud("Cases in this volume · ${cases.size}", color = Ice.Dim, modifier = Modifier.padding(top = 12.dp)) }
            itemsIndexed(cases, key = { _, c -> "c-" + c.id }) { _, c ->
                FrostCard(Modifier.fillMaxWidth(), onClick = { go("case/${c.id}") }) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(c.name, style = MaterialTheme.typography.titleMedium, color = Ice.Frost, maxLines = 2, overflow = TextOverflow.Ellipsis)
                            Hud("${c.court} · ${c.year}", color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
                        }
                        Spacer(Modifier.width(8.dp))
                        Pill(c.status, statusColor(c.status))
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun LessonScreen(vm: AppViewModel, lib: Library, id: String, go: (String) -> Unit, back: () -> Unit, openSibling: (String) -> Unit) {
    val prog by vm.progress.collectAsStateWithLifecycle()
    val haptic = LocalHapticFeedback.current
    val l = lib.lessonById[id]
    val m = l?.let { lib.moduleById[it.module] }
    val siblings = l?.let { lib.lessonsByModule[it.module] }.orEmpty()
    val pos = siblings.indexOfFirst { it.id == id }
    val color = Ice.volume[((m?.order ?: 1) - 1).mod(Ice.volume.size)]
    val related = l?.let { lesson -> lib.casesSorted.filter { it.module == lesson.module && lesson.body.any { p -> p.contains(caseKey(it.name)) } } }.orEmpty()
    // One question from this volume that hasn't been answered right yet (stable while on the page).
    val check = remember(id) { lib.quiz.filter { it.module == l?.module }.let { qs -> qs.firstOrNull { prog.quiz[it.id] != 1 } ?: qs.firstOrNull() } }

    Screen(title = m?.title ?: "Lesson", hud = "Vol. ${m?.vol.orEmpty()} · Lesson ${pos + 1} of ${siblings.size}", onBack = back) {
        if (l == null) { item { EmptyNote("This lesson is no longer in the library.") }; return@Screen }
        item(key = "head") {
            Column(Modifier.padding(top = 6.dp)) {
                Text(l.title, style = MaterialTheme.typography.headlineMedium, color = Ice.Frost)
                if (prog.terms.isEmpty()) {
                    Spacer(Modifier.height(10.dp))
                    Hud("Tip · tap any word to see what it means", color = Ice.Cyan, modifier = Modifier.testTag("tap_tip"))
                }
            }
        }
        if (l.plain.isNotBlank()) item(key = "plain") {
            FrostCard(Modifier.fillMaxWidth(), accent = Ice.Cyan) {
                Hud("In plain words")
                Spacer(Modifier.height(8.dp))
                LawText(l.plain, MaterialTheme.typography.bodyLarge, Ice.Frost, Modifier.testTag("plain"))
            }
        }
        item(key = "detailhead") { Hud(if (l.plain.isNotBlank()) "The detail" else l.summary, color = Ice.Dim) }
        item(key = "body") {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                if (l.plain.isNotBlank()) LawText(l.summary, MaterialTheme.typography.titleMedium, color.copy(alpha = 0.95f))
                l.body.forEach { LawText(it, MaterialTheme.typography.bodyLarge, Ice.Frost.copy(alpha = 0.92f)) }
            }
        }
        if (l.keyPoints.isNotEmpty()) item(key = "kp") {
            FrostCard(Modifier.fillMaxWidth(), accent = color) {
                Hud("Remember", color = color)
                Spacer(Modifier.height(6.dp))
                l.keyPoints.forEachIndexed { i, k -> Bullet(k, color, Modifier.testTag("kp_$i")) }
            }
        }
        if (related.isNotEmpty()) item(key = "rel") {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                related.forEach { c -> IceButton("Case: " + c.name.substringBefore(" v ").take(24), onClick = { go("case/${c.id}") }, primary = false, color = Ice.Aurora) }
            }
        }
        if (check != null) item(key = "check") { QuickCheck(vm, check) }
        item(key = "src") { SourceLinks(l.sources) }
        item(key = "actions") {
            val done = l.id in prog.lessons
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                IceButton(
                    if (done) "✓ Learned — tap to undo" else "Mark as learned · +${Game.LESSON} XP",
                    onClick = { haptic.performHapticFeedback(HapticFeedbackType.LongPress); vm.toggleLesson(l.id) },
                    modifier = Modifier.fillMaxWidth().testTag("mark_learned"), primary = !done, color = color,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    if (pos > 0) IceButton("‹ Previous", onClick = { openSibling(siblings[pos - 1].id) }, modifier = Modifier.weight(1f), primary = false)
                    else Spacer(Modifier.weight(1f))
                    if (pos in 0 until siblings.lastIndex) IceButton("Next ›", onClick = { openSibling(siblings[pos + 1].id) }, modifier = Modifier.weight(1f).testTag("next_lesson"), primary = false)
                    else Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}

/** A single quiz question answered inside the lesson. */
@Composable
fun QuickCheck(vm: AppViewModel, q: QuizQ) {
    var picked by rememberSaveable(q.id) { mutableStateOf<Int?>(null) }
    FrostCard(Modifier.fillMaxWidth().testTag("quick_check"), accent = Ice.Aurora) {
        Hud("Quick check · +${Game.QUIZ} XP", color = Ice.Aurora)
        Spacer(Modifier.height(8.dp))
        LawText(q.q, MaterialTheme.typography.titleMedium, Ice.Frost)
        Spacer(Modifier.height(10.dp))
        q.opts.forEachIndexed { i, opt ->
            val p = picked
            val c = when { p == null -> Ice.Edge; i == q.a -> Ice.Mint; i == p -> Ice.Coral; else -> Ice.EdgeLo }
            Row(
                Modifier.fillMaxWidth().padding(vertical = 4.dp).heightIn(min = 48.dp).clip(RoundedCornerShape(14.dp))
                    .background(if (p != null && i == q.a) Ice.Mint.copy(alpha = 0.12f) else if (p == i) Ice.Coral.copy(alpha = 0.12f) else Color.Transparent)
                    .border(1.dp, c, RoundedCornerShape(14.dp))
                    .clickable(enabled = p == null) { picked = i; vm.quickCheck(q, i) }
                    .testTag("qc_opt_$i").padding(horizontal = 14.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(opt, style = MaterialTheme.typography.bodyMedium, color = Ice.Frost, modifier = Modifier.weight(1f))
                if (p != null && i == q.a) Text("✓", color = Ice.Mint)
                if (p == i && i != q.a) Text("✕", color = Ice.Coral)
            }
        }
        picked?.let { p ->
            Spacer(Modifier.height(6.dp))
            Hud(if (p == q.a) "Correct" else "Not quite", color = if (p == q.a) Ice.Mint else Ice.Coral)
            LawText(q.why, MaterialTheme.typography.bodyMedium, Ice.Frost)
        }
    }
}

/** A short, distinctive part of a case name used to spot it in lesson text. */
fun caseKey(name: String): String {
    val parts = name.split(" v ")
    val a = parts[0].substringBefore(" (").trim()
    return if (a.length >= 6) a.take(14) else parts.getOrNull(1)?.trim()?.substringBefore(' ')?.takeIf { it.length >= 4 } ?: a
}
