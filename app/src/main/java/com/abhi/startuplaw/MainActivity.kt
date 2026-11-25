package com.abhi.startuplaw

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.abhi.startuplaw.data.Kind
import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.ui.components.Glyph
import com.abhi.startuplaw.ui.components.Icon
import com.abhi.startuplaw.ui.components.IceBackground
import com.abhi.startuplaw.ui.components.IceButton
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.openExternal
import com.abhi.startuplaw.ui.screens.AboutScreen
import com.abhi.startuplaw.ui.screens.CaseScreen
import com.abhi.startuplaw.ui.screens.GlossaryScreen
import com.abhi.startuplaw.ui.components.Celebrations
import com.abhi.startuplaw.ui.components.LocalWordLookup
import com.abhi.startuplaw.ui.components.LookupCard
import com.abhi.startuplaw.ui.components.WordLookup
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import com.abhi.startuplaw.ui.screens.CasesScreen
import com.abhi.startuplaw.ui.screens.HomeScreen
import com.abhi.startuplaw.ui.screens.LessonScreen
import com.abhi.startuplaw.ui.screens.LoopholesScreen
import com.abhi.startuplaw.ui.screens.MapScreen
import com.abhi.startuplaw.ui.screens.PlaybookScreen
import com.abhi.startuplaw.ui.screens.PracticeScreen
import com.abhi.startuplaw.ui.screens.SearchScreen
import com.abhi.startuplaw.ui.screens.StoryScreen
import com.abhi.startuplaw.ui.screens.TutorScreen
import com.abhi.startuplaw.ui.screens.UpdatesScreen
import com.abhi.startuplaw.ui.screens.VolumeScreen
import com.abhi.startuplaw.ui.theme.Ice
import com.abhi.startuplaw.ui.theme.IceTheme

class MainActivity : ComponentActivity() {
    private val vm: AppViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        val splash = installSplashScreen()
        super.onCreate(savedInstanceState)
        splash.setKeepOnScreenCondition { vm.library.value == null }
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.Transparent.toArgb()),
            navigationBarStyle = SystemBarStyle.dark(Color.Transparent.toArgb()),
        )
        setContent { IceTheme { AppRoot(vm) } }
    }
}

/** Top-level destinations shown in the bottom bar. */
enum class Tab(val route: String, val label: String, val glyph: Glyph) {
    Library("home", "Library", Glyph.Library),
    Cases("cases", "Cases", Glyph.Cases),
    Playbook("playbook", "Playbook", Glyph.Playbook),
    Practice("practice", "Practice", Glyph.Practice),
    Progress("map", "Progress", Glyph.Map),
}

/** Where a search hit, mindmap leaf or link should take you. */
fun routeFor(kind: Kind, id: String): String = when (kind) {
    Kind.Lesson -> "lesson/$id"
    Kind.Case -> "case/$id"
    Kind.Loophole -> "loopholes?focus=$id"
    Kind.Story -> "story/$id"
    Kind.Trap -> "playbook?tab=1&focus=$id"
    Kind.Update -> "updates"
    Kind.Quiz -> "practice"
    Kind.Term -> "glossary"
}

@Composable
fun AppRoot(vm: AppViewModel) {
    val lib by vm.library.collectAsStateWithLifecycle()
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route.orEmpty()
    val tab = Tab.entries.firstOrNull { route.substringBefore('?') == it.route }
    val library = lib
    if (library == null) { IceBackground { }; return }
    val lookup by vm.lookup.collectAsStateWithLifecycle()
    val online by vm.online.collectAsStateWithLifecycle()
    val wordLookup = remember(library) { WordLookup(library.glossaryIndex) { w, t, c -> vm.openLookup(w, t, c) } }

    CompositionLocalProvider(LocalWordLookup provides wordLookup) {
        Box(Modifier.fillMaxSize().background(Ice.Night)) {
            AppNav(nav, vm, library)
            Column(Modifier.align(Alignment.BottomCenter)) {
                UpdateBanner(vm)
                AnimatedVisibility(visible = tab != null, enter = slideInVertically { it } + fadeIn(), exit = slideOutVertically { it } + fadeOut()) {
                    BottomBar(tab) { t -> nav.navigateTab(t.route) }
                }
            }
            Celebrations(vm.rewards)
            lookup?.let { l ->
                LookupCard(l.word, l.term, l.context, online, onClose = vm::closeLookup,
                    onOpenGlossary = if (route == "glossary") null else ({ vm.closeLookup(); nav.navigate("glossary") { launchSingleTop = true } }))
            }
        }
    }
}

fun NavHostController.navigateTab(route: String) = navigate(route) {
    popUpTo(graph.findStartDestination().id) { saveState = true }
    launchSingleTop = true
    restoreState = true
}

