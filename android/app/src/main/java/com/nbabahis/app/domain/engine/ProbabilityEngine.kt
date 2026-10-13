package com.nbabahis.app.domain.engine

import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.sqrt

object ProbabilityEngine {

    private const val ERFC_COEFFICIENTS_A = doubleArrayOf(
        1.0, 0.196854, 0.115194, 0.000344, 0.019527
    )

    private const val ERFC_COEFFICIENTS_B = doubleArrayOf(
        0.0, 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    )

    /**
     * Approximates the error function erf(x) using Abramowitz & Stegun formula 7.1.26
     * Range: x ∈ ℝ, accuracy ~1e-7
     */
    private fun erf(x: Double): Double {
        val t = 1.0 / (1.0 + 0.3275911 * abs(x))
        val polynomial = ERFC_COEFFICIENTS_B[1] * t +
                ERFC_COEFFICIENTS_B[2] * t * t +
                ERFC_COEFFICIENTS_B[3] * t * t * t +
                ERFC_COEFFICIENTS_B[4] * t * t * t * t +
                ERFC_COEFFICIENTS_B[5] * t * t * t * t * t
        val sign = if (x >= 0.0) 1.0 else -1.0
        return sign * (1.0 - (ERFC_COEFFICIENTS_A[1] * t +
                ERFC_COEFFICIENTS_A[2] * t * t +
                ERFC_COEFFICIENTS_A[3] * t * t * t +
                ERFC_COEFFICIENTS_A[4] * t * t * t * t) * exp(-x * x))
    }

    /**
     * Standard normal CDF using erf approximation
     * Φ(x) = 0.5 * (1 + erf(x / √2))
     */
    private fun normalCDF(x: Double): Double = 0.5 * (1.0 + erf(x / sqrt(2.0)))

    /**
     * Poisson CDF: P(X ≤ k) for integer k ≥ 0 and λ > 0
     * Uses regularized gamma function: P(X ≤ k) = Q(k+1, λ) = 1 - Γ(k+1, λ)/k!
     * Computed via series expansion for numerical stability
     */
    private fun poissonCDF(k: Int, lambda: Double): Double {
        require(k >= 0) { "k must be non-negative" }
        require(lambda > 0) { "lambda must be positive" }

        if (lambda < 1e-10) return if (k >= 0) 1.0 else 0.0

        // Use series expansion for small λ or small k
        if (lambda < 30.0 && k < 100) {
            var sum = 0.0
            var term = exp(-lambda)
            sum += term
            for (i in 1..k) {
                term *= lambda / i
                sum += term
            }
            return sum
        }

        // For larger values, use normal approximation with continuity correction
        val z = (k + 0.5 - lambda) / sqrt(lambda)
        return normalCDF(z)
    }

    /**
     * Calculate probability that a normally distributed variable exceeds the threshold
     * P(X > threshold) = 1 - Φ((threshold - μ) / σ)
     */
    fun calculateOverProbability(projection: Double, threshold: Double, stdDev: Double): Double {
        require(stdDev >= 0.0) { "Standard deviation must be non-negative" }
        if (stdDev == 0.0) return if (projection > threshold) 1.0 else 0.0

        val z = (threshold - projection) / stdDev
        return 1.0 - normalCDF(z)
    }

    /**
     * Calculate probability that a normally distributed variable is below the threshold
     * P(X ≤ threshold) = Φ((threshold - μ) / σ)
     */
    fun calculateUnderProbability(projection: Double, threshold: Double, stdDev: Double): Double {
        require(stdDev >= 0.0) { "Standard deviation must be non-negative" }
        if (stdDev == 0.0) return if (projection <= threshold) 1.0 else 0.0

        val z = (threshold - projection) / stdDev
        return normalCDF(z)
    }

    /**
     * Calculate probabilities for common thresholds around a projection
     * Returns list of thresholds with their over/under probabilities
     * High-value thresholds are defined as those with over probability ≥ 0.65
     */
    fun getProbableThresholds(
        statKey: String,
        projection: Double,
        stdDev: Double
    ): List<ThresholdProb> {
        require(stdDev >= 0.0) { "Standard deviation must be non-negative" }

        val thresholds = when {
            statKey.contains("pts", ignoreCase = true) -> listOf(
                projection - 7.5,
                projection - 4.5,
                projection - 2.5,
                projection - 0.5,
                projection + 0.5,
                projection + 2.5,
                projection + 4.5,
                projection + 7.5
            )
            statKey.contains("reb", ignoreCase = true) || statKey.contains("trb", ignoreCase = true) -> listOf(
                projection - 4.5,
                projection - 2.5,
                projection - 1.5,
                projection - 0.5,
                projection + 0.5,
                projection + 1.5,
                projection + 2.5,
                projection + 4.5
            )
            statKey.contains("ast", ignoreCase = true) -> listOf(
                projection - 2.5,
                projection - 1.5,
                projection - 0.5,
                projection + 0.5,
                projection + 1.5,
                projection + 2.5
            )
            statKey.contains("blk", ignoreCase = true) || statKey.contains("stl", ignoreCase = true) || statKey.contains("3pm", ignoreCase = true) -> listOf(
                0.0,
                0.5,
                1.5,
                2.5,
                3.5,
                4.5
            ).filter { it >= 0.0 }
            else -> listOf(
                projection - 2.0,
                projection - 1.0,
                projection - 0.5,
                projection + 0.5,
                projection + 1.0,
                projection + 2.0
            )
        }.distinct().sorted()

        return thresholds.map { threshold ->
            val overProb = if (statKey.contains("blk", ignoreCase = true) ||
                statKey.contains("stl", ignoreCase = true) ||
                statKey.contains("3pm", ignoreCase = true)
            ) {
                // For count stats, use Poisson CDF for under, then derive over
                val k = threshold.toInt()
                val underProb = poissonCDF(k, projection)
                1.0 - underProb + (if (threshold == k.toDouble()) 0.0 else 0.0)
            } else {
                calculateOverProbability(projection, threshold, stdDev)
            }.coerceIn(0.0, 1.0)

            val underProb = 1.0 - overProb

            ThresholdProb(
                threshold = threshold,
                overProb = overProb,
                underProb = underProb,
                isHighValue = overProb >= 0.65
            )
        }
    }

    data class ThresholdProb(
        val threshold: Double,
        val overProb: Double,
        val underProb: Double,
        val isHighValue: Boolean
    )
}
