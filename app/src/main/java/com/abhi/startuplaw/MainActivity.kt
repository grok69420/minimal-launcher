package com.abhi.startuplaw

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.browser.customtabs.CustomTabColorSchemeParams
import androidx.browser.customtabs.CustomTabsIntent
import android.widget.Toast
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * Thin native shell around the Startup Law Library artifact.
 * All UI/UX lives in the hosted page, so any change published there
 * shows up in this app on the next load — no app update needed.
 */
class MainActivity : ComponentActivity() {

    companion object {
        const val DEFAULT_HOME_URL = "https://claude.ai/artifact/DKsSn81Jr9f7GRAm4Rt1rq"
        // Remote settings: change these on GitHub and the installed app follows, no rebuild.
        const val CONFIG_URL =
            "https://raw.githubusercontent.com/grok69420/minimal-launcher/startup-law-android/config.json"
        const val RELEASE_API =
            "https://api.github.com/repos/grok69420/minimal-launcher/releases/tags/startup-law-latest"
        const val APK_URL =
            "https://github.com/grok69420/minimal-launcher/releases/download/startup-law-latest/StartupLawLibrary.apk"
        private const val INK = 0xFF111112.toInt()
        private const val BONE = 0xFFF5F5F0.toInt()
        private const val LIME = 0xFFAEF02E.toInt()
    }

    private val io = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val prefs by lazy { getSharedPreferences("shell", MODE_PRIVATE) }
    private var homeUrl = DEFAULT_HOME_URL
    private var internalHosts = listOf("claude.ai", "anthropic.com", "claudeusercontent.com")
    private var refreshAfterMs = 30 * 60 * 1000L
    private lateinit var updateBar: View

