package com.nbabahis.app.domain.engine

import com.nbabahis.app.data.model.NbaPlayer
import com.nbabahis.app.data.model.TeamStats

enum class DefensiveScheme(val label: String) {
    DROP_COVERAGE("Drop Coverage (Derin Çember Koruması)"),
    SWITCH_ALL("Switch Defense (Sürekli El Değiştirme)"),
    BLITZ_TRAP("Blitz / Trap (Yıldıza İkili Sıkıştırma)"),
    BALANCED("Dengeli Şema")
}

data class TacticalModifiers(
    val paceMultiplier: Double, // Dynamic game possessions multiplier ~1.0
    val ptsModifier: Double,
    val rebModifier: Double,
    val astModifier: Double,
    val threesModifier: Double,
    val tovModifier: Double,
    val defensiveScheme: DefensiveScheme,
    val tacticalBreakdown: String
)

object MatchupTacticalEngine {

    fun calculateTacticalModifiers(
        player: NbaPlayer,
        teamStats: TeamStats?,
        oppStats: TeamStats?,
        isHome: Boolean
    ): TacticalModifiers {
        val defensiveScheme = determineDefensiveScheme(oppStats?.teamAbbr)
        val paceMultiplier = calculatePaceMultiplier(teamStats?.pace, oppStats?.pace)

        var ptsModifier = 1.0
        var rebModifier = 1.0
        var astModifier = 1.0
        var threesModifier = 1.0
        var tovModifier = 1.0

        val pos = player.position.uppercase()
        val isGuard = pos.contains("G")
        val isPlaymaker = pos.contains("PG") || (isGuard && !pos.contains("SG"))

        when (defensiveScheme) {
            DefensiveScheme.DROP_COVERAGE -> {
                if (isGuard) {
                    threesModifier *= 1.12 // Guard'lar drop savunan pivota karşı rahat 3'lük bulur
                    ptsModifier *= 1.05
                } else if (pos.contains("C")) {
                    rebModifier *= 0.92 // Çember altında kalabalık ribaund mücadelesi
                }
            }

            DefensiveScheme.SWITCH_ALL -> {
                if (isPlaymaker) {
                    astModifier *= 0.90 // Pas kanalları kapalı, pas akışı düşer
                    ptsModifier *= 1.04 // Birebir izolasyon ve serbest atış artar
                }
            }

            DefensiveScheme.BLITZ_TRAP -> {
                if (isPlaymaker) {
                    astModifier *= 1.14 // İkili sıkıştırmadan boş adama pas (asist patlaması)
                    tovModifier *= 1.20 // Top kaybı riski artar
                    ptsModifier *= 0.94 // Şut hacmi kısıtlanır
                }
            }

            DefensiveScheme.BALANCED -> {
                // Standart şema
            }
        }

        val breakdown = buildTacticalBreakdown(player, defensiveScheme)

        return TacticalModifiers(
            paceMultiplier = paceMultiplier,
            ptsModifier = ptsModifier,
            rebModifier = rebModifier,
            astModifier = astModifier,
            threesModifier = threesModifier,
            tovModifier = tovModifier,
            defensiveScheme = defensiveScheme,
            tacticalBreakdown = breakdown
        )
    }

    private fun determineDefensiveScheme(teamAbbr: String?): DefensiveScheme {
        return when (teamAbbr?.uppercase()) {
            "MIL", "MIN", "DEN", "UTA", "POR" -> DefensiveScheme.DROP_COVERAGE
            "BOS", "OKC", "GSW" -> DefensiveScheme.SWITCH_ALL
            "MIA", "NYK", "PHI" -> DefensiveScheme.BLITZ_TRAP
            else -> DefensiveScheme.BALANCED
        }
    }

    private fun calculatePaceMultiplier(teamPace: Double?, oppPace: Double?): Double {
        val tPace = teamPace ?: 99.0
        val oPace = oppPace ?: 99.0
        // Lig ortalaması 99.0 tempo baz alınarak dinamik katsayı
        val expectedPossessions = (tPace * oPace) / 99.0
        return (expectedPossessions / 99.0).coerceIn(0.92, 1.10)
    }

    private fun buildTacticalBreakdown(player: NbaPlayer, scheme: DefensiveScheme): String {
        return when (scheme) {
            DefensiveScheme.DROP_COVERAGE -> "${player.name} (${player.position}) derin çember korumasına karşı: Yüksek 3'lük şansı (+12%), zor boyalı alan bitirişi."
            DefensiveScheme.SWITCH_ALL -> "${player.name} (${player.position}) el değiştiren savunmaya karşı: Düşük asist akışı (-10%), yüksek izolasyon faul alma."
            DefensiveScheme.BLITZ_TRAP -> "${player.name} (${player.position}) ikili sıkıştırma baskısında: Artan asist potansiyeli (+14%), artan top kaybı riski (+20%)."
            DefensiveScheme.BALANCED -> "${player.name} dengeli şemada."
        }
    }
}
