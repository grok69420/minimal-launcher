package com.abhi.startuplaw.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.abhi.startuplaw.AppViewModel
import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.data.Source
import com.abhi.startuplaw.ui.components.Bar
import com.abhi.startuplaw.ui.components.FrostCard
import com.abhi.startuplaw.ui.components.Glyph
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.Icon
import com.abhi.startuplaw.ui.components.ProgressRing
import com.abhi.startuplaw.ui.components.Screen
import com.abhi.startuplaw.ui.components.ScrambleText
import com.abhi.startuplaw.ui.components.hudFrame
import com.abhi.startuplaw.ui.theme.Ice

@Composable
fun HomeScreen(vm: AppViewModel, lib: Library, go: (String) -> Unit) {
    val prog by vm.progress.collectAsStateWithLifecycle()
    val online by vm.online.collectAsStateWithLifecycle()
    val content by vm.content.collectAsStateWithLifecycle()
    val total = lib.lessons.size + lib.stories.size + lib.quiz.size
    val done = lib.lessons.count { it.id in prog.lessons } + lib.stories.count { it.id in prog.stories } + lib.quiz.count { prog.quiz[it.id] == 1 }
    val newUpdates = lib.updates.count { it.date > prog.seen }

    Screen(title = "Startup Law", hud = "Library // India", onBack = null, particles = true, actions = {
        StatusChip(online, content.syncing) { go("about") }
    }) {
        item(key = "hero") {
            Column(Modifier.fillMaxWidth().padding(top = 18.dp, bottom = 6.dp).hudFrame().padding(18.dp)) {
                Hud("Vol. I–${lib.modulesSorted.lastOrNull()?.vol ?: "I"} · ${lib.lessons.size} lessons · ${lib.cases.size} cases")
                Spacer(Modifier.height(10.dp))
                ScrambleText("Know the law before you need it.", MaterialTheme.typography.displaySmall)
                Spacer(Modifier.height(10.dp))
                Text(
                    "Indian startup law, the cases behind it, the loopholes that closed, and the founder fights worth learning from. Works offline; updates itself when you're online.",
                    style = MaterialTheme.typography.bodyMedium, color = Ice.Mist,
                )
            }
        }
        item(key = "search") {
            Row(
                Modifier.fillMaxWidth().heightIn(min = 54.dp).clip(RoundedCornerShape(16.dp))
                    .background(Ice.Glass).border(1.dp, Ice.Edge, RoundedCornerShape(16.dp))
                    .clickable(role = Role.Button) { go("search") }.testTag("open_search")
                    .padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Glyph.Search, Ice.Mist, 20.dp)
                Spacer(Modifier.width(12.dp))
                Text("Search cases, sections, founders…", color = Ice.Dim, style = MaterialTheme.typography.bodyMedium)
            }
        }
        item(key = "progress") {
            FrostCard(Modifier.fillMaxWidth(), onClick = { go("map") }, accent = Ice.Cyan) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val f = if (total == 0) 0f else done / total.toFloat()
                    ProgressRing(f, 78.dp) { Text("${(f * 100).toInt()}%", style = MaterialTheme.typography.titleMedium, color = Ice.Frost) }
                    Spacer(Modifier.width(18.dp))
                    Column(Modifier.weight(1f)) {
                        Hud("Your progress")
                        Text("$done of $total learned", style = MaterialTheme.typography.titleLarge, color = Ice.Frost)
                        Text("Lessons, founder stories and quiz answers. Tap for your map.", style = MaterialTheme.typography.bodyMedium, color = Ice.Mist)
                    }
                }
            }
        }
        item(key = "tiles") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Tile("Loopholes", "${lib.gaps.size} closed & open gaps", Ice.Coral, Modifier.weight(1f)) { go("loopholes") }
                    Tile("Updates", if (newUpdates > 0) "$newUpdates new" else "Checked ${lib.meta.lastChecked}", Ice.Amber, Modifier.weight(1f), badge = newUpdates) { go("updates") }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Tile("Ask the tutor", "Answers from your library", Ice.Aurora, Modifier.weight(1f)) { go("tutor") }
                    Tile("Term-sheet traps", "${lib.traps.size} clauses to fight", Ice.Mint, Modifier.weight(1f)) { go("playbook?tab=1") }
                }
            }
        }
        item(key = "volhead") {
            Column(Modifier.padding(top = 12.dp)) {
                Hud("Volumes", color = Ice.Dim)
                Text("The library", style = MaterialTheme.typography.headlineMedium, color = Ice.Frost)
            }
        }
        items(lib.modulesSorted, key = { "m-" + it.id }) { m ->
            val ls = lib.lessonsByModule[m.id].orEmpty()
            val d = ls.count { it.id in prog.lessons }
            val color = Ice.volume[(m.order - 1).mod(Ice.volume.size)]
            FrostCard(Modifier.fillMaxWidth().testTag("vol_${m.id}"), onClick = { go("volume/${m.id}") }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(46.dp).clip(RoundedCornerShape(14.dp)).background(color.copy(alpha = 0.12f)).border(1.dp, color.copy(alpha = 0.5f), RoundedCornerShape(14.dp)), contentAlignment = Alignment.Center) {
                        Text(m.vol, style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold), color = color)
                    }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text(m.title, style = MaterialTheme.typography.titleMedium, color = Ice.Frost, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        Text(m.blurb, style = MaterialTheme.typography.bodyMedium, color = Ice.Mist, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                    Icon(Glyph.Chevron, Ice.Dim, 18.dp)
                }
                Spacer(Modifier.height(12.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Bar(if (ls.isEmpty()) 0f else d / ls.size.toFloat(), color, Modifier.weight(1f))
                    Spacer(Modifier.width(10.dp))
                    Hud("$d/${ls.size}", color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
        item(key = "foot") {
            Column(Modifier.padding(top = 10.dp)) {
                Hud(
                    when (content.source) { Source.Synced -> "Synced this session"; Source.Saved -> "Saved copy on this phone"; Source.Bundled -> "Built-in copy" } +
                        " · last checked ${lib.meta.lastChecked}",
                    color = Ice.Dim, style = MaterialTheme.typography.labelSmall,
                )
                Spacer(Modifier.height(4.dp))
                Text("Educational only. Not legal or tax advice.", style = MaterialTheme.typography.bodyMedium, color = Ice.Dim)
            }
        }
    }
}

@Composable
fun StatusChip(online: Boolean, syncing: Boolean, onClick: () -> Unit) {
    val c = when { syncing -> Ice.Cyan; online -> Ice.Mint; else -> Ice.Amber }
    Row(
        Modifier.heightIn(min = 40.dp).clip(RoundedCornerShape(50)).border(1.dp, c.copy(alpha = 0.5f), RoundedCornerShape(50))
            .clickable(role = Role.Button, onClick = onClick).semantics { contentDescription = if (online) "Online. Open sync settings" else "Offline. Open sync settings" }
            .testTag("status_chip").padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(7.dp).clip(CircleShape).background(c))
        Spacer(Modifier.width(8.dp))
        Hud(when { syncing -> "Syncing"; online -> "Online"; else -> "Offline" }, color = c, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun Tile(title: String, sub: String, color: Color, modifier: Modifier, badge: Int = 0, onClick: () -> Unit) {
    FrostCard(modifier.heightIn(min = 112.dp), onClick = onClick, accent = color, padding = androidx.compose.foundation.layout.PaddingValues(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Glyph.Spark, color, 18.dp)
            Spacer(Modifier.weight(1f))
            if (badge > 0) Box(Modifier.clip(RoundedCornerShape(50)).background(color).padding(horizontal = 8.dp, vertical = 2.dp)) {
                Text("$badge", style = MaterialTheme.typography.labelSmall, color = Ice.OnCyan)
            }
        }
        Spacer(Modifier.height(14.dp))
        Text(title, style = MaterialTheme.typography.titleMedium, color = Ice.Frost, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(sub, style = MaterialTheme.typography.bodyMedium, color = Ice.Mist, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}
