package com.abhi.startuplaw.ui.components

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.browser.customtabs.CustomTabColorSchemeParams
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.abhi.startuplaw.data.Link
import com.abhi.startuplaw.ui.theme.Ice
import com.abhi.startuplaw.ui.theme.LocalReducedMotion
import kotlinx.coroutines.delay

val CardShape = RoundedCornerShape(20.dp)
val PillShape = RoundedCornerShape(50)

/** Frosted-glass panel with a faint top-lit edge. */
@Composable
fun FrostCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    accent: Color? = null,
    padding: PaddingValues = PaddingValues(18.dp),
    content: @Composable ColumnScope.() -> Unit,
) {
    val edge = Brush.verticalGradient(listOf(accent?.copy(alpha = 0.55f) ?: Ice.Edge, Ice.EdgeLo))
    Column(
        modifier
            .clip(CardShape)
            .background(Brush.verticalGradient(listOf(Ice.GlassHi, Ice.Glass)))
            .border(BorderStroke(1.dp, edge), CardShape)
            .then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
            .padding(padding),
        content = content,
    )
}

/** Monospace HUD label, the igloo-style overlay text. */
@Composable
fun Hud(text: String, modifier: Modifier = Modifier, color: Color = Ice.Cyan.copy(alpha = 0.85f), style: TextStyle = MaterialTheme.typography.labelMedium) {
    Text(text.uppercase(), modifier, color = color, style = style, maxLines = 2, overflow = TextOverflow.Ellipsis)
}

private const val GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789§¶#/<>*+=-"

/** Text that decodes from random glyphs into place, once per screen visit. */
@Composable
fun ScrambleText(text: String, style: TextStyle, modifier: Modifier = Modifier, color: Color = Ice.Frost, maxLines: Int = Int.MAX_VALUE) {
    val reduced = LocalReducedMotion.current
    var played by rememberSaveable(text) { mutableStateOf(reduced) }
    var shown by remember(text) { mutableStateOf(if (played) text else scramble(text, 0f)) }
    LaunchedEffect(text) {
        if (played) { shown = text; return@LaunchedEffect }
        val steps = 16
        for (i in 1..steps) { shown = scramble(text, i / steps.toFloat()); delay(28) }
        shown = text; played = true
    }
    Text(shown, modifier.semantics { contentDescription = text; heading() }, style = style, color = color, maxLines = maxLines, overflow = TextOverflow.Ellipsis)
}

private fun scramble(text: String, p: Float): String {
    val fixed = (text.length * p).toInt()
    return buildString(text.length) {
        text.forEachIndexed { i, c -> append(if (i < fixed || c.isWhitespace() || !c.isLetterOrDigit()) c else GLYPHS.random()) }
    }
}

@Composable
fun Pill(text: String, color: Color = Ice.Cyan, modifier: Modifier = Modifier, filled: Boolean = false) {
    Box(
        modifier
            .clip(PillShape)
            .background(if (filled) color else color.copy(alpha = 0.10f))
            .border(1.dp, color.copy(alpha = if (filled) 1f else 0.45f), PillShape)
            .padding(horizontal = 10.dp, vertical = 4.dp),
    ) {
        Text(text.uppercase(), style = MaterialTheme.typography.labelSmall, color = if (filled) Ice.OnCyan else color, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** Selectable filter chip (48dp touch target). */
@Composable
fun FilterPill(text: String, selected: Boolean, onClick: () -> Unit, color: Color = Ice.Cyan) {
    Box(
        Modifier
            .heightIn(min = 40.dp)
            .clip(PillShape)
            .background(if (selected) color else Color.Transparent)
            .border(1.dp, if (selected) color else Ice.Edge, PillShape)
            .clickable(role = Role.Tab, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge, color = if (selected) Ice.OnCyan else Ice.Frost, maxLines = 1)
    }
}

@Composable
fun IceButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, primary: Boolean = true, enabled: Boolean = true, color: Color = Ice.Cyan) {
    val c = if (enabled) color else Ice.Dim
    Box(
        modifier
            .heightIn(min = 48.dp)
            .clip(PillShape)
            .background(if (primary) c else Color.Transparent)
            .border(1.dp, if (primary) c else c.copy(alpha = 0.6f), PillShape)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 22.dp, vertical = 13.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text.uppercase(), style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold), color = if (primary) Ice.OnCyan else c, maxLines = 1)
    }
}

/** Thin HUD corner brackets around content, like a targeting frame. */
fun Modifier.hudFrame(color: Color = Ice.Cyan.copy(alpha = 0.5f), len: Dp = 14.dp) = drawBehind {
    val l = len.toPx(); val s = 1.5.dp.toPx()
    fun corner(x: Float, y: Float, dx: Float, dy: Float) {
        drawLine(color, Offset(x, y), Offset(x + dx * l, y), s, StrokeCap.Square)
        drawLine(color, Offset(x, y), Offset(x, y + dy * l), s, StrokeCap.Square)
    }
    corner(0f, 0f, 1f, 1f); corner(size.width, 0f, -1f, 1f)
    corner(0f, size.height, 1f, -1f); corner(size.width, size.height, -1f, -1f)
}

