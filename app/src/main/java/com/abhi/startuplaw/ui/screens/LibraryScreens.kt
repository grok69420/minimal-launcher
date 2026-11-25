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
import com.abhi.startuplaw.data.Library
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
            Column(Modifier.padding(vertical = 10.dp)) {
                ScrambleText(m.title, MaterialTheme.typography.headlineMedium)
                Spacer(Modifier.height(8.dp))
                Text(m.blurb, style = MaterialTheme.typography.bodyLarge, color = Ice.Mist)
            }
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

    Screen(title = l?.title ?: "Lesson", hud = "Vol. ${m?.vol.orEmpty()} · Lesson ${pos + 1} of ${siblings.size}", onBack = back) {
        if (l == null) { item { EmptyNote("This lesson is no longer in the library.") }; return@Screen }
        item(key = "head") {
            Column(Modifier.padding(top = 10.dp)) {
                Hud(m?.title.orEmpty(), color = color)
                Spacer(Modifier.height(8.dp))
                ScrambleText(l.title, MaterialTheme.typography.headlineMedium)
                Spacer(Modifier.height(12.dp))
                Text(l.summary, style = MaterialTheme.typography.titleMedium, color = Ice.Cyan.copy(alpha = 0.9f))
            }
        }
        item(key = "body") {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                l.body.forEach { Text(it, style = MaterialTheme.typography.bodyLarge, color = Ice.Frost.copy(alpha = 0.92f)) }
            }
        }
        if (l.keyPoints.isNotEmpty()) item(key = "kp") {
            FrostCard(Modifier.fillMaxWidth(), accent = color) {
                Hud("Key points", color = color)
                Spacer(Modifier.height(6.dp))
                l.keyPoints.forEach { Bullet(it, color) }
            }
        }
        if (related.isNotEmpty()) item(key = "rel") {
            Column {
                Hud("Cases mentioned", color = Ice.Dim)
                Spacer(Modifier.height(8.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    related.forEach { c ->
                        Box(Modifier.clip(CircleShape)) {
                            IceButton(c.name.substringBefore(" v ").take(28), onClick = { go("case/${c.id}") }, primary = false, color = Ice.Aurora)
                        }
                    }
                }
            }
        }
        item(key = "src") { SourceLinks(l.sources) }
        item(key = "meta") { if (l.updated.isNotBlank()) Hud("Updated ${l.updated}", color = Ice.Dim, style = MaterialTheme.typography.labelSmall) }
        item(key = "actions") {
            val done = l.id in prog.lessons
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                IceButton(
                    if (done) "✓ Learned — tap to undo" else "Mark as learned",
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

/** A short, distinctive part of a case name used to spot it in lesson text. */
fun caseKey(name: String): String {
    val parts = name.split(" v ")
    val a = parts[0].substringBefore(" (").trim()
    return if (a.length >= 6) a.take(14) else parts.getOrNull(1)?.trim()?.substringBefore(' ')?.takeIf { it.length >= 4 } ?: a
}
