package com.nbabahis.app.domain.engine

import com.nbabahis.app.data.model.NbaPlayer

enum class DefenderTier(val label: String, val badge: String) {
    ELITE_LOCKDOWN("Elit Kilit Savunmacı", "🔒"),
    ABOVE_AVERAGE("Sert Savunmacı", "🛡️"),
    NEUTRAL("Standart Savunmacı", "➖"),
    DEFENSIVE_LIABILITY("Zayıf Savunma Hedefi", "🎯")
}

data class DefenderProfile(
    val name: String,
    val teamAbbr: String,
    val position: String,
    val tier: DefenderTier,
    val dfgDiffPct: Double, // e.g. -5.2% means opponents shoot 5.2% worse against them
    val stealRate: Double,
    val blockRate: Double
)

data class DefenderMatchupImpact(
    val primaryDefender: DefenderProfile,
    val ptsModifier: Double,
    val fg3mModifier: Double,
    val tovModifier: Double,
    val matchupSummary: String
)

object PrimaryDefenderEngine {

    private val knownDefenderProfiles = mapOf(
        // Elite perimeter lockdowns
        "Jrue Holiday" to DefenderProfile("Jrue Holiday", "BOS", "G", DefenderTier.ELITE_LOCKDOWN, -6.1, 2.2, 0.4),
        "Derrick White" to DefenderProfile("Derrick White", "BOS", "G", DefenderTier.ELITE_LOCKDOWN, -5.8, 1.9, 0.5),
        "Alex Caruso" to DefenderProfile("Alex Caruso", "OKC", "G", DefenderTier.ELITE_LOCKDOWN, -5.3, 2.4, 0.6),
        "Lu Dort" to DefenderProfile("Lu Dort", "OKC", "G", DefenderTier.ELITE_LOCKDOWN, -5.6, 2.1, 0.3),
        "Herb Jones" to DefenderProfile("Herb Jones", "NOP", "F", DefenderTier.ELITE_LOCKDOWN, -5.4, 1.8, 1.1),
        "Jaden McDaniels" to DefenderProfile("Jaden McDaniels", "MIN", "F", DefenderTier.ELITE_LOCKDOWN, -5.2, 1.3, 0.9),
        "OG Anunoby" to DefenderProfile("OG Anunoby", "NYK", "F", DefenderTier.ELITE_LOCKDOWN, -5.5, 1.7, 0.7),
        "Marcus Smart" to DefenderProfile("Marcus Smart", "MEM", "G", DefenderTier.ELITE_LOCKDOWN, -5.0, 1.6, 0.3),
        "Dillon Brooks" to DefenderProfile("Dillon Brooks", "HOU", "F", DefenderTier.ELITE_LOCKDOWN, -5.1, 1.5, 0.4),

        // Elite interior anchors
        "Rudy Gobert" to DefenderProfile("Rudy Gobert", "MIN", "C", DefenderTier.ELITE_LOCKDOWN, -7.2, 0.3, 2.5),
        "Anthony Davis" to DefenderProfile("Anthony Davis", "LAL", "C", DefenderTier.ELITE_LOCKDOWN, -6.8, 0.5, 2.3),
        "Victor Wembanyama" to DefenderProfile("Victor Wembanyama", "SAS", "C", DefenderTier.ELITE_LOCKDOWN, -6.5, 0.4, 2.8),
        "Bam Adebayo" to DefenderProfile("Bam Adebayo", "MIA", "C", DefenderTier.ELITE_LOCKDOWN, -6.3, 1.1, 1.4),
        "Chet Holmgren" to DefenderProfile("Chet Holmgren", "OKC", "C", DefenderTier.ELITE_LOCKDOWN, -6.0, 0.3, 2.4),
        "Jarrett Allen" to DefenderProfile("Jarrett Allen", "CLE", "C", DefenderTier.ELITE_LOCKDOWN, -6.1, 0.2, 2.1),
        "Brook Lopez" to DefenderProfile("Brook Lopez", "MIL", "C", DefenderTier.ELITE_LOCKDOWN, -5.9, 0.2, 2.0),

        // Defensive liabilities / targets
        "Trae Young" to DefenderProfile("Trae Young", "ATL", "G", DefenderTier.DEFENSIVE_LIABILITY, 4.2, 0.6, 0.1),
        "Tyrese Haliburton" to DefenderProfile("Tyrese Haliburton", "IND", "G", DefenderTier.DEFENSIVE_LIABILITY, 3.5, 0.8, 0.1),
        "Jordan Poole" to DefenderProfile("Jordan Poole", "WAS", "G", DefenderTier.DEFENSIVE_LIABILITY, 3.6, 0.5, 0.1),
        "Anfernee Simons" to DefenderProfile("Anfernee Simons", "POR", "G", DefenderTier.DEFENSIVE_LIABILITY, 3.4, 0.6, 0.1),
        "Tyler Herro" to DefenderProfile("Tyler Herro", "MIA", "G", DefenderTier.DEFENSIVE_LIABILITY, 3.7, 0.6, 0.1)
    )

