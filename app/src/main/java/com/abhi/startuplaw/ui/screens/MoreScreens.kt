package com.abhi.startuplaw.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.abhi.startuplaw.AppViewModel
import com.abhi.startuplaw.BuildConfig
import com.abhi.startuplaw.data.Hit
import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.data.Source
import com.abhi.startuplaw.data.Study
import com.abhi.startuplaw.routeFor
import com.abhi.startuplaw.ui.components.EmptyNote
import com.abhi.startuplaw.ui.components.FrostCard
import com.abhi.startuplaw.ui.components.Glyph
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.IceButton
import com.abhi.startuplaw.ui.components.Icon
import com.abhi.startuplaw.ui.components.Pill
import com.abhi.startuplaw.ui.components.Screen
import com.abhi.startuplaw.ui.components.SourceLinks
import com.abhi.startuplaw.ui.components.openExternal
import com.abhi.startuplaw.ui.theme.Ice
import java.text.DateFormat
import java.util.Date

@Composable
fun UpdatesScreen(vm: AppViewModel, lib: Library, go: (String) -> Unit, back: () -> Unit) {
    val prog by vm.progress.collectAsStateWithLifecycle()
    val seenAtOpen = remember { prog.seen }
    // Mark as seen when leaving, so "new" badges stay visible while you read.
    DisposableEffect(Unit) { onDispose { vm.markUpdatesSeen(lib.latestUpdateDate) } }
    Screen(title = "Updates", hud = "Law changes · founder watch · checked ${lib.meta.lastChecked}", onBack = back) {
        item(key = "intro") {
            Text(lib.meta.note.ifBlank { "New judgments, rules and founder developments, newest first." }, style = MaterialTheme.typography.bodyMedium, color = Ice.Mist)
        }
        items(lib.updatesSorted, key = { it.id }) { u ->
            val fresh = u.date > seenAtOpen
            FrostCard(Modifier.fillMaxWidth().testTag("update_${u.id}"), accent = if (fresh) Ice.Amber else null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Hud(u.date, color = if (fresh) Ice.Amber else Ice.Dim, style = MaterialTheme.typography.labelSmall)
                    Spacer(Modifier.width(8.dp))
                    Pill(u.kind, Ice.Aurora)
                    Spacer(Modifier.weight(1f))
                    if (fresh) Pill("New", Ice.Amber, filled = true)
                }
                Spacer(Modifier.height(8.dp))
                Text(u.title, style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
                Spacer(Modifier.height(4.dp))
                Text(u.summary, style = MaterialTheme.typography.bodyMedium, color = Ice.Mist)
                Hud(lib.moduleTitle(u.module), color = Ice.Dim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp).clickable { go("volume/${u.module}") })
                SourceLinks(listOfNotNull(u.src))
            }
        }
    }
}

