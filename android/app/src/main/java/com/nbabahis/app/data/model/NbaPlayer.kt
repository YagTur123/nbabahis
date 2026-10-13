package com.nbabahis.app.data.model

import com.google.gson.annotations.SerializedName

data class NbaPlayer(
    @SerializedName("playerId")
    val playerId: Int,
    @SerializedName("name")
    val name: String,
    @SerializedName("teamAbbr")
    val teamAbbr: String,
    @SerializedName("position")
    val position: String, // "G", "F", "C", "G-F", etc.
    @SerializedName("jerseyNum")
    val jerseyNum: String = "",
    @SerializedName("injuryStatus")
    val injuryStatus: String? = null // "OUT", "QUESTIONABLE", "PROBABLE"
)
