package com.nbabahis.app.domain.model

enum class TrendType(val label: String, val emoji: String) {
    HOT("Yükselişte", "🔥"),
    WARM("İyi Formda", "📈"),
    NEUTRAL("Normal", "➖"),
    COOLING("Düşüş Eğiliminde", "📉"),
    COLD("Formsuz", "❄️")
}

data class Trend(
    val type: TrendType,
    val pctDiff: Double
)
