package com.abhi.startuplaw.ui.screens

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.LocalIndication
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.abhi.startuplaw.data.Palette
import com.abhi.startuplaw.data.Swatch
import com.abhi.startuplaw.ui.components.Block
import com.abhi.startuplaw.ui.components.Conceal
import com.abhi.startuplaw.ui.components.ExpandMark
import com.abhi.startuplaw.ui.components.FrostCard
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.Motion
import com.abhi.startuplaw.ui.components.Reveal
import com.abhi.startuplaw.ui.components.SourceLinks
import com.abhi.startuplaw.ui.components.pressScale
import com.abhi.startuplaw.ui.theme.Ice
import com.abhi.startuplaw.ui.theme.LocalReducedMotion
import com.abhi.startuplaw.ui.theme.Mono
import kotlinx.coroutines.delay

private fun Swatch.color(): Color = argb?.let { Color(it) } ?: Color.Gray

/** Readable ink for text drawn on [bg]. */
private fun inkOn(bg: Color): Color = if (bg.luminance() > 0.45f) Color(0xFF111111) else Color(0xFFF7F7F5)

/** A brand-inspired mood board: colour strip, then on tap a live preview, copyable swatches, how to use it and the legal line. */
@Composable
fun PaletteCard(p: Palette, expanded: Boolean, modifier: Modifier = Modifier, toggle: () -> Unit) {
    val accent = (p.role("Primary") ?: p.role("Accent") ?: p.swatches.first()).color()
    FrostCard(modifier.fillMaxWidth().testTag("palette_${p.id}"), onClick = toggle, accent = if (expanded) accent else null) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Hud("Inspired by ${p.brand}", color = Ice.Dim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.weight(1f))
            ExpandMark(expanded)
        }
        Spacer(Modifier.height(4.dp))
        Text(p.title, style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
        Spacer(Modifier.height(12.dp))
        SwatchStrip(p, expanded)
        Spacer(Modifier.height(12.dp))
        Text(p.mood, style = MaterialTheme.typography.bodyMedium, color = Ice.Mist, maxLines = if (expanded) Int.MAX_VALUE else 2)
        AnimatedVisibility(expanded, enter = Reveal, exit = Conceal) {
            Column(Modifier.padding(top = 14.dp)) {
                Hud("Preview", color = Ice.Dim)
                Spacer(Modifier.height(8.dp))
                MoodPreview(p)
                Spacer(Modifier.height(16.dp))
                Hud("Palette · tap a colour to copy it", color = Ice.Dim)
                Spacer(Modifier.height(4.dp))
                p.swatches.forEach { SwatchRow(it) }
                Block("Use it in your strategy", p.use, Ice.Mint)
                Block("Legal guardrail", p.guardrail, Ice.Coral)
                Block("Where the colours come from", p.basis, Ice.Amber)
                SourceLinks(p.src)
            }
        }
    }
}

/** The colours rise into place one after another, and the strip grows when the card opens. */
@Composable
private fun SwatchStrip(p: Palette, expanded: Boolean) {
    val reduced = LocalReducedMotion.current
    val h by animateDpAsState(if (expanded) 84.dp else 52.dp, if (reduced) tween(0) else Motion.settle(), label = "strip")
    Row(Modifier.fillMaxWidth().height(h).clip(RoundedCornerShape(14.dp)).semantics { contentDescription = "${p.brand} palette: " + p.swatches.joinToString { it.name } }) {
        p.swatches.forEachIndexed { i, s ->
            val rise = remember { Animatable(if (reduced) 1f else 0f) }
            LaunchedEffect(Unit) { if (!reduced) { delay(120L + i * 70L); rise.animateTo(1f, tween(520, easing = Motion.Decelerate)) } }
            Box(
                Modifier.weight(1f).fillMaxHeight()
                    .graphicsLayer { scaleY = rise.value; transformOrigin = TransformOrigin(0.5f, 1f); alpha = 0.4f + 0.6f * rise.value }
                    .background(s.color()),
            )
        }
    }
}

