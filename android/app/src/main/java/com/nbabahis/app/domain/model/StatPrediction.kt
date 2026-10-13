package com.nbabahis.app.domain.model

import com.nbabahis.app.domain.engine.ProbabilityEngine.ThresholdProb

data class StatPrediction(
    val statKey: String, // "PTS", "REB", "AST", "3PM", "PRA", "STL", "BLK"
    val displayName: String,
    val predictedValue: Double,
    val seasonAvg: Double,
    val l5Avg: Double,
    val l3Avg: Double,
    val diffFromSeason: Double, // predicted - seasonAvg
    val trend: Trend,
    val confidence: Int, // 0-100%
    val thresholds: List<ThresholdProb> = emptyList()
)
