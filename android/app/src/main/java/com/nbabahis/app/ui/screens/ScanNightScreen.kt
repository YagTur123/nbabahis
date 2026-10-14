package com.nbabahis.app.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Security
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nbabahis.app.domain.model.PredictionResult
import com.nbabahis.app.ui.screens.components.FilterChips
import com.nbabahis.app.ui.screens.components.PredictionCard
import com.nbabahis.app.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScanNightScreen(
    results: List<PredictionResult>,
    activeFilter: String,
    onFilterSelected: (String) -> Unit,
    onBackClicked: () -> Unit,
    modifier: Modifier = Modifier
) {
    var searchQuery by remember { mutableStateOf("") }

    val filteredResults = remember(results, searchQuery) {
        if (searchQuery.isBlank()) results
        else results.filter {
            it.player.name.contains(searchQuery, ignoreCase = true) ||
                    it.player.teamAbbr.contains(searchQuery, ignoreCase = true) ||
                    it.opponentAbbr.contains(searchQuery, ignoreCase = true)
        }
    }

    val totalSafeFloors = remember(results) {
        results.sumOf { r ->
            r.predictions.count { p -> p.safeFloorLine != null && p.safeFloorProb >= 0.88 }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = "Gece Taraması",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = TextPrimary
                        )
                        Text(
                            text = "${results.size} Oyuncu Analiz Edildi",
                            style = MaterialTheme.typography.labelSmall,
                            color = AccentGreen
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBackClicked) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Geri",
                            tint = TextPrimary
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = BgDark)
            )
        },
        containerColor = BgDark,
        modifier = modifier
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Stats summary card
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 6.dp),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceDark),
                border = BorderStroke(1.dp, CardBorder)
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text("Taranan Oyuncu", style = MaterialTheme.typography.labelSmall, color = TextMuted)
                        Text(
                            text = "${results.size}",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace,
                            color = AccentCyan
                        )
                    }

                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("🛡️ %90+ Kasa Fırsatı", style = MaterialTheme.typography.labelSmall, color = AccentGold)
                        Text(
                            text = "$totalSafeFloors Adet",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace,
                            color = AccentGold
                        )
                    }

                    Column(horizontalAlignment = Alignment.End) {
                        Text("Filtrelenen", style = MaterialTheme.typography.labelSmall, color = TextMuted)
                        Text(
                            text = "${filteredResults.size}",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace,
                            color = AccentGreen
                        )
                    }
                }
            }

            // Search Bar
            OutlinedTextField(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 6.dp),
                placeholder = { Text("Oyuncu veya takım ara (LAL, Curry, Tatum...)", fontSize = 13.sp, color = TextMuted) },
                leadingIcon = {
                    Icon(imageVector = Icons.Default.Search, contentDescription = null, tint = TextSecondary, modifier = Modifier.size(18.dp))
                },
                trailingIcon = {
                    if (searchQuery.isNotEmpty()) {
                        IconButton(onClick = { searchQuery = "" }) {
                            Icon(imageVector = Icons.Default.Clear, contentDescription = "Temizle", tint = TextSecondary, modifier = Modifier.size(18.dp))
                        }
                    }
                },
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = AccentCyan,
                    unfocusedBorderColor = CardBorder,
                    focusedTextColor = TextPrimary,
                    unfocusedTextColor = TextPrimary,
                    focusedContainerColor = SurfaceDark,
                    unfocusedContainerColor = SurfaceDark
                ),
                singleLine = true
            )

            // Category Filter Chips
            FilterChips(
                selectedFilter = activeFilter,
                onFilterSelected = onFilterSelected
            )

            // Results List
            if (filteredResults.isEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(32.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = if (searchQuery.isNotEmpty()) "Aramaya uygun oyuncu bulunamadı." else "Henüz tarama yapılmadı.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextMuted,
                        textAlign = TextAlign.Center
                    )
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    items(filteredResults, key = { it.player.playerId }) { pred ->
                        PredictionCard(
                            result = pred,
                            filter = activeFilter
                        )
                    }
                }
            }
        }
    }
}
