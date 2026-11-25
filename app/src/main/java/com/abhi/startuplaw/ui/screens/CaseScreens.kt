package com.abhi.startuplaw.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.abhi.startuplaw.AppViewModel
import com.abhi.startuplaw.data.Library
import com.abhi.startuplaw.ui.components.Block
import com.abhi.startuplaw.ui.components.EmptyNote
import com.abhi.startuplaw.ui.components.FilterPill
import com.abhi.startuplaw.ui.components.FrostCard
import com.abhi.startuplaw.ui.components.Hud
import com.abhi.startuplaw.ui.components.Pill
import com.abhi.startuplaw.ui.components.Screen
import com.abhi.startuplaw.ui.components.ScrambleText
import com.abhi.startuplaw.ui.components.SourceLinks
import com.abhi.startuplaw.ui.components.statusColor
import com.abhi.startuplaw.ui.theme.Ice

@Composable
fun ModuleFilter(lib: Library, selected: String?, onSelect: (String?) -> Unit, only: Set<String>? = null) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(vertical = 4.dp)) {
        item(key = "all") { FilterPill("All", selected == null, { onSelect(null) }) }
        items(lib.modulesSorted.filter { only == null || it.id in only }, key = { it.id }) { m ->
            FilterPill("${m.vol} · ${m.title.substringBefore(',').substringBefore(':').substringBefore(" &")}", selected == m.id, { onSelect(m.id) })
        }
    }
}

@Composable
fun CasesScreen(vm: AppViewModel, lib: Library, initialModule: String?, go: (String) -> Unit) {
    var module by rememberSaveable { mutableStateOf(initialModule) }
    val list = lib.casesSorted.filter { module == null || it.module == module }
    Screen(title = "Cases & precedents", hud = "${lib.cases.size} judgments · newest first", onBack = null) {
        item(key = "filter") { ModuleFilter(lib, module, { module = it }, lib.cases.map { it.module }.toSet()) }
        if (list.isEmpty()) item(key = "empty") { EmptyNote("No cases in this volume yet.") }
        items(list, key = { it.id }) { c ->
            FrostCard(Modifier.fillMaxWidth().testTag("case_${c.id}"), onClick = { go("case/${c.id}") }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Hud("${c.year} · ${c.court}", color = Ice.Dim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.weight(1f))
                    Pill(c.status, statusColor(c.status))
                }
                Spacer(Modifier.height(8.dp))
                Text(c.name, style = MaterialTheme.typography.titleMedium, color = Ice.Frost, maxLines = 3, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(6.dp))
                Text(c.held, style = MaterialTheme.typography.bodyMedium, color = Ice.Mist, maxLines = 3, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CaseScreen(lib: Library, id: String, back: () -> Unit) {
    val c = lib.caseById[id]
    Screen(title = c?.name ?: "Case", hud = c?.let { "${it.court} · ${it.year}" } ?: "Case", onBack = back) {
        if (c == null) { item { EmptyNote("This case is no longer in the library.") }; return@Screen }
        item(key = "head") {
            Column(Modifier.padding(top = 10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Pill(c.status, statusColor(c.status))
                    Spacer(Modifier.width(8.dp))
                    Hud(lib.moduleTitle(c.module), color = Ice.Dim, style = MaterialTheme.typography.labelSmall)
                }
                Spacer(Modifier.height(10.dp))
                ScrambleText(c.name, MaterialTheme.typography.headlineSmall)
                Spacer(Modifier.height(8.dp))
                Hud(listOf(c.court, c.date, c.citation).filter { it.isNotBlank() }.joinToString(" · "), color = Ice.Mist, style = MaterialTheme.typography.labelSmall)
            }
        }
        item(key = "facts") { FrostCard(Modifier.fillMaxWidth()) { Block("Facts", c.facts, Ice.Mist) } }
        item(key = "held") { FrostCard(Modifier.fillMaxWidth(), accent = Ice.Cyan) { Block("Held", c.held, Ice.Cyan) } }
        item(key = "why") { FrostCard(Modifier.fillMaxWidth(), accent = Ice.Mint) { Block("Why it matters for founders", c.why, Ice.Mint) } }
        if (c.tags.isNotEmpty()) item(key = "tags") {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { c.tags.forEach { Pill(it, Ice.Aurora) } }
        }
        item(key = "src") { SourceLinks(listOfNotNull(c.src)) }
    }
}
