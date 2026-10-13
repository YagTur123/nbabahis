package com.nbabahis.app.domain.model

import com.nbabahis.app.data.model.NbaPlayer

data class PredictionResult(
    val player: NbaPlayer,
    val opponentAbbr: String,
    val isHome: Boolean,
    val restDays: Int,
    val travelFatigueFactor: Double,
    val blowoutRisk: Boolean,
    val blowoutModifier: Double,
    val stakesReport: String = "",
    val tacticalReport: String = "",
    val fatigueReport: String = "",
    val defenderReport: String = "",
    val predictions: List<StatPrediction>
)
