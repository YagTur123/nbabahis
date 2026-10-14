package com.nbabahis.app.domain.engine

import com.nbabahis.app.data.model.NbaPlayer
import com.nbabahis.app.domain.model.PredictionResult
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

data class HalftimeBoxScore(
    val h1Pts: Double,
    val h1Reb: Double,
    val h1Ast: Double,
    val h1Threes: Double,
    val h1Min: Double,
    val fouls: Int,
    val marginAtHalf: Double // Ev sahibi - misafir farkı
)

data class LiveStatProjection(
    val statKey: String,
    val displayName: String,
    val h1Actual: Double,
    val h2Projected: Double,
    val totalProjected: Double,
    val pregameProjected: Double,
    val diffFromPregame: Double
)

data class LiveProjectionResult(
    val player: NbaPlayer,
    val originalPreGame: PredictionResult,
    val liveStats: List<LiveStatProjection>,
    val h2ProjectedMinutes: Double,
    val foulRiskNote: String?,
    val blowoutRiskNote: String?,
    val liveSummaryNote: String
)

object HalftimeLiveEngine {

    fun calculateLiveProjection(
        player: NbaPlayer,
        pregame: PredictionResult,
        h1: HalftimeBoxScore
    ): LiveProjectionResult {
        // Standart maç 48 dakika; ilk yarı 24 dakikadır.
        val h1MinutesPlayed = h1.h1Min.coerceIn(0.0, 24.0)
        var h2ProjectedMinutes = (h1MinutesPlayed * 1.02).coerceIn(0.0, 24.0)

        // 1. Faul Problemi Riski (Foul Trouble)
        var foulRiskNote: String? = null
        if (h1.fouls >= 3) {
            val penalty = if (h1.fouls >= 4) 0.35 else 0.20
            h2ProjectedMinutes *= (1.0 - penalty)
            val penaltyPct = (penalty * 100).toInt()
            foulRiskNote = "⚠️ Erken Faul Problemi (${h1.fouls} Faul): 2. yarı süre kısıtlaması (-%$penaltyPct dakika)"
        }

        // 2. Erken Blowout / Fark Açılma Riski (Bench dinlendirme)
        var blowoutRiskNote: String? = null
        val halfMargin = abs(h1.marginAtHalf)
        if (halfMargin >= 18.0) {
            h2ProjectedMinutes *= 0.82
            blowoutRiskNote = "⚠️ İlk Yarı Farkı (${halfMargin.toInt()} Sayı): 4. çeyrek dinlenme riski (-%18 süre)"
        }

        h2ProjectedMinutes = (h2ProjectedMinutes * 10.0).roundToInt() / 10.0

        // 3. İstatistik Bazında Ortalamaya Yakınsama (Regression to Mean) & 2. Yarı Projeksiyonu
        val liveStats = pregame.predictions.map { statPred ->
            val statKey = statPred.statKey
            val pregameVal = statPred.predictedValue
            val expectedH1 = pregameVal * 0.50

            val h1Actual = when (statKey) {
                "PTS" -> h1.h1Pts
                "REB" -> h1.h1Reb
                "AST" -> h1.h1Ast
                "3PM" -> h1.h1Threes
                "PRA" -> h1.h1Pts + h1.h1Reb + h1.h1Ast
                "P+R" -> h1.h1Pts + h1.h1Reb
                "P+A" -> h1.h1Pts + h1.h1Ast
                else -> expectedH1
            }

            // Eğer oyuncu ilk yarı beklentisinin %40 üstünde oynadıysa şut yüzdesi normalize olur
            val isOverperforming = expectedH1 > 0 && h1Actual > (expectedH1 * 1.40)
            val regressionFactor = if (isOverperforming) {
                val excess = (h1Actual - expectedH1) / expectedH1
                (1.0 - min(0.20, excess * 0.15)).coerceIn(0.80, 1.0)
            } else {
                1.0
            }

            // 2. Yarı tahmini = (Maç öncesi 2. yarı oranı) * (dakika oranı) * (regresyon faktörü)
            val minutesRatio = if (h1MinutesPlayed > 0) h2ProjectedMinutes / h1MinutesPlayed else 1.0
            val h2Projected = ((expectedH1 * minutesRatio * regressionFactor) * 10.0).roundToInt() / 10.0
            val totalLive = ((h1Actual + h2Projected) * 10.0).roundToInt() / 10.0
            val diff = ((totalLive - pregameVal) * 10.0).roundToInt() / 10.0

            LiveStatProjection(
                statKey = statKey,
                displayName = statPred.displayName,
                h1Actual = (h1Actual * 10.0).roundToInt() / 10.0,
                h2Projected = h2Projected,
                totalProjected = totalLive,
                pregameProjected = pregameVal,
                diffFromPregame = diff
            )
        }

        val summaryNote = buildString {
            append("Canlı Devre Arası Projeksiyonu: 2. Yarı Beklenen Süre: ${h2ProjectedMinutes} dk")
            if (foulRiskNote != null) append(" · $foulRiskNote")
            if (blowoutRiskNote != null) append(" · $blowoutRiskNote")
        }

        return LiveProjectionResult(
            player = player,
            originalPreGame = pregame,
            liveStats = liveStats,
            h2ProjectedMinutes = h2ProjectedMinutes,
            foulRiskNote = foulRiskNote,
            blowoutRiskNote = blowoutRiskNote,
            liveSummaryNote = summaryNote
        )
    }
}
