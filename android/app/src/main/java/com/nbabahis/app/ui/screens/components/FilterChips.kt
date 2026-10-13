package com.nbabahis.app.ui.screens.components

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.nbabahis.app.ui.theme.AccentGreen
import com.nbabahis.app.ui.theme.CardDark

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FilterChips(
    selectedFilter: String,
    onFilterSelected: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val filters = listOf(
        "ALL" to "Tümü",
        "PTS" to "Sayı (PTS)",
        "REB" to "Ribaund (REB)",
        "AST" to "Asist (AST)",
        "3PM" to "3'lük (3PM)",
        "PRA" to "Kombi (PRA)",
        "DEF" to "Savunma (STL/BLK)"
    )

    Row(
        modifier = modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        filters.forEach { (key, label) ->
            val isSelected = selectedFilter == key
            FilterChip(
                selected = isSelected,
                onClick = { onFilterSelected(key) },
                label = { Text(label) },
                colors = FilterChipDefaults.filterChipColors(
                    selectedContainerColor = AccentGreen,
                    selectedLabelColor = CardDark,
                    containerColor = CardDark
                )
            )
        }
    }
}
