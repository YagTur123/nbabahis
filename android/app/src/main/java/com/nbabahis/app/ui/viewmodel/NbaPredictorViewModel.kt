package com.nbabahis.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.nbabahis.app.data.model.NbaGame
import com.nbabahis.app.data.model.NbaPlayer
import com.nbabahis.app.data.repository.NbaRepository
import com.nbabahis.app.domain.model.PredictionResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter

data class UiState(
    val selectedDate: LocalDate = LocalDate.now(),
    val games: List<NbaGame> = emptyList(),
    val selectedGame: NbaGame? = null,
    val selectedTeamAbbr: String? = null,
    val teamRoster: List<NbaPlayer> = emptyList(),
    val selectedPlayer: NbaPlayer? = null,
    val playerPrediction: PredictionResult? = null,
    val scanNightResults: List<PredictionResult> = emptyList(),
    val backtestReport: com.nbabahis.app.domain.engine.BacktestReport? = null,
    val statFilter: String = "ALL", // "ALL", "PTS", "REB", "AST", "3PM", "PRA", "DEF"
    val isLoading: Boolean = false,
    val progressMessage: String = "",
    val error: String? = null
)

class NbaPredictorViewModel(
    private val repository: NbaRepository = NbaRepository()
) : ViewModel() {

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    init {
        loadInjuriesAndGames()
    }

    private fun loadInjuriesAndGames() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, progressMessage = "Sakatlık raporları ve maçlar getiriliyor...") }
            try {
                repository.loadInjuries()
                val dateStr = _uiState.value.selectedDate.format(DateTimeFormatter.ISO_LOCAL_DATE)
                val games = repository.getGames(dateStr)
                _uiState.update {
                    it.copy(
                        games = games,
                        isLoading = false,
                        progressMessage = ""
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        error = "Veri alınamadı: ${e.message}"
                    )
                }
            }
        }
    }

    fun setDate(date: LocalDate) {
        _uiState.update { it.copy(selectedDate = date, selectedGame = null, selectedPlayer = null, playerPrediction = null) }
        viewModelScope.launch {
            val dateStr = date.format(DateTimeFormatter.ISO_LOCAL_DATE)
            _uiState.update { it.copy(isLoading = true, progressMessage = "$dateStr maçları yükleniyor...") }
            val games = repository.getGames(dateStr)
            _uiState.update { it.copy(games = games, isLoading = false, progressMessage = "") }
        }
    }

    fun selectGame(game: NbaGame) {
        _uiState.update {
            it.copy(
                selectedGame = game,
                selectedTeamAbbr = game.homeTeamAbbr,
                selectedPlayer = null,
                playerPrediction = null
            )
        }
        loadTeamRoster(game.homeTeamId, game.homeTeamAbbr)
    }

    fun selectTeam(teamAbbr: String) {
        val game = _uiState.value.selectedGame ?: return
        _uiState.update { it.copy(selectedTeamAbbr = teamAbbr, selectedPlayer = null, playerPrediction = null) }
        val teamId = if (teamAbbr == game.homeTeamAbbr) game.homeTeamId else game.awayTeamId
        loadTeamRoster(teamId, teamAbbr)
    }

    private fun loadTeamRoster(teamId: Int, teamAbbr: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, progressMessage = "$teamAbbr kadrosu alınıyor...") }
            val roster = repository.getRoster(teamId, teamAbbr)
            _uiState.update {
                it.copy(
                    teamRoster = roster,
                    isLoading = false,
                    progressMessage = ""
                )
            }
            // Auto predict first star player if available
            val firstStar = roster.firstOrNull { it.injuryStatus?.contains("OUT", ignoreCase = true) != true }
            firstStar?.let { selectPlayer(it) }
        }
    }

    fun selectPlayer(player: NbaPlayer) {
        val game = _uiState.value.selectedGame ?: return
        val isHome = player.teamAbbr == game.homeTeamAbbr
        val oppAbbr = if (isHome) game.awayTeamAbbr else game.homeTeamAbbr

        _uiState.update { it.copy(selectedPlayer = player, isLoading = true, progressMessage = "${player.name} istatistik modelleri çalıştırılıyor...") }

        viewModelScope.launch {
            val oppTeamId = if (isHome) game.awayTeamId else game.homeTeamId
            val oppRoster = repository.getRoster(oppTeamId, oppAbbr)
            val pred = repository.predictForPlayer(
                player = player,
                teamRoster = _uiState.value.teamRoster,
                opponentRoster = oppRoster,
                opponentAbbr = oppAbbr,
                isHome = isHome,
                targetDate = _uiState.value.selectedDate
            )
            _uiState.update {
                it.copy(
                    playerPrediction = pred,
                    isLoading = false,
                    progressMessage = ""
                )
            }
        }
    }

    fun scanNight() {
        val games = _uiState.value.games
        if (games.isEmpty()) return

        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, progressMessage = "Günün tüm maçları taranıyor ve tahminler üretiliyor...") }
            val results = repository.scanNightPredictions(games, _uiState.value.selectedDate)
            _uiState.update {
                it.copy(
                    scanNightResults = results,
                    isLoading = false,
                    progressMessage = ""
                )
            }
        }
    }

    fun setFilter(filter: String) {
        _uiState.update { it.copy(statFilter = filter) }
    }

    fun runBacktest() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, progressMessage = "Geçmiş maç sonuçları ve modeller doğrulanıyor...") }
            val predictions = if (_uiState.value.scanNightResults.isNotEmpty()) {
                _uiState.value.scanNightResults
            } else {
                repository.scanNightPredictions(_uiState.value.games)
            }

            val actuals = mutableMapOf<Int, com.nbabahis.app.data.model.PlayerGameLog>()
            for (pred in predictions) {
                val logs = repository.getPlayerLogs(pred.player)
                if (logs.isNotEmpty()) {
                    actuals[pred.player.playerId] = logs.first()
                }
            }

            val report = com.nbabahis.app.domain.engine.BacktestTrackerEngine.evaluateBacktest(predictions, actuals)
            _uiState.update {
                it.copy(
                    backtestReport = report,
                    scanNightResults = predictions,
                    isLoading = false,
                    progressMessage = ""
                )
            }
        }
    }

    fun clearSelection() {
        _uiState.update {
            it.copy(
                selectedGame = null,
                selectedTeamAbbr = null,
                selectedPlayer = null,
                playerPrediction = null
            )
        }
    }
}
