package com.abhi.startuplaw.data

import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import javax.net.ssl.HttpsURLConnection

/** Small HTTPS-only client: hard size caps, timeouts, and no plain-HTTP redirects. */
object Net {
    class TooLarge : IOException("response too large")

    private fun open(url: String, accept: String): HttpsURLConnection {
        require(url.startsWith("https://")) { "https only" }
        val c = URL(url).openConnection() as? HttpsURLConnection ?: throw IOException("not https")
        c.connectTimeout = 12_000
        c.readTimeout = 20_000
        c.instanceFollowRedirects = true // HttpURLConnection never follows https -> http
        c.setRequestProperty("Accept", accept)
        c.setRequestProperty("User-Agent", "StartupLawLibrary-Android")
        return c
    }

    fun get(url: String, maxBytes: Int, accept: String = "*/*"): ByteArray {
        val c = open(url, accept)
        try {
            val code = c.responseCode
            if (code != HttpURLConnection.HTTP_OK) throw IOException("HTTP $code")
            if (!c.url.protocol.equals("https", true)) throw IOException("redirected off https")
            if (c.contentLengthLong > maxBytes) throw TooLarge()
            c.inputStream.use { input ->
                val out = ByteArrayOutputStream()
                val buf = ByteArray(16 * 1024)
                var total = 0
                while (true) {
                    val n = input.read(buf)
                    if (n < 0) break
                    total += n
                    if (total > maxBytes) throw TooLarge()
                    out.write(buf, 0, n)
                }
                return out.toByteArray()
            }
        } finally {
            c.disconnect()
        }
    }
}