@Composable
private fun QueryField(value: String, onChange: (String) -> Unit, placeholder: String, onDone: () -> Unit, tag: String, autoFocus: Boolean, singleLine: Boolean = true) {
    val focus = remember { FocusRequester() }
    val kb = LocalSoftwareKeyboardController.current
    LaunchedEffect(Unit) { if (autoFocus) runCatching { focus.requestFocus() } }
    Box(
        Modifier.fillMaxWidth().heightIn(min = 56.dp).clip(RoundedCornerShape(16.dp)).background(Ice.Glass).border(1.dp, Ice.Cyan.copy(alpha = 0.45f), RoundedCornerShape(16.dp))
            .padding(horizontal = 16.dp, vertical = 16.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        if (value.isEmpty()) Text(placeholder, color = Ice.Dim, style = MaterialTheme.typography.bodyLarge)
        BasicTextField(
            value = value, onValueChange = { onChange(it.take(600)) },
            textStyle = MaterialTheme.typography.bodyLarge.copy(color = Ice.Frost),
            cursorBrush = SolidColor(Ice.Cyan), singleLine = singleLine, maxLines = if (singleLine) 1 else 5,
            keyboardOptions = KeyboardOptions(imeAction = if (singleLine) ImeAction.Search else ImeAction.Default),
            keyboardActions = KeyboardActions(onSearch = { kb?.hide(); onDone() }),
            modifier = Modifier.fillMaxWidth().focusRequester(focus).testTag(tag),
        )
    }
}

@Composable
private fun HitCard(lib: Library, h: Hit, go: (String) -> Unit) {
    FrostCard(Modifier.fillMaxWidth(), onClick = { go(routeFor(h.kind, h.id)) }) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Pill(h.kind.label, Ice.Aurora)
            Spacer(Modifier.width(8.dp))
            Hud(lib.moduleTitle(h.module), color = Ice.Dim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.weight(1f))
        }
        Spacer(Modifier.height(8.dp))
        Text(h.title, style = MaterialTheme.typography.titleMedium, color = Ice.Frost)
        if (h.snippet.isNotBlank()) Text(h.snippet, style = MaterialTheme.typography.bodyMedium, color = Ice.Mist, maxLines = 3, overflow = TextOverflow.Ellipsis)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SearchScreen(vm: AppViewModel, lib: Library, go: (String) -> Unit, back: () -> Unit) {
    var q by rememberSaveable { mutableStateOf("") }
    val index = vm.index(lib)
    val hits = remember(q, lib) { if (q.isBlank()) emptyList() else index.search(q, 40) }
    Screen(title = "Search", hud = "Whole library · works offline", onBack = back) {
        item(key = "field") { QueryField(q, { q = it }, "e.g. ESOP tax, Tiger Global, drag-along", {}, "search_field", autoFocus = true) }
        if (q.isBlank()) item(key = "sugg") {
            Column {
                Hud("Try", color = Ice.Dim)
                Spacer(Modifier.height(8.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("non-compete", "reverse flip", "GAAR", "ESOP", "Press Note 3", "liquidation preference", "DPDP", "Byju").forEach { s ->
                        Box(Modifier.clip(RoundedCornerShape(50)).border(1.dp, Ice.Edge, RoundedCornerShape(50)).clickable(role = Role.Button) { q = s }.padding(horizontal = 14.dp, vertical = 10.dp)) {
                            Text(s, style = MaterialTheme.typography.bodyMedium, color = Ice.Frost)
                        }
                    }
                }
            }
        } else {
            item(key = "count") { Hud("${hits.size} matches", color = Ice.Dim) }
            if (hits.isEmpty()) item(key = "none") { EmptyNote("No matches. Try fewer words, or ask the tutor.") }
            items(hits, key = { it.kind.name + it.id }) { h -> HitCard(lib, h, go) }
        }
    }
}

private val SUGGESTIONS = listOf(
    "Can investors stop me starting another company?",
    "What happens to ESOPs in a reverse flip?",
    "Is a Mauritius holding company still worth it?",
    "Which term-sheet clauses can cost me control?",
)

@Composable
fun TutorScreen(vm: AppViewModel, lib: Library, go: (String) -> Unit, back: () -> Unit) {
    val online by vm.online.collectAsStateWithLifecycle()
    val ctx = LocalContext.current
    var q by rememberSaveable { mutableStateOf("") }
    var asked by rememberSaveable { mutableStateOf("") }
    val answer = remember(asked, lib) { if (asked.isBlank()) null else Study.tutor(lib, vm.index(lib), asked) }
    Screen(title = "Ask the tutor", hud = "Notes first · then Claude", onBack = back) {
        item(key = "how") {
            Text(
                "Type a question. The app finds the notes in your library that answer it (works offline). Online, tap Ask Claude to open Claude with those notes attached, so the answer stays grounded in the library. Educational only.",
                style = MaterialTheme.typography.bodyMedium, color = Ice.Mist,
            )
        }
        item(key = "field") { QueryField(q, { q = it }, "Your question", { if (q.isNotBlank()) asked = q.trim() }, "tutor_field", autoFocus = false, singleLine = false) }
        item(key = "ask") {
            IceButton("Find in library", onClick = { if (q.isNotBlank()) asked = q.trim() }, enabled = q.isNotBlank(), modifier = Modifier.fillMaxWidth().testTag("tutor_find"))
        }
        if (asked.isBlank()) item(key = "sugg") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Hud("Try asking", color = Ice.Dim)
                SUGGESTIONS.forEach { s ->
                    FrostCard(Modifier.fillMaxWidth(), onClick = { q = s; asked = s }, padding = androidx.compose.foundation.layout.PaddingValues(14.dp)) {
                        Text(s, style = MaterialTheme.typography.bodyMedium, color = Ice.Frost)
                    }
                }
            }
        }
        if (answer != null) {
            item(key = "claude") {
                FrostCard(Modifier.fillMaxWidth(), accent = Ice.Aurora) {
                    Hud("Explain it with Claude", color = Ice.Aurora)
                    Spacer(Modifier.height(6.dp))
                    Text(
                        if (online) "Opens a new Claude chat with your question and the ${answer.notes.size} matching notes filled in. Review and send it there."
                        else "You're offline. The notes below are from your library; connect to the internet to ask Claude.",
                        style = MaterialTheme.typography.bodyMedium, color = Ice.Mist,
                    )
                    Spacer(Modifier.height(12.dp))
                    IceButton("Ask Claude", onClick = { openExternal(ctx, Study.claudeUrl(answer.prompt)) }, enabled = online, color = Ice.Aurora, modifier = Modifier.fillMaxWidth().testTag("tutor_claude"))
                }
            }
            item(key = "nh") { Hud(if (answer.notes.isEmpty()) "Not covered in the library notes" else "From the library · ${answer.notes.size} notes", color = Ice.Dim) }
            items(answer.notes, key = { "n-" + it.kind.name + it.id }) { h -> HitCard(lib, h, go) }
        }
    }
}

