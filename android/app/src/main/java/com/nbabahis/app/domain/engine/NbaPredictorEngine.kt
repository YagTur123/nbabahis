package com.nbabahis.app.domain.engine

import com.nbabahis.app.data.model.NbaPlayer
import com.nbabahis.app.data.model.PlayerGameLog
import com.nbabahis.app.data.model.TeamStats
import com.nbabahis.app.domain.model.*
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import kotlin.math.roundToInt
import kotlin.math.sqrt

object NbaPredictorEngine {

    private const val MIN_GAMES_REQUIRED = 5
    private const val MIN_MINUTES_THRESHOLD = 12.0

    // Floor limits for realistic NBA projections
    private val FLOORS = mapOf(
        "PTS" to 4.0,
        "REB" to 1.5,
        "AST" to 1.0,
        "3PM" to 0.5,
        "STL" to 0.3,
        "BLK" to 0.2,
        "PRA" to 7.0,
        "P+R" to 6.0,
        "P+A" to 5.5
    )

    fun predictPlayer(
        player: NbaPlayer,
        history: List<PlayerGameLog>,
        teamRoster: List<NbaPlayer>,
        teamStats: TeamStats?,
        opponentStats: TeamStats?,
        isHome: Boolean,
        targetDate: LocalDate = LocalDate.now()
    ): PredictionResult? {
        if (history.size < MIN_GAMES_REQUIRED) return null

        // Check if player is strictly OUT
        if (player.injuryStatus?.contains("OUT", ignoreCase = true) == true) {
            return null
        }

        val avgMinutes = history.map { it.min }.average()
        if (avgMinutes < MIN_MINUTES_THRESHOLD) return null

        val lastGame = history.first()
        val lastDate = try {
            LocalDate.parse(lastGame.gameDate.take(10))
        } catch (_: Exception) {
            targetDate.minusDays(2)
        }
        val restDays = ChronoUnit.DAYS.between(lastDate, targetDate).toInt().coerceAtLeast(0)

        // 1. Travel & Altitude Fatigue
        val fatigueFactor = TravelFatigueCalculator.calculateFatigue(
            teamAbbr = player.teamAbbr,
            isHome = isHome,
            oppAbbr = opponentStats?.teamAbbr ?: "",
            history = history,
            targetDate = targetDate
        )

        // 2. Blowout Risk
        val ownMargin = teamStats?.avgMargin ?: 0.0
        val oppMargin = opponentStats?.avgMargin ?: 0.0
        val marginDiff = kotlin.math.abs(ownMargin - oppMargin)
        val blowoutRisk = marginDiff > 12.0
        val blowoutModifier = if (blowoutRisk) {
            if (avgMinutes >= 32.0) 0.88 else if (avgMinutes >= 28.0) 0.93 else 1.05
        } else {
            1.0
        }

        // 3. Team Usage Boost (Teammate absences)
        val usageBoost = UsageShiftCalculator.calculateUsageMultiplier(player, teamRoster)

        // 4. Opponent Defense & Pace Factors
        val oppDefRating = opponentStats?.defRating ?: 114.0
        val oppPace = opponentStats?.pace ?: 99.0
        val defFactor = (oppDefRating / 114.0).coerceIn(0.90, 1.12)
        val paceFactor = (1.0 + ((oppPace - 99.0) / 99.0) * 0.45).coerceIn(0.92, 1.10)

        val statTypes = listOf(
            Triple("PTS", "Sayı", { g: PlayerGameLog -> g.pts }),
            Triple("REB", "Ribaund", { g: PlayerGameLog -> g.reb }),
            Triple("AST", "Asist", { g: PlayerGameLog -> g.ast }),
            Triple("3PM", "3 Sayılık Basket", { g: PlayerGameLog -> g.fg3m }),
            Triple("PRA", "Sayı+Rib+Ast", { g: PlayerGameLog -> g.pra }),
            Triple("P+R", "Sayı+Ribaund", { g: PlayerGameLog -> g.pr }),
            Triple("P+A", "Sayı+Asist", { g: PlayerGameLog -> g.pa }),
            Triple("STL", "Top Çalma", { g: PlayerGameLog -> g.stl }),
            Triple("BLK", "Blok", { g: PlayerGameLog -> g.blk })
        )

        val predictions = statTypes.map { (key, label, extractor) ->
            projectStat(
                statKey = key,
                displayName = label,
                extractor = extractor,
                history = history,
                player = player,
                isHome = isHome,
                restDays = restDays,
                fatigueFactor = fatigueFactor,
                blowoutModifier = blowoutModifier,
                usageBoost = usageBoost,
                defFactor = defFactor,
                paceFactor = paceFactor,
                oppStats = opponentStats
            )
        }

        return PredictionResult(
            player = player,
            opponentAbbr = opponentStats?.teamAbbr ?: "OPP",
            isHome = isHome,
            restDays = restDays,
            travelFatigueFactor = fatigueFactor,
            blowoutRisk = blowoutRisk,
            blowoutModifier = blowoutModifier,
            predictions = predictions
        )
    }

