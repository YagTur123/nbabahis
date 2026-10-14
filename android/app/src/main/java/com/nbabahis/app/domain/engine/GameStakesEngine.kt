package com.nbabahis.app.domain.engine

import com.nbabahis.app.data.model.NbaPlayer
import com.nbabahis.app.data.model.TeamStats
import kotlin.math.abs

enum class GameImportanceTier(val label: String, val minutesMultiplier: Double) {
    PLAYOFF_LEVERAGE_HIGH("Playoff/Play-in Yarışı", 1.08),
    NORMAL_REGULAR_SEASON("Normal Sezon", 1.00),
    TANKING_OR_REST_RISK("Tanking / Dinlendirme Riski", 0.85),
    SECURED_PLAYOFF_SEED("Sıralama Garantilendi", 0.92)
}

data class GameStakesContext(
    val isRivalryOrConferenceGame: Boolean,
    val isNationalTv: Boolean,
    val teamWinPct: Double,
    val opponentWinPct: Double,
    val gamesRemainingInSeason: Int = 15,
    val isReturningFromInjury: Boolean = false
)

data class StakesImpact(
    val importanceTier: GameImportanceTier,
    val projectedMinutesModifier: Double,
    val scoringIntensityModifier: Double,
    val defensiveIntensityModifier: Double,
    val explanation: String
)

object GameStakesEngine {

    fun evaluateGameStakes(
        player: NbaPlayer,
        teamStats: TeamStats?,
        oppStats: TeamStats?,
        context: GameStakesContext
    ): StakesImpact {
        val teamWinDiff = context.teamWinPct - context.opponentWinPct
        val isPlayoffRace = context.gamesRemainingInSeason <= 15 && abs(teamWinDiff) <= 0.12
        val isHighStakes = isPlayoffRace || context.isRivalryOrConferenceGame
        val isLowStakes = context.gamesRemainingInSeason <= 10 && context.teamWinPct < 0.32

        val (importanceTier, baseMinutesMultiplier) = when {
            isHighStakes && context.isNationalTv -> GameImportanceTier.PLAYOFF_LEVERAGE_HIGH to 1.08
            isHighStakes -> GameImportanceTier.PLAYOFF_LEVERAGE_HIGH to 1.06
            isLowStakes -> GameImportanceTier.TANKING_OR_REST_RISK to 0.85
            context.teamWinPct >= 0.72 && context.gamesRemainingInSeason <= 6 -> GameImportanceTier.SECURED_PLAYOFF_SEED to 0.92
            else -> GameImportanceTier.NORMAL_REGULAR_SEASON to 1.00
        }

        var minutesModifier = baseMinutesMultiplier
        var scoringIntensityModifier = 1.0
        var defensiveIntensityModifier = 1.0
        val explanations = mutableListOf<String>()

        // 1. National TV boost (Stars perform better under spotlight)
        if (context.isNationalTv) {
            scoringIntensityModifier *= 1.04
            defensiveIntensityModifier *= 1.03
            explanations.add("Ulusal Yayın (Prime-Time): +4% sayı motivasyonu")
        }

        // 2. Rivalry / Conference game (Harder defense, slower pace)
        if (context.isRivalryOrConferenceGame) {
            defensiveIntensityModifier *= 1.06
            scoringIntensityModifier *= 0.98
            explanations.add("Konferans/Ezeli Rekabet: +6% savunma sertliği")
        }

        // 3. Minutes restriction on injury return
        if (context.isReturningFromInjury || player.injuryStatus?.contains("GTD", ignoreCase = true) == true) {
            minutesModifier *= 0.85
            scoringIntensityModifier *= 0.92
            explanations.add("Sakatlık/GTD dönüşü: Dakika kısıtlaması (-15%)")
        }

        // 4. Opponent defensive profile impact
        if (oppStats != null) {
            if (oppStats.defRating < 111.0) {
                scoringIntensityModifier *= 0.95
                explanations.add("Elit savunma rakip (DefRtg < 111): -5% skor hacmi")
            } else if (oppStats.defRating > 117.0) {
                scoringIntensityModifier *= 1.05
                explanations.add("Zayıf savunma rakip (DefRtg > 117): +5% skor hacmi")
            }
        }

        val explanation = buildString {
            append("Önem: ${importanceTier.label}")
            if (explanations.isNotEmpty()) {
                append(" · ")
                append(explanations.joinToString(" · "))
            }
        }

        return StakesImpact(
            importanceTier = importanceTier,
            projectedMinutesModifier = minutesModifier,
            scoringIntensityModifier = scoringIntensityModifier,
            defensiveIntensityModifier = defensiveIntensityModifier,
            explanation = explanation
        )
    }
}
