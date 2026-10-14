package com.nbabahis.app.domain.engine

import com.nbabahis.app.data.model.PlayerGameLog
import com.nbabahis.app.domain.model.PredictionResult
import kotlin.math.abs
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sqrt

data class StatBacktestMetrics(
    val statKey: String,
    val sampleSize: Int,
    val mae: Double,
    val rmse: Double,
    val hitRatePct: Double,
    val modelBias: Double
)

data class BacktestReport(
    val evaluatedCount: Int,
    val overallHitRatePct: Double,
    val eliteSafeHitRatePct: Double = 0.0,
    val metricsByStat: Map<String, StatBacktestMetrics>,
    val accuracyGrade: String,
    val calibrationNotes: List<String>
)

object BacktestTrackerEngine {

    fun evaluateBacktest(
        pastPredictions: List<PredictionResult>,
        actualBoxScores: Map<Int, PlayerGameLog>
    ): BacktestReport {
        if (pastPredictions.isEmpty() || actualBoxScores.isEmpty()) {
            return BacktestReport(
                evaluatedCount = 0,
                overallHitRatePct = 0.0,
                metricsByStat = emptyMap(),
                accuracyGrade = "N/A",
                calibrationNotes = listOf("Doğrulama için yeterli maç verisi bulunamadı.")
            )
        }

        val validPredictions = pastPredictions.filter { pred ->
            actualBoxScores.containsKey(pred.player.playerId)
        }

        val statErrors = mutableMapOf<String, MutableList<Double>>()
        val statBiases = mutableMapOf<String, MutableList<Double>>()
        val statThresholdHits = mutableMapOf<String, MutableList<Boolean>>()
        val eliteHits = mutableListOf<Boolean>()

        validPredictions.forEach { prediction ->
            val actual = actualBoxScores[prediction.player.playerId] ?: return@forEach

            prediction.predictions.forEach { statPred ->
                val statKey = statPred.statKey
                val predictedValue = statPred.predictedValue

                val actualValue = when (statKey) {
                    "PTS" -> actual.pts
                    "REB" -> actual.reb
                    "AST" -> actual.ast
                    "3PM" -> actual.fg3m
                    "STL" -> actual.stl
                    "BLK" -> actual.blk
                    "PRA" -> actual.pra
                    "P+R" -> actual.pr
                    "P+A" -> actual.pa
                    else -> null
                } ?: return@forEach

                val error = predictedValue - actualValue
                statErrors.getOrPut(statKey) { mutableListOf() }.add(abs(error))
                statBiases.getOrPut(statKey) { mutableListOf() }.add(error)

                // High confidence threshold evaluation
                statPred.thresholds.filter { it.isHighValue }.forEach { t ->
                    val isHit = actualValue > t.threshold
                    statThresholdHits.getOrPut(statKey) { mutableListOf() }.add(isHit)
                }

                // %90+ Güvenli Alternatif Kasa Baremi kontrolü
                if (statPred.safeFloorLine != null && statPred.safeFloorProb >= 0.88) {
                    val isEliteHit = actualValue >= statPred.safeFloorLine
                    eliteHits.add(isEliteHit)
                }
            }
        }

        val metricsByStat = mutableMapOf<String, StatBacktestMetrics>()
        val allHits = mutableListOf<Boolean>()
        val calibrationNotes = mutableListOf<String>()

        statErrors.keys.forEach { statKey ->
            val errors = statErrors[statKey] ?: emptyList()
            val biases = statBiases[statKey] ?: emptyList()
            val hits = statThresholdHits[statKey] ?: emptyList()

            val sampleSize = errors.size
            if (sampleSize == 0) return@forEach

            val mae = round2(errors.average())
            val rmse = round2(sqrt(errors.map { it.pow(2) }.average()))
            val modelBias = round2(biases.average())

            val hitRatePct = if (hits.isNotEmpty()) {
                allHits.addAll(hits)
                round2((hits.count { it }.toDouble() / hits.size) * 100.0)
            } else {
                round2((errors.count { it <= 2.5 }.toDouble() / sampleSize) * 100.0)
            }

            metricsByStat[statKey] = StatBacktestMetrics(
                statKey = statKey,
                sampleSize = sampleSize,
                mae = mae,
                rmse = rmse,
                hitRatePct = hitRatePct,
                modelBias = modelBias
            )

            val biasDirection = if (modelBias > 0) "yüksek (+)" else "düşük (-)"
            if (abs(modelBias) > 0.8) {
                calibrationNotes.add("$statKey: Model ortalama ${abs(modelBias)} birim $biasDirection tahmin üretti.")
            }
        }

        val overallHitRate = if (allHits.isNotEmpty()) {
            round2((allHits.count { it }.toDouble() / allHits.size) * 100.0)
        } else if (metricsByStat.isNotEmpty()) {
            round2(metricsByStat.values.map { it.hitRatePct }.average())
        } else {
            0.0
        }

        val grade = when {
            overallHitRate >= 78.0 -> "A+"
            overallHitRate >= 72.0 -> "A"
            overallHitRate >= 66.0 -> "B+"
            overallHitRate >= 60.0 -> "B"
            else -> "C"
        }

        if (calibrationNotes.isEmpty()) {
            calibrationNotes.add("Tüm temel istatistiklerde model sapması dengeli ve optimum aralıkta.")
        }

        val eliteSafeHitRate = if (eliteHits.isNotEmpty()) {
            round2((eliteHits.count { it }.toDouble() / eliteHits.size) * 100.0)
        } else {
            0.0
        }

        return BacktestReport(
            evaluatedCount = validPredictions.size,
            overallHitRatePct = overallHitRate,
            eliteSafeHitRatePct = eliteSafeHitRate,
            metricsByStat = metricsByStat,
            accuracyGrade = grade,
            calibrationNotes = calibrationNotes
        )
    }

    private fun round2(v: Double): Double = (v * 100.0).roundToInt() / 100.0
}