/** A tiny live mock-up in the palette: background, headline, button and accent, so you can judge the mood at a glance. */
@Composable
private fun MoodPreview(p: Palette) {
    val bg = (p.role("Background") ?: p.swatches.last()).color()
    val text = p.role("Text")?.color() ?: inkOn(bg)
    val primary = (p.role("Primary") ?: p.role("Accent") ?: p.swatches.first()).color()
    val accent = (p.role("Accent") ?: p.role("Surface") ?: p.swatches.first()).color()
    val surface = p.role("Surface")?.color() ?: bg
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(bg).border(1.dp, Ice.EdgeLo, RoundedCornerShape(18.dp))
            .padding(18.dp).testTag("preview_${p.id}"),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(10.dp).clip(CircleShape).background(accent))
            Spacer(Modifier.width(8.dp))
            Text("YOUR BRAND", style = MaterialTheme.typography.labelSmall, color = text.copy(alpha = 0.75f))
        }
        Spacer(Modifier.height(10.dp))
        Text("A headline in this mood", style = MaterialTheme.typography.headlineSmall, color = text)
        Spacer(Modifier.height(4.dp))
        Text("Supporting line for the offer.", style = MaterialTheme.typography.bodyMedium, color = text.copy(alpha = 0.7f))
        Spacer(Modifier.height(14.dp))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.clip(RoundedCornerShape(50)).background(primary).padding(horizontal = 16.dp, vertical = 9.dp)) {
                Text("Shop now", style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold), color = inkOn(primary))
            }
            Box(Modifier.clip(RoundedCornerShape(50)).background(surface).border(1.dp, text.copy(alpha = 0.25f), RoundedCornerShape(50)).padding(horizontal = 14.dp, vertical = 9.dp)) {
                Text("Learn more", style = MaterialTheme.typography.labelLarge, color = inkOn(surface))
            }
        }
    }
}

@Composable
private fun SwatchRow(s: Swatch) {
    val clipboard = LocalClipboardManager.current
    val haptic = LocalHapticFeedback.current
    var copied by remember { mutableStateOf(false) }
    LaunchedEffect(copied) { if (copied) { delay(1300); copied = false } }
    val source = remember { MutableInteractionSource() }
    Row(
        Modifier.fillMaxWidth().pressScale(source, to = 0.97f).heightIn(min = 56.dp).clip(RoundedCornerShape(14.dp))
            .clickable(interactionSource = source, indication = LocalIndication.current, role = Role.Button) {
                clipboard.setText(AnnotatedString(s.hex.uppercase())); haptic.performHapticFeedback(HapticFeedbackType.LongPress); copied = true
            }
            .semantics { contentDescription = "${s.name}, ${s.hex}. Tap to copy." }
            .testTag("swatch_${s.hex.drop(1).lowercase()}")
            .padding(vertical = 8.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(34.dp).clip(RoundedCornerShape(10.dp)).background(s.color()).border(1.dp, Ice.Edge, RoundedCornerShape(10.dp)))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(s.name + if (s.role.isNotBlank()) " · ${s.role}" else "", style = MaterialTheme.typography.bodyMedium, color = Ice.Frost)
            Text(s.basis, style = MaterialTheme.typography.bodyMedium.copy(fontSize = 11.sp, lineHeight = 14.sp), color = Ice.Dim)
        }
        Spacer(Modifier.width(8.dp))
        AnimatedContent(copied, transitionSpec = {
            (slideInVertically(tween(Motion.SHORT)) { it } + fadeIn(tween(Motion.SHORT))) togetherWith (slideOutVertically(tween(Motion.SHORT)) { -it } + fadeOut(tween(120)))
        }, label = "copied") { done ->
            Text(if (done) "COPIED" else s.hex.uppercase(), style = MaterialTheme.typography.labelLarge.copy(fontFamily = Mono), color = if (done) Ice.Mint else Ice.Cyan)
        }
    }
}
