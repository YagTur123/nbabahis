package com.nbabahis.app.data.api

import okhttp3.Interceptor
import okhttp3.Response

class NbaHeadersInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request().newBuilder()
            .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            .header("Accept", "application/json, text/plain, */*")
            .header("Accept-Language", "en-US,en;q=0.9")
            .header("Referer", "https://www.nba.com/")
            .header("Origin", "https://www.nba.com")
            .header("x-nba-stats-origin", "stats")
            .header("x-nba-stats-token", "true")
            .header("Connection", "keep-alive")
            .build()
        return chain.proceed(request)
    }
}
