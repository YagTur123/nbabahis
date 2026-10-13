package com.nbabahis.app.data.model

import com.google.gson.annotations.SerializedName

data class PlayerGameLog(
    @SerializedName("gameId")
    val gameId: String = "",
    @SerializedName("gameDate")
    val gameDate: String = "",
    @SerializedName("matchup")
    val matchup: String = "",
    @SerializedName("min")
    val min: Double = 0.0,
    @SerializedName("pts")
    val pts: Double = 0.0,
    @SerializedName("reb")
    val reb: Double = 0.0,
    @SerializedName("ast")
    val ast: Double = 0.0,
    @SerializedName("stl")
    val stl: Double = 0.0,
    @SerializedName("blk")
    val blk: Double = 0.0,
    @SerializedName("tov")
    val tov: Double = 0.0,
    @SerializedName("pf")
    val pf: Double = 0.0,
    @SerializedName("fg3m")
    val fg3m: Double = 0.0,
    @SerializedName("fg3a")
    val fg3a: Double = 0.0,
    @SerializedName("fgm")
    val fgm: Double = 0.0,
    @SerializedName("fga")
    val fga: Double = 0.0,
    @SerializedName("ftm")
    val ftm: Double = 0.0,
    @SerializedName("fta")
    val fta: Double = 0.0,
    @SerializedName("plusMinus")
    val plusMinus: Double = 0.0
) {
    val pra: Double get() = pts + reb + ast
    val pr: Double get() = pts + reb
    val pa: Double get() = pts + ast
    val ar: Double get() = ast + reb
    val sb: Double get() = stl + blk
}
