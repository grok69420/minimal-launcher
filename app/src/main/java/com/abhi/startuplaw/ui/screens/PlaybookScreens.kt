package com.abhi.startuplaw.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.abhi.startuplaw.AppViewModel
import com.abhi.startuplaw.data.Gap
import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.data.Trap
import com.abhi.startuplaw.ui.components.Block
import com.abhi.startuplaw.ui.components.EmptyNote
import com.abhi.startuplaw.ui.components.FilterPill
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
import com.abhi.startuplaw.ui.theme.Mono

@Composable
fun PlaybookScreen(vm: AppViewModel, lib: Library, initialTab: Int, focus: String?, go: (String) -> Unit) {
    val prog by vm.progress.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableStateOf(initialTab.coerceIn(0, 1)) }
    var open by rememberSaveable { mutableStateOf(focus) }
    val state = rememberLazyListState()
    LaunchedEffect(focus) {
        if (focus != null) {
            val i = lib.trapsSorted.indexOfFirst { it.id == focus }
            if (i >= 0) state.scrollToItem(i + 1)
        }
    }
    Screen(title = "Founder playbook", hud = "Control · term sheets · survival", onBack = null, state = state) {
        item(key = "tabs") {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterPill("Stories · ${lib.stories.size}", tab == 0, { tab = 0 })
                FilterPill("Term-sheet traps · ${lib.traps.size}", tab == 1, { tab = 1 })
            }
        }
        if (tab == 0) {
            items(lib.storiesSorted, key = { "s-" + it.id }) { s ->
                val studied = s.id in prog.stories
                FrostCard(Modifier.fillMaxWidth().testTag("story_${s.id}"), onClick = { go("story/${s.id}") }, accent = if (studied) Ice.Cyan else null) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Hud("${s.country} · ${s.year} · ${s.kind}", color = Ice.Dim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.weight(1f))
                        if (studied) Icon(Glyph.Check, Ice.Cyan, 16.dp)
                    }
                    Spacer(Modifier.height(8.dp))
                    Text(s.name, style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
                    Spacer(Modifier.height(6.dp))
                    Text(s.lesson, style = MaterialTheme.typography.bodyMedium, color = Ice.Mist, maxLines = 3, overflow = TextOverflow.Ellipsis)
                    Spacer(Modifier.height(10.dp))
                    Pill(s.outcome, statusColor(s.outcome))
                }
            }
        } else {
            items(lib.trapsSorted, key = { "t-" + it.id }) { t ->
                TrapCard(t, expanded = open == t.id) { open = if (open == t.id) null else t.id }
            }
        }
    }
}

@Composable
private fun TrapCard(t: Trap, expanded: Boolean, toggle: () -> Unit) {
    FrostCard(Modifier.fillMaxWidth().testTag("trap_${t.id}"), onClick = toggle, accent = if (expanded) Ice.Mint else null) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Hud("Trap ${t.order.toString().padStart(2, '0')}", color = Ice.Mint, modifier = Modifier.weight(1f))
            Text(if (expanded) "–" else "+", style = MaterialTheme.typography.titleLarge, color = Ice.Mist)
        }
        Spacer(Modifier.height(6.dp))
        Text(t.clause, style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
        AnimatedVisibility(expanded, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
            Column(Modifier.padding(top = 8.dp)) {
                if (t.looks.isNotBlank()) {
                    Hud("Looks like", color = Ice.Dim)
                    Spacer(Modifier.height(6.dp))
                    Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Color(0x33000000)).border(1.dp, Ice.EdgeLo, RoundedCornerShape(12.dp)).padding(12.dp)) {
                        com.abhi.startuplaw.ui.components.LawText(t.looks, MaterialTheme.typography.bodyMedium.copy(fontFamily = Mono, fontStyle = FontStyle.Normal), Ice.Frost.copy(alpha = 0.85f))
                    }
                }
                Block("The risk", t.risk, Ice.Coral)
                Block("Ask for instead", t.ask, Ice.Mint)
                Block("India angle", t.india, Ice.Cyan)
                Block("Seen in", t.seen, Ice.Aurora)
            }
        }
    }
}