@Composable
fun ProgressRing(fraction: Float, size: Dp, stroke: Dp = 6.dp, color: Color = Ice.Cyan, content: @Composable () -> Unit = {}) {
    val reduced = LocalReducedMotion.current
    val anim = remember { Animatable(if (reduced) fraction else 0f) }
    LaunchedEffect(fraction) { if (reduced) anim.snapTo(fraction) else anim.animateTo(fraction, tween(900, easing = FastOutSlowInEasing)) }
    Box(Modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(size)) {
            val w = stroke.toPx()
            drawArc(Ice.Edge, -90f, 360f, false, style = Stroke(w), topLeft = Offset(w / 2, w / 2), size = androidx.compose.ui.geometry.Size(this.size.width - w, this.size.height - w))
            drawArc(
                Brush.sweepGradient(listOf(Ice.CyanDeep, color, Ice.Frost, Ice.CyanDeep)), -90f, 360f * anim.value, false,
                style = Stroke(w, cap = StrokeCap.Round), topLeft = Offset(w / 2, w / 2), size = androidx.compose.ui.geometry.Size(this.size.width - w, this.size.height - w),
            )
        }
        content()
    }
}

@Composable
fun Bar(fraction: Float, color: Color, modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().height(4.dp).clip(PillShape).background(Ice.Edge)) {
        Box(Modifier.fillMaxWidth(fraction.coerceIn(0f, 1f)).height(4.dp).clip(PillShape).background(color))
    }
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier, hud: String? = null) {
    Column(modifier.padding(top = 8.dp, bottom = 4.dp)) {
        if (hud != null) Hud(hud, color = Ice.Dim)
        Text(text, style = MaterialTheme.typography.titleLarge, color = Ice.Frost, modifier = Modifier.semantics { heading() })
    }
}

/** A labelled block of prose inside a detail screen. */
@Composable
fun Block(label: String, text: String, color: Color = Ice.Cyan) {
    if (text.isBlank()) return
    Column(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(6.dp).clip(CircleShape).background(color))
            Spacer(Modifier.width(8.dp))
            Hud(label, color = color)
        }
        Spacer(Modifier.height(6.dp))
        Text(text, style = MaterialTheme.typography.bodyLarge, color = Ice.Frost.copy(alpha = 0.92f))
    }
}

@Composable
fun Bullet(text: String, color: Color = Ice.Cyan) {
    Row(Modifier.padding(vertical = 4.dp)) {
        Text("◆", color = color, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(top = 4.dp, end = 10.dp))
        Text(text, style = MaterialTheme.typography.bodyMedium, color = Ice.Frost)
    }
}

@Composable
fun SourceLinks(links: List<Link>) {
    val ctx = LocalContext.current
    val safe = links.filter { it.isSafe }
    if (safe.isEmpty()) return
    Column(Modifier.fillMaxWidth().padding(top = 8.dp)) {
        Hud("Sources", color = Ice.Dim)
        safe.forEach { l ->
            Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp).clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { openLink(ctx, l.u) }.padding(vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("↗", color = Ice.Cyan, style = MaterialTheme.typography.titleMedium, modifier = Modifier.width(26.dp))
                Column(Modifier.weight(1f)) {
                    Text(l.t.ifBlank { Uri.parse(l.u).host ?: l.u }, style = MaterialTheme.typography.bodyMedium, color = Ice.Frost)
                    Text(Uri.parse(l.u).host.orEmpty(), style = MaterialTheme.typography.labelSmall, color = Ice.Dim, maxLines = 1)
                }
            }
        }
    }
}

@Composable
fun RowScope.Stat(value: String, label: String, color: Color = Ice.Frost) {
    Column(Modifier.weight(1f)) {
        Text(value, style = MaterialTheme.typography.headlineSmall, color = color)
        Hud(label, color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
fun EmptyNote(text: String) {
    Text(text, style = MaterialTheme.typography.bodyMedium, color = Ice.Mist, modifier = Modifier.padding(vertical = 24.dp))
}

fun statusColor(s: String): Color {
    val t = s.lowercase()
    return when {
        t.startsWith("good law") || "kept control" in t || "survived" in t || "won" in t || "in place" in t -> Ice.Mint
        "ongoing" in t || "narrow" in t || "partly" in t || "rework" in t -> Ice.Amber
        "closed" in t || "abolished" in t || "supersed" in t || "ousted" in t || "lost" in t || "collapsed" in t || "bankrupt" in t -> Ice.Coral
        else -> Ice.Aurora
    }
}

/** Opens an https link in a dark Custom Tab, falling back to any browser. Never crashes. */
fun openLink(ctx: Context, url: String) {
    if (!url.startsWith("https://")) return
    val uri = Uri.parse(url)
    runCatching {
        val params = CustomTabColorSchemeParams.Builder().setToolbarColor(Ice.Night.toArgb()).setNavigationBarColor(Ice.Night.toArgb()).build()
        CustomTabsIntent.Builder().setDefaultColorSchemeParams(params).setColorScheme(CustomTabsIntent.COLOR_SCHEME_DARK).setShowTitle(true)
            .build().launchUrl(ctx, uri)
    }.recoverCatching {
        ctx.startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }.onFailure { if (it !is ActivityNotFoundException) it.printStackTrace() }
}

/** Opens a link in whichever app handles it (e.g. the Claude app for claude.ai links). */
fun openExternal(ctx: Context, url: String) {
    if (!url.startsWith("https://")) return
    runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
        .onFailure { openLink(ctx, url) }
}