@Composable
fun AboutScreen(vm: AppViewModel, lib: Library, back: () -> Unit) {
    val c by vm.content.collectAsStateWithLifecycle()
    val online by vm.online.collectAsStateWithLifecycle()
    val up by vm.update.collectAsStateWithLifecycle()
    var confirm by remember { mutableStateOf(false) }
    val fmt = remember { DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT) }
    Screen(title = "Sync & app", hud = "Offline-first · signed updates", onBack = back) {
        item(key = "net") {
            FrostCard(Modifier.fillMaxWidth(), accent = if (online) Ice.Mint else Ice.Amber) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Glyph.Sync, if (online) Ice.Mint else Ice.Amber)
                    Spacer(Modifier.width(10.dp))
                    Hud(if (online) "Online" else "Offline — using the copy on this phone", color = if (online) Ice.Mint else Ice.Amber)
                }
                Spacer(Modifier.height(10.dp))
                Row { Text("Library checked for new law", Modifier.weight(1f), color = Ice.Mist); Text(lib.meta.lastChecked, color = Ice.Frost) }
                Row { Text("Copy in use", Modifier.weight(1f), color = Ice.Mist); Text(when (c.source) { Source.Bundled -> "Built into app"; Source.Saved -> "Downloaded earlier"; Source.Synced -> "Just downloaded" }, color = Ice.Frost) }
                Row { Text("Last sync", Modifier.weight(1f), color = Ice.Mist); Text(if (c.lastSyncAt == 0L) "Never" else fmt.format(Date(c.lastSyncAt)), color = Ice.Frost) }
                if (c.lastResult.isNotBlank()) Text(c.lastResult, style = MaterialTheme.typography.bodyMedium, color = Ice.Dim, modifier = Modifier.padding(top = 6.dp))
                Spacer(Modifier.height(12.dp))
                IceButton(if (c.syncing) "Syncing…" else "Sync now", onClick = { vm.syncNow() }, enabled = online && !c.syncing, modifier = Modifier.fillMaxWidth().testTag("sync_now"))
            }
        }
        item(key = "app") {
            FrostCard(Modifier.fillMaxWidth()) {
                Hud("App")
                Spacer(Modifier.height(6.dp))
                Row { Text("Version", Modifier.weight(1f), color = Ice.Mist); Text("${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})", color = Ice.Frost) }
                Row { Text("Newer build", Modifier.weight(1f), color = Ice.Mist); Text(if (up.available > 0) "Build ${up.available} ready" else "None found", color = Ice.Frost) }
                Spacer(Modifier.height(12.dp))
                IceButton("Check for app update", onClick = { vm.syncNow() }, primary = false, enabled = online, modifier = Modifier.fillMaxWidth())
            }
        }
        item(key = "sec") {
            FrostCard(Modifier.fillMaxWidth()) {
                Hud("Privacy & security")
                Spacer(Modifier.height(6.dp))
                listOf(
                    "No account and no tracking. Your progress is stored only on this phone (and in your phone's own backup).",
                    "Library downloads are accepted only when signed with this app's own release key, and never replace a newer copy with an older one.",
                    "App updates install only if the download is this app, signed with the same key.",
                    "HTTPS only. Source links open in your browser.",
                ).forEach { Text("· $it", style = MaterialTheme.typography.bodyMedium, color = Ice.Mist, modifier = Modifier.padding(vertical = 3.dp)) }
            }
        }
        item(key = "reset") {
            IceButton("Reset my progress", onClick = { confirm = true }, primary = false, color = Ice.Coral, modifier = Modifier.fillMaxWidth())
        }
        item(key = "legal") { Text("Educational only. Not legal or tax advice; for a real decision speak to a lawyer or CA.", style = MaterialTheme.typography.bodyMedium, color = Ice.Dim) }
    }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = Ice.Deep, titleContentColor = Ice.Frost, textContentColor = Ice.Mist,
        title = { Text("Reset progress?") },
        text = { Text("This clears lessons learned, stories studied, quiz answers and flashcards on this phone. It can't be undone.") },
        confirmButton = { TextButton(onClick = { vm.resetProgress(); confirm = false }) { Text("Reset", color = Ice.Coral) } },
        dismissButton = { TextButton(onClick = { confirm = false }) { Text("Cancel", color = Ice.Frost) } },
    )
}
