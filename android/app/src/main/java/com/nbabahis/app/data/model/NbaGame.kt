package com.nbabahis.app.data.model

import com.google.gson.annotations.SerializedName

data class NbaGame(
    @SerializedName("gameId")
    val gameId: String,
    @SerializedName("homeTeamId")
    val homeTeamId: Int,
    @SerializedName("awayTeamId")
    val awayTeamId: Int,
    @SerializedName("homeTeamAbbr")
    val homeTeamAbbr: String,
    @SerializedName("awayTeamAbbr")
    val awayTeamAbbr: String,
    @SerializedName("homeTeamName")
    val homeTeamName: String = "",
    @SerializedName("awayTeamName")
    val awayTeamName: String = "",
    @SerializedName("gameDate")
    val gameDate: String,
    @SerializedName("gameStatus")
    val gameStatus: String = "Scheduled",
    @SerializedName("gameTime")
    val gameTime: String = ""
)
