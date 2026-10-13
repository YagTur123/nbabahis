package com.nbabahis.app.domain.engine

import com.nbabahis.app.data.model.NbaPlayer

object UsageShiftCalculator {

    /**
     * Calculates usage boost multiplier when key teammates are injured/out.
     */
    fun calculateUsageMultiplier(
        player: NbaPlayer,
        teamRoster: List<NbaPlayer>
    ): Double {
        val injuredTeammates = teamRoster.filter {
            it.playerId != player.playerId &&
            (it.injuryStatus?.contains("OUT", ignoreCase = true) == true ||
             it.injuryStatus?.contains("DOUBT", ignoreCase = true) == true)
        }

        if (injuredTeammates.isEmpty()) return 1.0

        val isGuard = player.position.contains("G", ignoreCase = true)
        val isForward = player.position.contains("F", ignoreCase = true)
        val isCenter = player.position.contains("C", ignoreCase = true)

        var boost = 1.0

        for (injured in injuredTeammates) {
            val injuredPos = injured.position
            val injIsGuard = injuredPos.contains("G", ignoreCase = true)
            val injIsForward = injuredPos.contains("F", ignoreCase = true)
            val injIsCenter = injuredPos.contains("C", ignoreCase = true)

            // When a player of same or adjacent position is out, usage shifts heavily
            if (isGuard && injIsGuard) {
                boost += 0.06 // 6% usage boost for remaining guards
            } else if (isForward && injIsForward) {
                boost += 0.05 // 5% boost for remaining forwards
            } else if (isCenter && injIsCenter) {
                boost += 0.08 // Backup centers get substantial minutes boost
            } else {
                boost += 0.02 // General redistribution of shot volume
            }
        }

        // Cap at 1.25 (maximum 25% boost)
        return boost.coerceAtMost(1.25)
    }
}
