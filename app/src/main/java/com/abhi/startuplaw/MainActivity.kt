package com.abhi.startuplaw

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
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
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

/**
 * Thin native shell around the Startup Law Library artifact.
 * All UI/UX lives in the hosted page, so any change published there
 * shows up in this app on the next load — no app update needed.
 */
class MainActivity : ComponentActivity() {

    companion object {
        const val HOME_URL = "https://claude.ai/artifact/DKsSn81Jr9f7GRAm4Rt1rq"
        private const val INK = 0xFF111112.toInt()
        private const val BONE = 0xFFF5F5F0.toInt()
        private const val LIME = 0xFFAEF02E.toInt()
        private const val REFRESH_AFTER_MS = 30 * 60 * 1000L // reload if away 30+ min
    }

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

        val root = FrameLayout(this).apply { setBackgroundColor(INK) }
        web = WebView(this).apply { setBackgroundColor(INK) }
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            isIndeterminate = false
            max = 100
            progressTintList = android.content.res.ColorStateList.valueOf(LIME)
            progressBackgroundTintList = android.content.res.ColorStateList.valueOf(INK)
        }
        errorView = buildErrorView()

        root.addView(web, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        root.addView(progress, FrameLayout.LayoutParams(MATCH_PARENT, dp(3), Gravity.TOP))
        root.addView(errorView, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
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
    }

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
        if (pausedAt > 0 && SystemClock.elapsedRealtime() - pausedAt > REFRESH_AFTER_MS) web.reload()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    /** Sign-in links from email (claude.ai) open here; everything else starts at the library. */
    private fun openFromIntent(intent: Intent?) {
        val data = intent?.data
        errorView.visibility = View.GONE
        if (data != null && isInternal(data)) web.loadUrl(data.toString()) else web.loadUrl(HOME_URL)
    }

    private fun isInternal(uri: Uri): Boolean {
        val host = uri.host ?: return false
        if (uri.scheme != "https") return false
        return host == "claude.ai" || host.endsWith(".claude.ai") ||
            host.endsWith("anthropic.com") || host.endsWith("claudeusercontent.com")
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

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()
}
