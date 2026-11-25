package com.abhi.startuplaw.ui.screens

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.abhi.startuplaw.AppViewModel
import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.ui.components.Bar
import com.abhi.startuplaw.ui.components.Bullet
import com.abhi.startuplaw.ui.components.CardShape
import com.abhi.startuplaw.ui.components.EmptyNote
import com.abhi.startuplaw.ui.components.FilterPill
import com.abhi.startuplaw.ui.components.FrostCard
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.IceButton
import com.abhi.startuplaw.ui.components.ProgressRing
import com.abhi.startuplaw.ui.components.Screen
import com.abhi.startuplaw.ui.components.hudFrame
import com.abhi.startuplaw.ui.theme.Ice
import com.abhi.startuplaw.ui.theme.LocalReducedMotion

@Composable
fun PracticeScreen(vm: AppViewModel, lib: Library) {
    var tab by rememberSaveable { mutableStateOf(0) }
    Screen(title = "Practice", hud = "Quiz · flashcards", onBack = null) {
        item(key = "tabs") {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterPill("Quiz · ${lib.quiz.size}", tab == 0, { tab = 0 })
                FilterPill("Flashcards · ${vm.deck(lib).size}", tab == 1, { tab = 1 })
            }
        }
        if (tab == 0) item(key = "quiz") { Quiz(vm, lib) } else item(key = "cards") { Flashcards(vm, lib) }
    }
}

@Composable
private fun Quiz(vm: AppViewModel, lib: Library) {
    val s by vm.quiz.collectAsStateWithLifecycle()
    val prog by vm.progress.collectAsStateWithLifecycle()
    val haptic = LocalHapticFeedback.current
    LaunchedEffect(lib) { vm.ensureQuiz(lib) }
    if (lib.quiz.isEmpty()) { EmptyNote("No quiz questions yet."); return }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        ModuleFilter(lib, s.module, { vm.startQuiz(lib, it) }, lib.quiz.map { it.module }.toSet())
        val mastered = lib.quiz.count { prog.quiz[it.id] == 1 }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Hud("Mastered $mastered / ${lib.quiz.size}", color = Ice.Dim, modifier = Modifier.weight(1f))
            if (s.order.isNotEmpty() && !s.done) Hud("Q ${s.index + 1} / ${s.order.size} · ${s.right} right", color = Ice.Cyan)
        }
        if (s.done) {
            FrostCard(Modifier.fillMaxWidth().testTag("quiz_done"), accent = Ice.Cyan) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val f = if (s.answered == 0) 0f else s.right / s.answered.toFloat()
                    ProgressRing(f, 72.dp) { Text("${s.right}/${s.answered}", style = MaterialTheme.typography.titleMedium, color = Ice.Frost) }
                    Spacer(Modifier.width(16.dp))
                    Column(Modifier.weight(1f)) {
                        Hud("Round complete")
                        Text(if (f >= 0.8f) "Strong round." else if (f >= 0.5f) "Getting there." else "Worth another pass.", style = MaterialTheme.typography.titleLarge, color = Ice.Frost)
                    }
                }
                Spacer(Modifier.height(14.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    IceButton("Retry missed", onClick = { vm.startQuiz(lib, s.module, onlyMissed = true) }, modifier = Modifier.weight(1f), primary = false)
                    IceButton("New round", onClick = { vm.startQuiz(lib, s.module) }, modifier = Modifier.weight(1f))
                }
            }
            return@Column
        }
        val q = lib.quiz.firstOrNull { it.id == s.order.getOrNull(s.index) }
        if (q == null) { EmptyNote("Loading questions…"); return@Column }
        Bar((s.index) / s.order.size.toFloat(), Ice.Cyan)
        Column(Modifier.fillMaxWidth().hudFrame().padding(16.dp)) {
            Hud(lib.moduleTitle(q.module), color = Ice.Aurora, style = MaterialTheme.typography.labelSmall)
            Spacer(Modifier.height(8.dp))
            Text(q.q, style = MaterialTheme.typography.titleLarge, color = Ice.Frost, modifier = Modifier.testTag("quiz_question"))
        }
        q.opts.forEachIndexed { i, opt ->
            val picked = s.picked
            val color = when {
                picked == null -> Ice.Edge
                i == q.a -> Ice.Mint
                i == picked -> Ice.Coral
                else -> Ice.EdgeLo
            }
            val fill = when {
                picked == null -> Ice.Glass
                i == q.a -> Ice.Mint.copy(alpha = 0.14f)
                i == picked -> Ice.Coral.copy(alpha = 0.14f)
                else -> Color.Transparent
            }
            Row(
                Modifier.fillMaxWidth().heightIn(min = 56.dp).clip(RoundedCornerShape(16.dp)).background(fill).border(1.dp, color, RoundedCornerShape(16.dp))
                    .clickable(enabled = picked == null, role = Role.Button) {
                        haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove); vm.pick(lib, i)
                    }
                    .testTag("opt_$i").padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("ABCDEFG"[i].toString(), style = MaterialTheme.typography.labelLarge, color = if (picked != null && i == q.a) Ice.Mint else Ice.Cyan, modifier = Modifier.width(26.dp))
                Text(opt, style = MaterialTheme.typography.bodyLarge, color = Ice.Frost, modifier = Modifier.weight(1f))
                if (picked != null && i == q.a) Text("✓", color = Ice.Mint, style = MaterialTheme.typography.titleMedium)
                if (picked == i && i != q.a) Text("✕", color = Ice.Coral, style = MaterialTheme.typography.titleMedium)
            }
        }
        if (s.picked != null) {
            val right = s.picked == q.a
            FrostCard(Modifier.fillMaxWidth(), accent = if (right) Ice.Mint else Ice.Coral) {
                Hud(if (right) "Correct" else "Not quite", color = if (right) Ice.Mint else Ice.Coral)
                Spacer(Modifier.height(6.dp))
                Text(q.why, style = MaterialTheme.typography.bodyMedium, color = Ice.Frost)
            }
            IceButton(if (s.index + 1 >= s.order.size) "See score" else "Next question", onClick = { vm.nextQuestion() }, modifier = Modifier.fillMaxWidth().testTag("quiz_next"))
        }
    }
}

