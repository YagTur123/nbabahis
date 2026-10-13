package com.nbabahis.app.data.model

data class TeamStats(
    val teamAbbr: String,
    val defRating: Double = 114.0, // League average ~114
    val pace: Double = 99.0,       // League average ~99
    val rebPct: Double = 0.50,     // League average 50%
    val avgMargin: Double = 0.0,
    val oppPts: Double = 114.0,
    val oppReb: Double = 43.5,
    val oppAst: Double = 26.5
)