@Composable
private fun AppNav(nav: NavHostController, vm: AppViewModel, lib: Library) {
    val back: () -> Unit = { if (!nav.popBackStack()) nav.navigateTab("home") }
    val go: (String) -> Unit = { r -> nav.navigate(r) { launchSingleTop = true } }
    NavHost(
        nav, startDestination = "home",
        enterTransition = { fadeIn(androidx.compose.animation.core.tween(220)) + scaleIn(androidx.compose.animation.core.tween(220), initialScale = 0.985f) },
        exitTransition = { fadeOut(androidx.compose.animation.core.tween(160)) },
        popEnterTransition = { fadeIn(androidx.compose.animation.core.tween(220)) },
        popExitTransition = { fadeOut(androidx.compose.animation.core.tween(160)) + scaleOut(androidx.compose.animation.core.tween(160), targetScale = 0.985f) },
    ) {
        composable("home") { HomeScreen(vm, lib, go) }
        composable("cases?module={module}", arguments = listOf(navArgument("module") { type = NavType.StringType; nullable = true; defaultValue = null })) {
            CasesScreen(vm, lib, it.arguments?.getString("module"), go)
        }
        composable("playbook?tab={tab}&focus={focus}", arguments = listOf(
            navArgument("tab") { type = NavType.IntType; defaultValue = 0 },
            navArgument("focus") { type = NavType.StringType; nullable = true; defaultValue = null },
        )) { PlaybookScreen(vm, lib, it.arguments?.getInt("tab") ?: 0, it.arguments?.getString("focus"), go) }
        composable("practice") { PracticeScreen(vm, lib) }
        composable("map") { MapScreen(vm, lib, go) }
        composable("volume/{id}") { VolumeScreen(vm, lib, it.arguments?.getString("id").orEmpty(), go, back) }
        composable("lesson/{id}") { e ->
            LessonScreen(vm, lib, e.arguments?.getString("id").orEmpty(), go, back) { next -> nav.navigate("lesson/$next") { popUpTo("lesson/{id}") { inclusive = true } } }
        }
        composable("case/{id}") { CaseScreen(lib, it.arguments?.getString("id").orEmpty(), back) }
        composable("story/{id}") { StoryScreen(vm, lib, it.arguments?.getString("id").orEmpty(), back) }
        composable("loopholes?focus={focus}", arguments = listOf(navArgument("focus") { type = NavType.StringType; nullable = true; defaultValue = null })) {
            LoopholesScreen(lib, it.arguments?.getString("focus"), back)
        }
        composable("updates") { UpdatesScreen(vm, lib, go, back) }
        composable("tutor") { TutorScreen(vm, lib, go, back) }
        composable("search") { SearchScreen(vm, lib, go, back) }
        composable("about") { AboutScreen(vm, lib, back) }
        composable("glossary") { GlossaryScreen(vm, lib, back) }
    }
}

@Composable
private fun BottomBar(current: Tab?, onSelect: (Tab) -> Unit) {
    Box(
        Modifier.fillMaxWidth()
            .background(Brush.verticalGradient(0f to Color.Transparent, 0.3f to Ice.Night, 1f to Ice.Night))
            .windowInsetsPadding(WindowInsets.navigationBars)
            .padding(horizontal = 12.dp, vertical = 8.dp)
    ) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(26.dp))
                .background(Color(0xFA0A121C))
                .border(1.dp, Ice.Edge, RoundedCornerShape(26.dp))
                .padding(horizontal = 4.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Tab.entries.forEach { t ->
                val on = t == current
                Column(
                    Modifier.weight(1f).clip(RoundedCornerShape(22.dp))
                        .background(if (on) Ice.Cyan.copy(alpha = 0.14f) else Color.Transparent)
                        .clickable(role = Role.Tab) { onSelect(t) }
                        .semantics { selected = on; contentDescription = t.label }
                        .testTag("tab_${t.route}")
                        .padding(vertical = 8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Icon(t.glyph, if (on) Ice.Cyan else Ice.Mist, 22.dp)
                    Spacer(Modifier.height(4.dp))
                    Text(t.label, style = MaterialTheme.typography.labelSmall, color = if (on) Ice.Cyan else Ice.Mist, maxLines = 1)
                }
            }
        }
    }
}

@Composable
private fun UpdateBanner(vm: AppViewModel) {
    val up by vm.update.collectAsStateWithLifecycle()
    val ctx = LocalContext.current
    AnimatedVisibility(visible = up.available > 0, enter = fadeIn() + slideInVertically { it / 2 }, exit = fadeOut()) {
        Row(
            Modifier.padding(horizontal = 14.dp, vertical = 4.dp).fillMaxWidth()
                .clip(RoundedCornerShape(18.dp)).background(Color(0xF0102231)).border(1.dp, Ice.Cyan.copy(alpha = 0.5f), RoundedCornerShape(18.dp))
                .padding(start = 16.dp, end = 8.dp, top = 8.dp, bottom = 8.dp).testTag("update_banner"),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Hud("App update ready", color = Ice.Cyan)
                Text("Downloads in your browser. Open it to install over this app; your progress stays.", style = MaterialTheme.typography.bodyMedium, color = Ice.Mist)
            }
            IceButton("Get", onClick = { openExternal(ctx, BuildConfig.APK_URL) })
        }
    }
}