    private fun projectStat(
        statKey: String,
        displayName: String,
        extractor: (PlayerGameLog) -> Double,
        history: List<PlayerGameLog>,
        player: NbaPlayer,
        isHome: Boolean,
        restDays: Int,
        fatigueFactor: Double,
        blowoutModifier: Double,
        usageBoost: Double,
        defFactor: Double,
        paceFactor: Double,
        oppStats: TeamStats?
    ): StatPrediction {
        val values = history.map(extractor)
        val seasonAvg = values.average()
        val l5Values = values.take(5)
        val l3Values = values.take(3)
        val l5Avg = if (l5Values.isNotEmpty()) l5Values.average() else seasonAvg
        val l3Avg = if (l3Values.isNotEmpty()) l3Values.average() else seasonAvg

        // 1. Exponential Weighted Moving Average (EWMA)
        var projection = (l3Avg * 0.45) + (l5Avg * 0.35) + (seasonAvg * 0.20)

        // 2. Home vs Away Adjustment
        val homeSplits = history.filter { it.matchup.contains("vs.") }.map(extractor)
        val awaySplits = history.filter { it.matchup.contains("@") }.map(extractor)
        if (isHome && homeSplits.isNotEmpty() && seasonAvg > 0) {
            val homeRatio = (homeSplits.average() / seasonAvg).coerceIn(0.92, 1.12)
            projection *= homeRatio
        } else if (!isHome && awaySplits.isNotEmpty() && seasonAvg > 0) {
            val awayRatio = (awaySplits.average() / seasonAvg).coerceIn(0.88, 1.08)
            projection *= awayRatio
        }

        // 3. Rest Days Adjustment
        if (restDays <= 1) {
            projection *= 0.94 // B2B fatigue
        } else if (restDays >= 3) {
            projection *= 1.025 // Fresh legs
        }

        // 4. Modifiers
        projection *= fatigueFactor
        projection *= blowoutModifier
        projection *= usageBoost

        // 5. Opponent Defensive Matchup by Position (DvP)
        val isGuard = player.position.contains("G", ignoreCase = true)
        val isCenter = player.position.contains("C", ignoreCase = true)

        var statDefFactor = defFactor
        if (statKey == "REB" && isCenter && oppStats != null) {
            val rebRatio = (oppStats.oppReb / 43.5).coerceIn(0.88, 1.15)
            statDefFactor = rebRatio
        } else if (statKey == "3PM" && isGuard) {
            statDefFactor = (defFactor * 1.05).coerceIn(0.88, 1.15)
        }
        projection *= statDefFactor
        projection *= paceFactor

        // Floor validation
        val floorVal = FLOORS[statKey] ?: 0.5
        projection = projection.coerceAtLeast(floorVal)

        // Trend calculation
        val pctDiff = if (seasonAvg > 0) ((l5Avg - seasonAvg) / seasonAvg) * 100.0 else 0.0
        val trendType = when {
            pctDiff >= 20.0 -> TrendType.HOT
            pctDiff >= 10.0 -> TrendType.WARM
            pctDiff <= -20.0 -> TrendType.COLD
            pctDiff <= -10.0 -> TrendType.COOLING
            else -> TrendType.NEUTRAL
        }

        // Confidence calculation (consistency / variance)
        val variance = values.map { (it - seasonAvg) * (it - seasonAvg) }.average()
        val stdDev = sqrt(variance)
        val cv = if (seasonAvg > 0) stdDev / seasonAvg else 1.0
        // Probability thresholds (Over / Under distribution)
        val thresholds = ProbabilityEngine.getProbableThresholds(
            statKey = statKey,
            projection = (projection * 10.0).roundToInt() / 10.0,
            stdDev = if (stdDev > 0) stdDev else 2.0
        )

        return StatPrediction(
            statKey = statKey,
            displayName = displayName,
            predictedValue = (projection * 10.0).roundToInt() / 10.0,
            seasonAvg = (seasonAvg * 10.0).roundToInt() / 10.0,
            l5Avg = (l5Avg * 10.0).roundToInt() / 10.0,
            l3Avg = (l3Avg * 10.0).roundToInt() / 10.0,
            diffFromSeason = ((projection - seasonAvg) * 10.0).roundToInt() / 10.0,
            trend = Trend(trendType, (pctDiff * 10.0).roundToInt() / 10.0),
            confidence = confidenceScore,
            thresholds = thresholds
        )
    }
}
