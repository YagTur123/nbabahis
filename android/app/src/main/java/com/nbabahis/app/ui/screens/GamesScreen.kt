package com.nbabahis.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nbabahis.app.ui.screens.components.FilterChips
import com.nbabahis.app.ui.screens.components.GameCard
import com.nbabahis.app.ui.screens.components.PredictionCard
import com.nbabahis.app.ui.theme.*
import com.nbabahis.app.ui.viewmodel.UiState
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GamesScreen(
    uiState: UiState,
    onDateSelected: (LocalDate) -> Unit,
    onGameSelected: (com.nbabahis.app.data.model.NbaGame) -> Unit,
    onTeamSelected: (String) -> Unit,
    onPlayerSelected: (com.nbabahis.app.data.model.NbaPlayer) -> Unit,
    onFilterSelected: (String) -> Unit,
    onScanNightClicked: () -> Unit,
    onBacktestClicked: () -> Unit,
    modifier: Modifier = Modifier
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = "NBA Predictor",
                            style = MaterialTheme.typography.titleLarge,
                            color = TextPrimary
                        )
                        Text(
                            text = "Native İstatistik & Projeksiyon Motoru",
                            style = MaterialTheme.typography.labelSmall,
                            color = AccentGreen
                        )
                    }
                },
                actions = {
                    FilledTonalButton(
                        onClick = onBacktestClicked,
                        colors = ButtonDefaults.filledTonalButtonColors(
                            containerColor = CardDark,
                            contentColor = AccentGreen
                        ),
                        modifier = Modifier.padding(end = 6.dp)
                    ) {
                        Text("📈 Doğrula", fontSize = 12.sp)
                    }
                    FilledTonalButton(
                        onClick = onScanNightClicked,
                        colors = ButtonDefaults.filledTonalButtonColors(
                            containerColor = AccentPurple,
                            contentColor = TextPrimary
                        ),
                        modifier = Modifier.padding(end = 8.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.AutoAwesome,
                            contentDescription = "Geceyi Tara",
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Geceyi Tara", fontSize = 12.sp)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = BgDark
                )
            )
        },
        containerColor = BgDark,
        modifier = modifier
    ) { paddingValues ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
            contentPadding = PaddingValues(bottom = 32.dp)
        ) {
            // 1. Date Selector Bar
            item {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val isToday = uiState.selectedDate == LocalDate.now()
                    val isTmrw = uiState.selectedDate == LocalDate.now().plusDays(1)

                    FilterChip(
                        selected = isToday,
                        onClick = { onDateSelected(LocalDate.now()) },
                        label = { Text("Bugün") },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = AccentGreen,
                            selectedLabelColor = CardDark
                        )
                    )

                    FilterChip(
                        selected = isTmrw,
                        onClick = { onDateSelected(LocalDate.now().plusDays(1)) },
                        label = { Text("Yarın") },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = AccentGreen,
                            selectedLabelColor = CardDark
                        )
                    )

                    Text(
                        text = "Tarih: ${uiState.selectedDate}",
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier
                            .align(Alignment.CenterVertically)
                            .padding(start = 8.dp)
                    )
                }
            }

            // 2. Loading Indicator
            if (uiState.isLoading) {
                item {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        CircularProgressIndicator(color = AccentGreen)
                        if (uiState.progressMessage.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(10.dp))
                            Text(
                                text = uiState.progressMessage,
                                style = MaterialTheme.typography.bodyMedium,
                                color = TextSecondary
                            )
                        }
                    }
                }
            }

            // 3. Match List (Horizontal or Vertical Cards)
            item {
                Text(
                    text = "Günün Maçları (${uiState.games.size})",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                )
            }

            item {
                LazyRow(
                    contentPadding = PaddingValues(horizontal = 16.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(uiState.games) { game ->
                        val isSelected = uiState.selectedGame?.gameId == game.gameId
                        GameCard(
                            game = game,
                            isSelected = isSelected,
                            onClick = { onGameSelected(game) },
                            modifier = Modifier.width(220.dp)
                        )
                    }
                }
            }

            // 4. Selected Match Roster & Team Switcher
            uiState.selectedGame?.let { game ->
                item {
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = "Takım ve Oyuncu Seç",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                    )

                    // Team Switcher
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        val isHome = uiState.selectedTeamAbbr == game.homeTeamAbbr
                        Button(
                            onClick = { onTeamSelected(game.homeTeamAbbr) },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (isHome) AccentGreen else CardDark,
                                contentColor = if (isHome) CardDark else TextPrimary
                            ),
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("${game.homeTeamAbbr} (Ev Sahibi)")
                        }

                        Button(
                            onClick = { onTeamSelected(game.awayTeamAbbr) },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (!isHome) AccentGreen else CardDark,
                                contentColor = if (!isHome) CardDark else TextPrimary
                            ),
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("${game.awayTeamAbbr} (Deplasman)")
                        }
                    }

                    // Player Selector Horizontal Chips
                    LazyRow(
                        contentPadding = PaddingValues(horizontal = 16.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(uiState.teamRoster) { player ->
                            val isPlayerSelected = uiState.selectedPlayer?.playerId == player.playerId
                            val isInjured = player.injuryStatus?.contains("OUT", ignoreCase = true) == true

                            InputChip(
                                selected = isPlayerSelected,
                                onClick = { if (!isInjured) onPlayerSelected(player) },
                                label = {
                                    Text(
                                        text = if (isInjured) "${player.name} (OUT)" else "${player.name} (${player.position})",
                                        color = if (isInjured) HotRed else if (isPlayerSelected) CardDark else TextPrimary
                                    )
                                },
                                colors = InputChipDefaults.inputChipColors(
                                    selectedContainerColor = AccentGreen,
                                    containerColor = CardDark
                                )
                            )
                        }
                    }
                }
            }

            // 5. Stat Filter Chips
            if (uiState.playerPrediction != null) {
                item {
                    Spacer(modifier = Modifier.height(12.dp))
                    FilterChips(
                        selectedFilter = uiState.statFilter,
                        onFilterSelected = onFilterSelected
                    )
                }

                // 6. Detailed Player Prediction Card
                item {
                    Box(modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                        PredictionCard(
                            result = uiState.playerPrediction,
                            filter = uiState.statFilter
                        )
                    }
                }
            }
        }
    }
}