@Composable
private fun Flashcards(vm: AppViewModel, lib: Library) {
    val s by vm.cards.collectAsStateWithLifecycle()
    val prog by vm.progress.collectAsStateWithLifecycle()
    val all = vm.deck(lib)
    val deck = if (s.unknownOnly) all.filter { prog.cards[it.id] != "k" } else all
    val known = all.count { prog.cards[it.id] == "k" }
    val reduced = LocalReducedMotion.current
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterPill("All cards", !s.unknownOnly, { vm.setUnknownOnly(false) })
            FilterPill("Still learning · ${all.size - known}", s.unknownOnly, { vm.setUnknownOnly(true) })
        }
        Hud("Known $known / ${all.size}", color = Ice.Dim)
        val card = deck.getOrNull(s.index)
        if (card == null) {
            FrostCard(Modifier.fillMaxWidth(), accent = Ice.Cyan) {
                Hud(if (deck.isEmpty()) "Nothing left to learn here" else "End of deck")
                Spacer(Modifier.height(6.dp))
                Text(if (deck.isEmpty()) "You know every card. New ones appear as the library updates." else "You went through ${deck.size} cards.", style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
                Spacer(Modifier.height(12.dp))
                IceButton("Start again", onClick = { vm.restartCards() }, modifier = Modifier.fillMaxWidth())
            }
            return@Column
        }
        Hud("Card ${s.index + 1} / ${deck.size}", color = Ice.Cyan)
        val rot by animateFloatAsState(if (s.flipped) 180f else 0f, tween(if (reduced) 0 else 420), label = "flip")
        Box(
            Modifier.fillMaxWidth().heightIn(min = 300.dp)
                .graphicsLayer { rotationY = rot; cameraDistance = 14f * density }
                .clip(CardShape)
                .background(androidx.compose.ui.graphics.Brush.verticalGradient(listOf(Ice.GlassHi, Ice.Glass)))
                .border(1.dp, if (rot > 90f) Ice.Cyan.copy(alpha = 0.6f) else Ice.Edge, CardShape)
                .clickable(role = Role.Button) { vm.flip() }
                .semantics { contentDescription = if (s.flipped) "Card answer. Tap to flip back" else "Card question. Tap to see the answer" }
                .testTag("flashcard")
                .padding(22.dp),
        ) {
            if (rot <= 90f) {
                Column {
                    Hud("${card.kind.label} · ${lib.moduleTitle(card.module)}", color = Ice.Aurora, style = MaterialTheme.typography.labelSmall)
                    Spacer(Modifier.height(18.dp))
                    Text(card.front, style = MaterialTheme.typography.headlineSmall, color = Ice.Frost)
                    Spacer(Modifier.height(24.dp))
                    Hud("Tap to reveal", color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
                }
            } else {
                Column(Modifier.graphicsLayer { rotationY = 180f }) {
                    Hud("Answer", color = Ice.Cyan, style = MaterialTheme.typography.labelSmall)
                    Spacer(Modifier.height(12.dp))
                    Text(card.back, style = MaterialTheme.typography.bodyLarge, color = Ice.Frost)
                    card.points.take(4).forEach { Bullet(it, tappable = false) }
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            IceButton("Again", onClick = { vm.answerCard(card.id, false) }, modifier = Modifier.weight(1f).testTag("card_again"), primary = false, color = Ice.Amber)
            IceButton("Know it", onClick = { vm.answerCard(card.id, true) }, modifier = Modifier.weight(1f).testTag("card_know"))
        }
        Spacer(Modifier.size(1.dp))
    }
}
