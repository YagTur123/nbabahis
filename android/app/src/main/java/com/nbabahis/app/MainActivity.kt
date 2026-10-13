package com.nbabahis.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.animation.Crossfade
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import com.nbabahis.app.ui.screens.GamesScreen
import com.nbabahis.app.ui.screens.ScanNightScreen
import com.nbabahis.app.ui.theme.BgDark
import com.nbabahis.app.ui.theme.NbaPredictorTheme
import com.nbabahis.app.ui.viewmodel.NbaPredictorViewModel

class MainActivity : ComponentActivity() {

    private val viewModel: NbaPredictorViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            NbaPredictorTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = BgDark
                ) {
                    val uiState by viewModel.uiState.collectAsState()
                    var currentScreen by remember { mutableStateOf("GAMES") }

                    Crossfade(targetState = currentScreen, label = "screen_transition") { screen ->
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
                            "SCAN_NIGHT" -> {
                                ScanNightScreen(
                                    results = uiState.scanNightResults,
                                    activeFilter = uiState.statFilter,
                                    onFilterSelected = { viewModel.setFilter(it) },
                                    onBackClicked = { currentScreen = "GAMES" }
                                )
                            }
                            "BACKTEST" -> {
                                com.nbabahis.app.ui.screens.BacktestScreen(
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