    private lateinit var web: WebView
    private lateinit var errorView: View
    private lateinit var progress: ProgressBar
    private var pausedAt = 0L

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(INK),
            navigationBarStyle = SystemBarStyle.dark(INK)
        )
        super.onCreate(savedInstanceState)
        applyConfig(prefs.getString("config", null)) // last known remote settings

        // Chrome mode: the library opens in a Chrome tab that shares your Chrome sign-in,
        // which is the only way Google sign-in works (Google blocks it inside app web views).
        if (isChromeMode()) {
            setupChromeHub()
            if (savedInstanceState == null) openFromIntent(intent)
            refreshRemote()
            return
        }

        val root = FrameLayout(this).apply { setBackgroundColor(INK) }
        web = WebView(this).apply { setBackgroundColor(INK) }
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            isIndeterminate = false
            max = 100
            progressTintList = android.content.res.ColorStateList.valueOf(LIME)
            progressBackgroundTintList = android.content.res.ColorStateList.valueOf(INK)
        }
        errorView = buildErrorView()
        updateBar = buildUpdateBar()

        root.addView(web, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        root.addView(progress, FrameLayout.LayoutParams(MATCH_PARENT, dp(3), Gravity.TOP))
        root.addView(errorView, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        root.addView(updateBar, FrameLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT, Gravity.BOTTOM))
        setContentView(root)

        // Keep content clear of the status bar, navigation bar and keyboard.
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }

        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(web, true) // the artifact runs in a sandboxed frame
        }

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            loadWithOverviewMode = true
            useWideViewPort = true
            setSupportMultipleWindows(false)
            // Present as normal Chrome so claude.ai serves the standard site.
            userAgentString = userAgentString.replace("; wv", "")
        }

        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                if (isGoogleSignIn(uri)) {
                    switchToChromeMode()
                    return true
                }
                if (isInternal(uri)) return false
                openExternally(uri)
                return true
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) errorView.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
            }
        }

        web.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                progress.progress = newProgress
                progress.visibility = if (newProgress >= 100) View.GONE else View.VISIBLE
            }
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack()
                else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        if (savedInstanceState != null) web.restoreState(savedInstanceState)
        else openFromIntent(intent)
        refreshRemote()
    }

    /** Pull remote settings and check for a newer app build, off the main thread. */
    private fun refreshRemote() {
        io.execute {
            fetch(CONFIG_URL)?.let { json ->
                main.post {
                    val oldHome = homeUrl
                    if (applyConfig(json)) {
                        prefs.edit().putString("config", json).apply()
                        if (::web.isInitialized && homeUrl != oldHome && web.url?.startsWith(oldHome) == true) web.loadUrl(homeUrl)
                    }
                }
            }
            fetch(RELEASE_API)?.let { json ->
                val latest = runCatching {
                    Regex("versionCode:\\s*(\\d+)").find(JSONObject(json).optString("body"))?.groupValues?.get(1)?.toInt()
                }.getOrNull() ?: return@let
                if (latest > BuildConfig.VERSION_CODE) main.post { updateBar.visibility = View.VISIBLE }
            }
        }
    }

    private fun applyConfig(json: String?): Boolean {
        if (json == null) return false
        return runCatching {
            val o = JSONObject(json)
            val url = o.optString("homeUrl")
            if (url.startsWith("https://")) homeUrl = url
            o.optJSONArray("internalHosts")?.let { arr ->
                val list = (0 until arr.length()).map { arr.getString(it) }.filter { it.isNotBlank() }
                if (list.isNotEmpty()) internalHosts = list
            }
            val mins = o.optInt("refreshMinutes", 0)
            if (mins > 0) refreshAfterMs = mins * 60_000L
            true
        }.getOrDefault(false)
    }

    private fun fetch(url: String): String? = runCatching {
        (URL(url).openConnection() as HttpURLConnection).run {
            connectTimeout = 8000; readTimeout = 8000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Cache-Control", "no-cache")
            try { if (responseCode == 200) inputStream.bufferedReader().readText() else null }
            finally { disconnect() }
        }
    }.getOrNull()

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        openFromIntent(intent)
    }

    override fun onPause() {
        super.onPause()
        pausedAt = SystemClock.elapsedRealtime()
        CookieManager.getInstance().flush()
    }

    override fun onResume() {
        super.onResume()
        // Pick up any newly published design or content after a long break.
        if (pausedAt > 0 && SystemClock.elapsedRealtime() - pausedAt > refreshAfterMs) {
            if (::web.isInitialized) web.reload()
            refreshRemote()
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        if (::web.isInitialized) web.saveState(outState)
    }

    /** Sign-in links from email (claude.ai) open here; everything else starts at the library. */
    private fun openFromIntent(intent: Intent?) {
        val data = intent?.data
        val target = if (data != null && isInternal(data)) data.toString() else homeUrl
        if (isChromeMode()) { openInChrome(target); return }
        errorView.visibility = View.GONE
        web.loadUrl(target)
    }

    private fun isChromeMode() = prefs.getString("mode", "app") == "chrome"

    private fun isGoogleSignIn(uri: Uri): Boolean {
        val host = uri.host ?: return false
        return host == "accounts.google.com" || host.endsWith(".accounts.google.com")
    }

    /** Called when Google sign-in starts inside the app: move to Chrome mode for good. */
    private fun switchToChromeMode() {
        prefs.edit().putString("mode", "chrome").apply()
        Toast.makeText(this, "Google sign-in opens in Chrome. The library will open there from now on.", Toast.LENGTH_LONG).show()
        openInChrome(homeUrl)
        recreate()
    }

    private fun switchToAppMode() {
        prefs.edit().putString("mode", "app").apply()
        recreate()
    }

    private fun openInChrome(url: String) {
        val colors = CustomTabColorSchemeParams.Builder()
            .setToolbarColor(INK).setNavigationBarColor(INK).build()
        val tab = CustomTabsIntent.Builder()
            .setDefaultColorSchemeParams(colors)
            .setColorScheme(CustomTabsIntent.COLOR_SCHEME_DARK)
            .setShowTitle(false)
            .setUrlBarHidingEnabled(true)
            .setShareState(CustomTabsIntent.SHARE_STATE_OFF)
            .build()
        try { tab.launchUrl(this, Uri.parse(url)) } catch (_: Exception) { openExternally(Uri.parse(url)) }
    }

    /** Small home screen shown behind the Chrome tab: open the library, update, or switch mode. */
    private fun setupChromeHub() {
        val root = FrameLayout(this).apply { setBackgroundColor(INK) }
        updateBar = buildUpdateBar()
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(32), dp(32), dp(32), dp(32))
            addView(TextView(context).apply {
                text = "STARTUP\nLAW LIBRARY"
                setTextColor(BONE); textSize = 34f; gravity = Gravity.CENTER
                typeface = Typeface.create("sans-serif-black", Typeface.NORMAL)
            })
            addView(TextView(context).apply {
                text = "Opens in Chrome so your Google sign-in works."
                setTextColor(Color.parseColor("#A7A39A")); textSize = 15f; gravity = Gravity.CENTER
                setPadding(0, dp(12), 0, dp(28))
            })
            addView(pillButton("OPEN LIBRARY  →", LIME, INK) { openInChrome(homeUrl) },
                LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT))
            addView(Button(context).apply {
                text = "Use in-app mode instead (email sign-in)"
                isAllCaps = false
                setTextColor(Color.parseColor("#A7A39A"))
                setBackgroundColor(Color.TRANSPARENT)
                setOnClickListener { switchToAppMode() }
            }, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { topMargin = dp(18) })
        }
        root.addView(col, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        root.addView(updateBar, FrameLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT, Gravity.BOTTOM))
        setContentView(root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
    }

    private fun pillButton(label: String, bg: Int, fg: Int, onClick: () -> Unit) = Button(this).apply {
        text = label
        setTextColor(fg)
        typeface = Typeface.DEFAULT_BOLD
        background = android.graphics.drawable.GradientDrawable().apply { setColor(bg); cornerRadius = dp(999).toFloat() }
        setPadding(dp(28), dp(14), dp(28), dp(14))
        setOnClickListener { onClick() }
    }

    private fun isInternal(uri: Uri): Boolean {
        val host = uri.host ?: return false
        if (uri.scheme != "https") return false
        return internalHosts.any { host == it || host.endsWith(".$it") }
    }

    private fun openExternally(uri: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (_: Exception) { /* no app can open it */ }
    }

    private fun buildErrorView(): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER
        setBackgroundColor(INK)
        setPadding(dp(32), dp(32), dp(32), dp(32))
        visibility = View.GONE
        addView(TextView(context).apply {
            text = "CAN’T REACH\nTHE LIBRARY"
            setTextColor(BONE)
            textSize = 30f
            typeface = Typeface.create("sans-serif-black", Typeface.NORMAL)
            gravity = Gravity.CENTER
        })
        addView(TextView(context).apply {
            text = "Check your internet connection and try again."
            setTextColor(Color.parseColor("#A7A39A"))
            textSize = 15f
            gravity = Gravity.CENTER
            setPadding(0, dp(12), 0, dp(24))
        })
        addView(Button(context).apply {
            text = "RETRY  →"
            setTextColor(INK)
            typeface = Typeface.DEFAULT_BOLD
            background = android.graphics.drawable.GradientDrawable().apply {
                setColor(LIME); cornerRadius = dp(999).toFloat()
            }
            setPadding(dp(28), dp(14), dp(28), dp(14))
            setOnClickListener {
                errorView.visibility = View.GONE
                web.reload()
            }
        }, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT))
    }

    /** Lime bar shown when GitHub has a newer build; installs over this one, keeping your sign-in. */
    private fun buildUpdateBar(): View = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setBackgroundColor(LIME)
        setPadding(dp(20), dp(12), dp(12), dp(12))
        visibility = View.GONE
        addView(TextView(context).apply {
            text = "APP UPDATE READY"
            setTextColor(INK)
            typeface = Typeface.DEFAULT_BOLD
            textSize = 14f
        }, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
        addView(Button(context).apply {
            text = "INSTALL  →"
            setTextColor(LIME)
            typeface = Typeface.DEFAULT_BOLD
            background = android.graphics.drawable.GradientDrawable().apply {
                setColor(INK); cornerRadius = dp(999).toFloat()
            }
            setPadding(dp(18), dp(8), dp(18), dp(8))
            setOnClickListener { openExternally(Uri.parse(APK_URL)) }
        })
        addView(Button(context).apply {
            text = "LATER"
            setTextColor(INK)
            setBackgroundColor(Color.TRANSPARENT)
            setOnClickListener { updateBar.visibility = View.GONE }
        })
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()
}