    fun identifyPrimaryDefender(
        offensivePlayer: NbaPlayer,
        opponentRoster: List<NbaPlayer>,
        opponentAbbr: String
    ): DefenderProfile {
        val offPos = offensivePlayer.position.uppercase()
        val isGuard = offPos.contains("G")
        val isCenter = offPos.contains("C")

        // 1. Check if an elite defender exists on the opponent roster for this position
        for (opp in opponentRoster) {
            val profile = knownDefenderProfiles[opp.name]
            if (profile != null) {
                val defPos = opp.position.uppercase()
                val match = (isGuard && defPos.contains("G")) ||
                            (isCenter && defPos.contains("C")) ||
                            (!isGuard && !isCenter && defPos.contains("F"))
                if (match) {
                    return profile.copy(teamAbbr = opponentAbbr)
                }
            }
        }

        // 2. Check position-matched opponent
        val matchedOpponent = opponentRoster.firstOrNull { opp ->
            val defPos = opp.position.uppercase()
            (isGuard && defPos.contains("G")) ||
            (isCenter && defPos.contains("C")) ||
            (!isGuard && !isCenter && defPos.contains("F"))
        }

        if (matchedOpponent != null) {
            val known = knownDefenderProfiles[matchedOpponent.name]
            if (known != null) return known.copy(teamAbbr = opponentAbbr)

            return DefenderProfile(
                name = matchedOpponent.name,
                teamAbbr = opponentAbbr,
                position = matchedOpponent.position,
                tier = DefenderTier.NEUTRAL,
                dfgDiffPct = 0.0,
                stealRate = 1.0,
                blockRate = if (isCenter) 1.2 else 0.4
            )
        }

        // 3. Fallback generic positional defender
        return DefenderProfile(
            name = "$opponentAbbr Savunması",
            teamAbbr = opponentAbbr,
            position = offensivePlayer.position,
            tier = DefenderTier.NEUTRAL,
            dfgDiffPct = 0.0,
            stealRate = 1.0,
            blockRate = 0.5
        )
    }

    fun calculateMatchupImpact(
        offensivePlayer: NbaPlayer,
        opponentRoster: List<NbaPlayer>,
        opponentAbbr: String
    ): DefenderMatchupImpact {
        val primaryDefender = identifyPrimaryDefender(offensivePlayer, opponentRoster, opponentAbbr)
        val dfgDiff = primaryDefender.dfgDiffPct
        val stealRate = primaryDefender.stealRate
        val blockRate = primaryDefender.blockRate

        val ptsModifier = when (primaryDefender.tier) {
            DefenderTier.ELITE_LOCKDOWN -> 0.90 + (dfgDiff / 100.0) * 0.5 // e.g. -6% -> 0.87
            DefenderTier.ABOVE_AVERAGE -> 0.96 + (dfgDiff / 100.0) * 0.3
            DefenderTier.NEUTRAL -> 1.00
            DefenderTier.DEFENSIVE_LIABILITY -> 1.08 + (dfgDiff / 100.0) * 0.2 // e.g. +4% -> 1.088
        }.coerceIn(0.85, 1.15)

        val fg3mModifier = when (primaryDefender.tier) {
            DefenderTier.ELITE_LOCKDOWN -> 0.92 + (dfgDiff / 100.0) * 0.4
            DefenderTier.ABOVE_AVERAGE -> 0.96 + (dfgDiff / 100.0) * 0.2
            DefenderTier.NEUTRAL -> 1.00
            DefenderTier.DEFENSIVE_LIABILITY -> 1.06 + (dfgDiff / 100.0) * 0.1
        }.coerceIn(0.88, 1.14)

        val tovModifier = when {
            primaryDefender.tier == DefenderTier.ELITE_LOCKDOWN && stealRate >= 1.8 -> 1.12
            primaryDefender.tier == DefenderTier.ELITE_LOCKDOWN -> 1.06
            stealRate >= 1.5 -> 1.03
            else -> 1.00
        }.coerceIn(0.95, 1.18)

        val summary = buildString {
            append("${primaryDefender.tier.badge} ${primaryDefender.name} (${primaryDefender.teamAbbr}) ")
            when (primaryDefender.tier) {
                DefenderTier.ELITE_LOCKDOWN -> append("elit kilit savunmacı: Çember/perimetre şutlarında %${-dfgDiff} baskı.")
                DefenderTier.ABOVE_AVERAGE -> append("sert savunmacı: Orta düzey şut baskısı.")
                DefenderTier.NEUTRAL -> append("standart pozisyon savunucusu.")
                DefenderTier.DEFENSIVE_LIABILITY -> append("zayıf savunma hedefi: Şutörlere %${dfgDiff} daha açık pozisyon veriyor.")
            }
        }

        return DefenderMatchupImpact(
            primaryDefender = primaryDefender,
            ptsModifier = ptsModifier,
            fg3mModifier = fg3mModifier,
            tovModifier = tovModifier,
            matchupSummary = summary
        )
    }
}
