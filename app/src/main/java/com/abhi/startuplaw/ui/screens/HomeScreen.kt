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
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.abhi.startuplaw.AppViewModel
import com.abhi.startuplaw.data.Game
import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.data.Progress
import com.abhi.startuplaw.ui.components.Bar
import com.abhi.startuplaw.ui.components.FrostCard
import com.abhi.startuplaw.ui.components.Glyph
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.IceButton
import com.abhi.startuplaw.ui.components.Icon
import com.abhi.startuplaw.ui.components.ProgressRing
import com.abhi.startuplaw.ui.components.Screen
import com.abhi.startuplaw.ui.theme.Ice

@Composable
fun HomeScreen(vm: AppViewModel, lib: Library, go: (String) -> Unit) {
    val prog by vm.progress.collectAsStateWithLifecycle()
    val online by vm.online.collectAsStateWithLifecycle()
    val content by vm.content.collectAsStateWithLifecycle()
    val newUpdates = lib.updates.count { it.date > prog.seen }
    val next = lib.lessonsInOrder.firstOrNull { it.id !in prog.lessons }

    Screen(title = "Startup Law", hud = "Learn it from zero", onBack = null, particles = true, actions = {
        StatusChip(online, content.syncing) { go("about") }
    }) {
        item(key = "player") { PlayerCard(prog, lib) { go("map") } }
        item(key = "continue") {
            if (next != null) {
                val m = lib.moduleById[next.module]
                val pos = lib.lessonsByModule[next.module].orEmpty().indexOf(next) + 1
                FrostCard(Modifier.fillMaxWidth().testTag("continue"), onClick = { go("lesson/${next.id}") }, accent = Ice.Cyan) {
                    Hud(if (prog.lessons.isEmpty()) "Start here" else "Up next · Vol. ${m?.vol} · Lesson $pos")
                    Spacer(Modifier.height(6.dp))
                    Text(next.title, style = MaterialTheme.typography.headlineSmall, color = Ice.Frost)
                    Spacer(Modifier.height(6.dp))
                    Text(next.plain.ifBlank { next.summary }, style = MaterialTheme.typography.bodyMedium, color = Ice.Mist, maxLines = 3, overflow = TextOverflow.Ellipsis)
                    Spacer(Modifier.height(14.dp))
                    IceButton(if (prog.lessons.isEmpty()) "Start · +${Game.LESSON} XP" else "Continue · +${Game.LESSON} XP", onClick = { go("lesson/${next.id}") }, modifier = Modifier.fillMaxWidth())
                }
            } else {
                FrostCard(Modifier.fillMaxWidth(), accent = Ice.Mint) {
                    Hud("All lessons learned", color = Ice.Mint)
                    Text("Keep your streak with the quiz and flashcards. New lessons appear as the law changes.", style = MaterialTheme.typography.bodyMedium, color = Ice.Frost)
                }
            }
        }
        item(key = "search") {
            Row(
                Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(RoundedCornerShape(16.dp))
                    .background(Ice.Glass).border(1.dp, Ice.Edge, RoundedCornerShape(16.dp))
                    .clickable(role = Role.Button) { go("search") }.testTag("open_search")
                    .padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Glyph.Search, Ice.Mist, 20.dp)
                Spacer(Modifier.width(12.dp))
                Text("Search anything", color = Ice.Dim, style = MaterialTheme.typography.bodyMedium)
            }
        }
        item(key = "chips") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                QuickChip("Glossary", Ice.Cyan, Modifier.weight(1f), tag = "chip_glossary") { go("glossary") }
                QuickChip("Loopholes", Ice.Coral, Modifier.weight(1f)) { go("loopholes") }
                QuickChip("Updates", Ice.Amber, Modifier.weight(1f), badge = newUpdates) { go("updates") }
                QuickChip("Tutor", Ice.Aurora, Modifier.weight(1f)) { go("tutor") }
            }
        }
        item(key = "volhead") { Hud("Volumes", color = Ice.Dim, modifier = Modifier.padding(top = 8.dp)) }
        items(lib.modulesSorted, key = { "m-" + it.id }) { m ->
            val ls = lib.lessonsByModule[m.id].orEmpty()
            val d = ls.count { it.id in prog.lessons }
            val color = Ice.volume[(m.order - 1).mod(Ice.volume.size)]
            FrostCard(Modifier.fillMaxWidth().testTag("vol_${m.id}"), onClick = { go("volume/${m.id}") }, padding = androidx.compose.foundation.layout.PaddingValues(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(color.copy(alpha = 0.12f)).border(1.dp, color.copy(alpha = 0.5f), RoundedCornerShape(12.dp)), contentAlignment = Alignment.Center) {
                        if (ls.isNotEmpty() && d == ls.size) Icon(Glyph.Check, color, 18.dp)
                        else Text(m.vol, style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold), color = color)
                    }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text(m.title, style = MaterialTheme.typography.titleMedium, color = Ice.Frost, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        Spacer(Modifier.height(8.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Bar(if (ls.isEmpty()) 0f else d / ls.size.toFloat(), color, Modifier.weight(1f))
                            Spacer(Modifier.width(10.dp))
                            Hud("$d/${ls.size}", color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }
        }
        item(key = "foot") { Text("Educational only. Not legal or tax advice.", style = MaterialTheme.typography.bodyMedium, color = Ice.Dim, modifier = Modifier.padding(top = 6.dp)) }
    }
}

/** Level, XP to next level, streak and today's goal. */
@Composable
fun PlayerCard(prog: Progress, lib: Library, onClick: (() -> Unit)?) {
    val xp = Game.xp(prog, lib)
    val lv = Game.level(xp)
    val streak = Game.streak(prog)
    val today = Game.todayXp(prog)
    FrostCard(Modifier.fillMaxWidth().testTag("player_card"), onClick = onClick, accent = Ice.Cyan) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            ProgressRing((today / Game.DAILY_GOAL.toFloat()).coerceAtMost(1f), 68.dp, color = Ice.Mint) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("$today", style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
                    Hud("/${Game.DAILY_GOAL}", color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
                }
            }
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Hud("Level ${lv.index + 1}")
                Text(lv.name, style = MaterialTheme.typography.headlineSmall, color = Ice.Frost)
                Spacer(Modifier.height(6.dp))
                Bar(lv.progress(xp), Ice.Cyan)
                Spacer(Modifier.height(4.dp))
                Hud(Game.nextLevelName(lv)?.let { "$xp XP · ${lv.to!! - xp} to $it" } ?: "$xp XP · top level", color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).clip(CircleShape).background(if (streak > 0) Ice.Amber else Ice.Dim))
            Spacer(Modifier.width(8.dp))
            Text(
                when { streak == 0 -> "Learn something today to start a streak"; streak == 1 -> "1-day streak"; else -> "$streak-day streak" } +
                    if (today >= Game.DAILY_GOAL) " · daily goal done" else " · ${Game.DAILY_GOAL - minOf(today, Game.DAILY_GOAL)} XP to today's goal",
                style = MaterialTheme.typography.bodyMedium, color = Ice.Mist, modifier = Modifier.semantics { contentDescription = "Streak $streak days, $today XP today" },
            )
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
private fun QuickChip(label: String, color: Color, modifier: Modifier, badge: Int = 0, tag: String = "chip_" + label.lowercase(), onClick: () -> Unit) {
    Box(
        modifier.heightIn(min = 64.dp).clip(RoundedCornerShape(16.dp)).background(color.copy(alpha = 0.08f))
            .border(1.dp, color.copy(alpha = 0.4f), RoundedCornerShape(16.dp)).clickable(role = Role.Button, onClick = onClick).testTag(tag)
            .padding(horizontal = 6.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(Glyph.Spark, color, 16.dp)
            Spacer(Modifier.height(6.dp))
            Text(label, style = MaterialTheme.typography.bodyMedium.copy(fontSize = 13.sp), color = Ice.Frost, maxLines = 1)
        }
        if (badge > 0) Box(Modifier.align(Alignment.TopEnd).clip(RoundedCornerShape(50)).background(color).padding(horizontal = 6.dp, vertical = 1.dp)) {
            Text("$badge", style = MaterialTheme.typography.labelSmall, color = Ice.OnCyan)
        }
    }
}
