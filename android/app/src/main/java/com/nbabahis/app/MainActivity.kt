package com.nbabahis.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.animation.Crossfade
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.SportsBasketball
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nbabahis.app.ui.screens.BacktestScreen
import com.nbabahis.app.ui.screens.GamesScreen
import com.nbabahis.app.ui.screens.SafeSlateScreen
import com.nbabahis.app.ui.screens.ScanNightScreen
import com.nbabahis.app.ui.theme.*
import com.nbabahis.app.ui.viewmodel.NbaPredictorViewModel

class MainActivity : ComponentActivity() {

    private val viewModel: NbaPredictorViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            NbaPredictorTheme {
                val uiState by viewModel.uiState.collectAsState()
                var currentScreen by remember { mutableStateOf("GAMES") }

                Scaffold(
                    modifier = Modifier.fillMaxSize(),
                    containerColor = BgDark,
                    bottomBar = {
                        NavigationBar(
                            containerColor = SurfaceDark,
                            tonalElevation = 8.dp
                        ) {
                            NavigationBarItem(
                                selected = currentScreen == "GAMES",
                                onClick = { currentScreen = "GAMES" },
                                icon = {
                                    Icon(
                                        imageVector = Icons.Default.SportsBasketball,
                                        contentDescription = "Maçlar",
                                        modifier = Modifier.size(20.dp)
                                    )
                                },
                                label = { Text("Maçlar", fontSize = 11.sp) },
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = CardDark,
                                    selectedTextColor = AccentCyan,
                                    indicatorColor = AccentCyan,
                                    unselectedIconColor = TextMuted,
                                    unselectedTextColor = TextMuted
                                )
                            )

                            NavigationBarItem(
                                selected = currentScreen == "SAFE_SLATE",
                                onClick = {
                                    if (uiState.scanNightResults.isEmpty()) {
                                        viewModel.scanNight()
                                    }
                                    currentScreen = "SAFE_SLATE"
                                },
                                icon = {
                                    Icon(
                                        imageVector = Icons.Default.Security,
                                        contentDescription = "Kasa",
                                        modifier = Modifier.size(20.dp)
                                    )
                                },
                                label = { Text("%90+ Kasa", fontSize = 11.sp) },
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = CardDark,
                                    selectedTextColor = AccentGold,
                                    indicatorColor = AccentGold,
                                    unselectedIconColor = TextMuted,
                                    unselectedTextColor = TextMuted
                                )
                            )

                            NavigationBarItem(
                                selected = currentScreen == "SCAN_NIGHT",
                                onClick = {
                                    if (uiState.scanNightResults.isEmpty()) {
                                        viewModel.scanNight()
                                    }
                                    currentScreen = "SCAN_NIGHT"
                                },
                                icon = {
                                    Icon(
                                        imageVector = Icons.Default.AutoAwesome,
                                        contentDescription = "Tara",
                                        modifier = Modifier.size(20.dp)
                                    )
                                },
                                label = { Text("Geceyi Tara", fontSize = 11.sp) },
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = CardDark,
                                    selectedTextColor = AccentPurple,
                                    indicatorColor = AccentPurple,
                                    unselectedIconColor = TextMuted,
                                    unselectedTextColor = TextMuted
                                )
                            )

                            NavigationBarItem(
                                selected = currentScreen == "BACKTEST",
                                onClick = {
                                    viewModel.runBacktest()
                                    currentScreen = "BACKTEST"
                                },
                                icon = {
                                    Icon(
                                        imageVector = Icons.Default.BarChart,
                                        contentDescription = "Doğrulama",
                                        modifier = Modifier.size(20.dp)
                                    )
                                },
                                label = { Text("Doğrulama", fontSize = 11.sp) },
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = CardDark,
                                    selectedTextColor = AccentGreen,
                                    indicatorColor = AccentGreen,
                                    unselectedIconColor = TextMuted,
                                    unselectedTextColor = TextMuted
                                )
                            )
                        }
                    }
                ) { innerPadding ->
                    Crossfade(
                        targetState = currentScreen,
                        label = "screen_transition",
                        modifier = Modifier.padding(innerPadding)
                    ) { screen ->
                        when (screen) {
                            "GAMES" -> {
                                GamesScreen(
                                    uiState = uiState,
                                    onDateSelected = { viewModel.setDate(it) },
                                    onGameSelected = { viewModel.selectGame(it) },
                                    onTeamSelected = { viewModel.selectTeam(it) },
                                    onPlayerSelected = { viewModel.selectPlayer(it) },
                                    onFilterSelected = { viewModel.setFilter(it) },
                                    onScanNightClicked = {
                                        viewModel.scanNight()
                                        currentScreen = "SCAN_NIGHT"
                                    },
                                    onBacktestClicked = {
                                        viewModel.runBacktest()
                                        currentScreen = "BACKTEST"
                                    }
                                )
                            }
                            "SAFE_SLATE" -> {
                                SafeSlateScreen(
                                    results = uiState.scanNightResults,
                                    onBackClicked = { currentScreen = "GAMES" }
                                )
                            }
                            "SCAN_NIGHT" -> {
                                ScanNightScreen(
                                    results = uiState.scanNightResults,
                                    activeFilter = uiState.statFilter,
                                    onFilterSelected = { viewModel.setFilter(it) },
                                    onBackClicked = { currentScreen = "GAMES" }
                                )
                            }
                            "BACKTEST" -> {
                                BacktestScreen(
                                    report = uiState.backtestReport,
                                    onBackClicked = { currentScreen = "GAMES" },
                                    onRunBacktestClicked = { viewModel.runBacktest() }
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
