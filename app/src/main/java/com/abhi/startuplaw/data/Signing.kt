package com.abhi.startuplaw.data

import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import java.io.ByteArrayInputStream
import java.security.MessageDigest
import java.security.PublicKey
import java.security.Signature
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate

/**
 * Content and app updates are trusted only if they are signed by the same key that signed
 * this installed app. The public key is read from the app's own signing certificate, so no
 * key is embedded in the code and a different build cannot vouch for foreign content.
 */
object Signing {

    /** Pure check, unit-tested: does [sig] verify [data] under any of [keys]? */
    fun verify(data: ByteArray, sig: ByteArray, keys: List<PublicKey>): Boolean = keys.any { key ->
        val alg = when (key.algorithm) {
            "RSA" -> "SHA256withRSA"
            "EC" -> "SHA256withECDSA"
            else -> return@any false
        }
        runCatching {
            Signature.getInstance(alg).run { initVerify(key); update(data); verify(sig) }
        }.getOrDefault(false)
    }

    fun appKeys(context: Context): List<PublicKey> =
        signatureBytes(context.packageManager, context.packageName, null).mapNotNull { toCert(it)?.publicKey }

    fun appCertDigests(context: Context): Set<String> =
        signatureBytes(context.packageManager, context.packageName, null).map { sha256(it) }.toSet()

    /** Signing-certificate digests of an APK file that has not been installed yet. */
    fun archiveCertDigests(pm: PackageManager, apkPath: String): Pair<String?, Set<String>> {
        val info = archiveInfo(pm, apkPath) ?: return null to emptySet()
        return info.packageName to signatureBytes(pm, null, info).map { sha256(it) }.toSet()
    }

    @SuppressLint("PackageManagerGetSignatures")
    @Suppress("DEPRECATION")
    private fun archiveInfo(pm: PackageManager, path: String): PackageInfo? = runCatching {
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        if (Build.VERSION.SDK_INT >= 33) pm.getPackageArchiveInfo(path, PackageManager.PackageInfoFlags.of(flags.toLong()))
        else pm.getPackageArchiveInfo(path, flags)
    }.getOrNull()

    @SuppressLint("PackageManagerGetSignatures")
    @Suppress("DEPRECATION")
    private fun signatureBytes(pm: PackageManager, pkg: String?, given: PackageInfo?): List<ByteArray> = runCatching {
        if (Build.VERSION.SDK_INT >= 28) {
            val info = given ?: if (Build.VERSION.SDK_INT >= 33)
                pm.getPackageInfo(pkg!!, PackageManager.PackageInfoFlags.of(PackageManager.GET_SIGNING_CERTIFICATES.toLong()))
            else pm.getPackageInfo(pkg!!, PackageManager.GET_SIGNING_CERTIFICATES)
            val si = info.signingInfo ?: return@runCatching emptyList()
            val sigs = if (si.hasMultipleSigners()) si.apkContentsSigners else si.signingCertificateHistory
            sigs.orEmpty().map { it.toByteArray() }
        } else {
            val info = given ?: pm.getPackageInfo(pkg!!, PackageManager.GET_SIGNATURES)
            info.signatures.orEmpty().map { it.toByteArray() }
        }
    }.getOrDefault(emptyList())

    private fun toCert(bytes: ByteArray): X509Certificate? = runCatching {
        CertificateFactory.getInstance("X.509").generateCertificate(ByteArrayInputStream(bytes)) as X509Certificate
    }.getOrNull()

    fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
}
