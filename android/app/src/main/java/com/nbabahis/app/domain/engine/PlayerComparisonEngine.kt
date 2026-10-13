package com.nbabahis.app.domain.engine

import com.nbabahis.app.domain.model.PredictionResult
import com.nbabahis.app.domain.model.StatPrediction

data class StatComparison(
    val statKey: String,
    val displayName: String,
    val player1Value: Double,
    val player2Value: Double,
    val difference: Double,
    val winnerPlayerIndex: Int // 1 if player1 > player2, 2 if player2 > player1, 0 if equal
)

data class ComparisonResult(
    val player1Name: String,
    val player2Name: String,
    val player1Team: String,
    val player2Team: String,
    val comparisons: List<StatComparison>,
    val overallAdvantagePlayer: Int, // 1 or 2
    val summaryText: String
)

object PlayerComparisonEngine {

    fun comparePlayers(p1: PredictionResult, p2: PredictionResult): ComparisonResult {
        val player1Name = p1.player.name
        val player2Name = p2.player.name
        val player1Team = p1.player.teamAbbr
        val player2Team = p2.player.teamAbbr

        val statComparisons = mutableListOf<StatComparison>()

        val p1Stats = p1.predictions.associateBy { it.statKey }
        val p2Stats = p2.predictions.associateBy { it.statKey }

        val commonStatKeys = p1Stats.keys.intersect(p2Stats.keys)

        var p1Wins = 0
        var p2Wins = 0
        var ties = 0

        for (statKey in commonStatKeys) {
            val p1Prediction = p1Stats[statKey] ?: continue
            val p2Prediction = p2Stats[statKey] ?: continue

            val p1Value = p1Prediction.predictedValue
            val p2Value = p2Prediction.predictedValue

            val difference = ((p1Value - p2Value) * 10.0).toInt() / 10.0
            val winnerIndex = when {
                difference > 0 -> 1
                difference < 0 -> 2
                else -> 0
            }

            when (winnerIndex) {
                1 -> p1Wins++
                2 -> p2Wins++
                0 -> ties++
            }

            statComparisons.add(
                StatComparison(
                    statKey = statKey,
                    displayName = p1Prediction.displayName,
                    player1Value = p1Value,
                    player2Value = p2Value,
                    difference = difference,
                    winnerPlayerIndex = winnerIndex
                )
            )
        }

        val overallAdvantagePlayer = when {
            p1Wins > p2Wins -> 1
            p2Wins > p1Wins -> 2
            else -> 0
        }

        val summaryText = buildString {
            append("Head-to-head comparison between $player1Name ($player1Team) and $player2Name ($player2Team). ")
            append("Player 1 leads in $p1Wins stats, Player 2 leads in $p2Wins stats, and $ties stats are tied. ")
            when (overallAdvantagePlayer) {
                1 -> append("$player1Name has the overall advantage.")
                2 -> append("$player2Name has the overall advantage.")
                0 -> append("The players are evenly matched.")
            }
        }

        return ComparisonResult(
            player1Name = player1Name,
            player2Name = player2Name,
            player1Team = player1Team,
            player2Team = player2Team,
            comparisons = statComparisons,
            overallAdvantagePlayer = overallAdvantagePlayer,
            summaryText = summaryText
        )
    }
}
