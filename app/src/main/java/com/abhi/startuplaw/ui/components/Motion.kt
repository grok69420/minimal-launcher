package com.abhi.startuplaw.ui.components

import android.os.SystemClock
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.dp
import com.abhi.startuplaw.ui.theme.Ice
import com.abhi.startuplaw.ui.theme.LocalReducedMotion
import kotlinx.coroutines.delay

/** One motion language for the whole app: Material 3 "emphasized" curves and soft springs. */
object Motion {
    val Emphasized = CubicBezierEasing(0.2f, 0f, 0f, 1f)
    val Decelerate = CubicBezierEasing(0.05f, 0.7f, 0.1f, 1f)
    val Accelerate = CubicBezierEasing(0.3f, 0f, 0.8f, 0.15f)
    const val SHORT = 200
    const val MEDIUM = 320
    const val LONG = 450
    /** Springs used for anything the finger touches. */
    fun <T> touch() = spring<T>(dampingRatio = 0.55f, stiffness = 700f)
    fun <T> settle() = spring<T>(dampingRatio = 0.82f, stiffness = Spring.StiffnessMediumLow)
}

/** Shrinks a little while held and springs back on release. Pair with clickable(interactionSource = source). */
fun Modifier.pressScale(source: MutableInteractionSource, enabled: Boolean = true, to: Float = 0.965f): Modifier = composed {
    val pressed by source.collectIsPressedAsState()
    val reduced = LocalReducedMotion.current
    val s by animateFloatAsState(if (enabled && pressed && !reduced) to else 1f, Motion.touch(), label = "press")
    graphicsLayer { scaleX = s; scaleY = s }
}

/** Created once per screen visit; lets the first cards on a screen rise in one after another. */
class Entrance(val start: Long = SystemClock.uptimeMillis()) { var count = 0 }

val LocalEntrance = staticCompositionLocalOf<Entrance?> { null }

/**
 * Fades and lifts content into place, staggered, but only for what is on screen in the first moment
 * of a visit. Anything composed later (scrolling, expanding) just appears, so lists never feel slow.
 */
fun Modifier.appear(): Modifier = composed {
    val e = LocalEntrance.current
    val reduced = LocalReducedMotion.current
    val slot = remember {
        if (e == null || reduced || SystemClock.uptimeMillis() - e.start > 450) null
        else (e.count++).coerceAtMost(7) to Animatable(0f)
    }
    if (slot == null) return@composed this
    val (order, a) = slot
    LaunchedEffect(Unit) {
        delay(order * 45L)
        a.animateTo(1f, tween(Motion.LONG, easing = Motion.Decelerate))
    }
    graphicsLayer {
        alpha = a.value
        translationY = (1f - a.value) * 22.dp.toPx()
    }
}

/** "+" that turns into "×" when its card opens. */
@Composable
fun ExpandMark(expanded: Boolean) {
    val reduced = LocalReducedMotion.current
    val r by animateFloatAsState(if (expanded) 45f else 0f, if (reduced) tween(0) else Motion.settle(), label = "expand")
    Text("+", style = MaterialTheme.typography.titleLarge, color = if (expanded) Ice.Frost else Ice.Mist, modifier = Modifier.graphicsLayer { rotationZ = r })
}

/** Opening and closing a card's details: the space grows on a spring and the text fades in after it. */
val Reveal = androidx.compose.animation.expandVertically(spring(dampingRatio = 0.9f, stiffness = Spring.StiffnessMediumLow)) +
    androidx.compose.animation.fadeIn(tween(260, delayMillis = 60))
val Conceal = androidx.compose.animation.shrinkVertically(tween(260, easing = Motion.Emphasized)) +
    androidx.compose.animation.fadeOut(tween(140))
