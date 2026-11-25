package com.abhi.startuplaw.ui.theme

import android.provider.Settings
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.compose.material3.Typography

/** Igloo-inspired palette: night ice, frosted glass, a cold cyan glow. */
object Ice {
    val Night = Color(0xFF05080D)
    val Deep = Color(0xFF0A111B)
    val Glass = Color(0x14CFE9FF)
    val GlassHi = Color(0x24CFE9FF)
    val Edge = Color(0x33CFE9FF)
    val EdgeLo = Color(0x0FCFE9FF)
    val Frost = Color(0xFFEAF4FA)
    val Mist = Color(0xFF9AAEBD)
    val Dim = Color(0xFF5F7282)
    val Cyan = Color(0xFF8FE8FF)
    val CyanDeep = Color(0xFF2BB8E0)
    val Aurora = Color(0xFFB59CFF)
    val Mint = Color(0xFF7CF5C8)
    val Amber = Color(0xFFFFC46B)
    val Coral = Color(0xFFFF8A9A)
    val OnCyan = Color(0xFF03121A)

    /** One accent per volume, all cold hues. */
    val volume = listOf(
        Color(0xFF8FE8FF), Color(0xFFB59CFF), Color(0xFF7CF5C8), Color(0xFF8DB8FF), Color(0xFFFFC46B), Color(0xFFFF9EC7),
        Color(0xFF6FE3D6), Color(0xFFD7C2FF), Color(0xFFFFD9A0), Color(0xFFA8D8FF), Color(0xFF9EF0B0), Color(0xFFCFE9FF),
    )
}

val Mono = FontFamily.Monospace

private val typography = Typography(
    displaySmall = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Light, fontSize = 34.sp, lineHeight = 38.sp, letterSpacing = (-0.5).sp),
    headlineMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Light, fontSize = 28.sp, lineHeight = 33.sp, letterSpacing = (-0.3).sp),
    headlineSmall = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Normal, fontSize = 22.sp, lineHeight = 28.sp),
    titleLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Medium, fontSize = 19.sp, lineHeight = 25.sp),
    titleMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Medium, fontSize = 16.sp, lineHeight = 22.sp),
    bodyLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 16.sp, lineHeight = 25.sp),
    bodyMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 14.sp, lineHeight = 21.sp),
    labelLarge = TextStyle(fontFamily = Mono, fontWeight = FontWeight.Medium, fontSize = 13.sp, letterSpacing = 1.2.sp),
    labelMedium = TextStyle(fontFamily = Mono, fontSize = 11.sp, letterSpacing = 1.4.sp),
    labelSmall = TextStyle(fontFamily = Mono, fontSize = 10.sp, letterSpacing = 1.4.sp),
)

private val scheme = darkColorScheme(
    primary = Ice.Cyan, onPrimary = Ice.OnCyan,
    secondary = Ice.Aurora, onSecondary = Ice.Night,
    tertiary = Ice.Mint,
    background = Ice.Night, onBackground = Ice.Frost,
    surface = Ice.Deep, onSurface = Ice.Frost,
    surfaceVariant = Color(0xFF111B27), onSurfaceVariant = Ice.Mist,
    surfaceContainer = Color(0xFF0D1620), surfaceContainerHigh = Color(0xFF121D2A),
    outline = Ice.Edge, outlineVariant = Ice.EdgeLo,
    error = Ice.Coral,
)

/** True when the phone's animator scale is 0 (Remove animations): we then skip decorative motion. */
val LocalReducedMotion = staticCompositionLocalOf { false }

@Composable
fun IceTheme(content: @Composable () -> Unit) {
    val ctx = LocalContext.current
    val reduced = remember {
        runCatching { Settings.Global.getFloat(ctx.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f }.getOrDefault(false)
    }
    CompositionLocalProvider(LocalReducedMotion provides reduced) {
        MaterialTheme(colorScheme = scheme, typography = typography, content = content)
    }
}
