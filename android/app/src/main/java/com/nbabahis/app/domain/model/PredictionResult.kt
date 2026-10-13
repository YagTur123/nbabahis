package com.nbabahis.app.domain.model

import com.nbabahis.app.data.model.NbaPlayer

data class PredictionResult(
    val player: NbaPlayer,
    val opponentAbbr: String,
    val isHome: Boolean,
    val restDays: Int,
    val travelFatigueFactor: Double, // örn: 0.94
    val blowoutRisk: Boolean,
    val blowoutModifier: Double,
    val predictions: List<StatPrediction>
)