@Composable
fun StoryScreen(vm: AppViewModel, lib: Library, id: String, back: () -> Unit) {
    val prog by vm.progress.collectAsStateWithLifecycle()
    val haptic = LocalHapticFeedback.current
    val s = lib.storyById[id]
    Screen(title = s?.short?.ifBlank { s.name } ?: "Story", hud = s?.let { "${it.country} · ${it.year}" } ?: "Founder story", onBack = back) {
        if (s == null) { item { EmptyNote("This story is no longer in the library.") }; return@Screen }
        item(key = "head") {
            Column(Modifier.padding(top = 10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Pill(s.outcome, statusColor(s.outcome))
                    Spacer(Modifier.width(8.dp))
                    Hud(s.kind, color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
                }
                Spacer(Modifier.height(10.dp))
                ScrambleText(s.name, MaterialTheme.typography.headlineSmall)
                if (s.who.isNotBlank()) { Spacer(Modifier.height(6.dp)); Hud(s.who, color = Ice.Mist, style = MaterialTheme.typography.labelSmall) }
            }
        }
        if (s.status.isNotBlank()) item(key = "status") {
            FrostCard(Modifier.fillMaxWidth(), accent = Ice.Amber) {
                Block("Latest" + if (s.checked.isNotBlank()) " · checked ${s.checked}" else "", s.status, Ice.Amber)
            }
        }
        item(key = "what") { Block("What happened", s.what, Ice.Mist) }
        item(key = "move") { FrostCard(Modifier.fillMaxWidth()) { Block("The move", s.move, Ice.Aurora) } }
        item(key = "lesson") { FrostCard(Modifier.fillMaxWidth(), accent = Ice.Cyan) { Block("Lesson", s.lesson, Ice.Cyan) } }
        item(key = "apply") { FrostCard(Modifier.fillMaxWidth(), accent = Ice.Mint) { Block("Apply it to your startups", s.apply, Ice.Mint) } }
        item(key = "src") { SourceLinks(s.src) }
        item(key = "act") {
            val done = s.id in prog.stories
            IceButton(
                if (done) "✓ Studied — tap to undo" else "Mark as studied · +${com.abhi.startuplaw.data.Game.STORY} XP",
                onClick = { haptic.performHapticFeedback(HapticFeedbackType.LongPress); vm.toggleStory(s.id) },
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp).testTag("mark_studied"), primary = !done,
            )
        }
    }
}

@Composable
fun LoopholesScreen(lib: Library, focus: String?, back: () -> Unit) {
    var open by rememberSaveable { mutableStateOf(focus) }
    val state = rememberLazyListState()
    LaunchedEffect(focus) {
        val i = lib.gapsSorted.indexOfFirst { it.id == focus }
        if (i >= 0) state.scrollToItem(i)
    }
    Screen(title = "Loopholes", hud = "How gaps were used, then closed", onBack = back, state = state) {
        items(lib.gapsSorted, key = { it.id }) { g -> GapCard(lib, g, open == g.id) { open = if (open == g.id) null else g.id } }
    }
}

@Composable
private fun GapCard(lib: Library, g: Gap, expanded: Boolean, toggle: () -> Unit) {
    val c = statusColor(g.status)
    FrostCard(Modifier.fillMaxWidth().testTag("gap_${g.id}"), onClick = toggle, accent = if (expanded) c else null) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) { Pill(g.status, c) }
            Text(if (expanded) "–" else "+", style = MaterialTheme.typography.titleLarge, color = Ice.Mist)
        }
        Spacer(Modifier.height(6.dp))
        Hud(lib.moduleTitle(g.module), color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
        Spacer(Modifier.height(6.dp))
        Text(g.title, style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
        AnimatedVisibility(expanded, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
            Column(Modifier.padding(top = 6.dp)) {
                Block("The gap", g.gap, Ice.Amber)
                Block("How it was used", g.used, Ice.Aurora)
                Block("How it was closed", g.closed, Ice.Coral)
                if (g.timeline.isNotEmpty()) {
                    Hud("Timeline", color = Ice.Dim, modifier = Modifier.padding(top = 8.dp, bottom = 6.dp))
                    g.timeline.forEachIndexed { i, t ->
                        Row(Modifier.fillMaxWidth()) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(18.dp)) {
                                Box(Modifier.padding(top = 5.dp).size(9.dp).clip(CircleShape).background(c))
                                if (i < g.timeline.lastIndex) Box(Modifier.width(1.dp).height(30.dp).background(Ice.Edge))
                            }
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.padding(bottom = 8.dp)) {
                                Text(t.y, style = MaterialTheme.typography.labelLarge, color = c)
                                Text(t.e, style = MaterialTheme.typography.bodyMedium, color = Ice.Frost)
                            }
                        }
                    }
                }
                Block("Today", g.today, Ice.Mint)
                SourceLinks(g.src)
            }
        }
    }
}
