package org.rescuenet.offline

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.View
import android.webkit.*
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

/**
 * Main Android Activity for RescueNet FieldMesh.
 *
 * Hosts the offline-first PWA dashboard in a hardware-accelerated WebView
 * with full IndexedDB, LocalStorage, and ServiceWorker support, bound to
 * Google Nearby Connections for zero-network peer-to-peer mesh synchronization.
 */
class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "MainActivity"
        // Default target URL: local laptop IP on Wi-Fi hotspot or emulator loopback
        const val DEFAULT_LOCAL_URL = "http://10.0.2.2:8000"
    }

    private lateinit var webView: WebView
    private lateinit var meshService: NearbyMeshService
    private var webBridge: NearbyWebBridge? = null

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.entries.all { it.value }
        if (allGranted) {
            Log.i(TAG, "All Nearby mesh permissions granted")
            meshService.startMesh("android-${Build.MODEL.replace("\\s+".toRegex(), "-").lowercase()}")
        } else {
            Log.w(TAG, "Some permissions were denied; Nearby peer discovery will be limited")
            Toast.makeText(this, "Permissions required for direct offline P2P mesh", Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialize Nearby Mesh Service
        meshService = NearbyMeshService(this)

        // Setup WebView
        webView = WebView(this).apply {
            id = View.generateViewId()
        }
        setContentView(webView)

        configureWebView()
        requestMeshPermissions()

        // Load the RescueNet application
        val targetUrl = intent.getStringExtra("EXTRA_URL") ?: DEFAULT_LOCAL_URL
        webView.loadUrl(targetUrl)
    }

    private fun configureWebView() {
        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true // Enable IndexedDB & localStorage
        settings.databaseEnabled = true
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.cacheMode = WebSettings.LOAD_DEFAULT
        settings.useWideViewPort = true
        settings.loadWithOverviewMode = true

        // Register the Native Nearby Bridge to window.AndroidNearby
        webBridge = NearbyWebBridge(webView, meshService)
        webView.addJavascriptInterface(webBridge!!, "AndroidNearby")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                return false
            }

            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                super.onReceivedError(view, request, error)
                Log.w(TAG, "WebView error: ${error?.description}")
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean {
                Log.d("RescueNetJS", "${consoleMessage?.message()} -- line ${consoleMessage?.lineNumber()}")
                return true
            }
        }
    }

    private fun requestMeshPermissions() {
        val permissions = mutableListOf<String>()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            permissions.add(Manifest.permission.BLUETOOTH_SCAN)
            permissions.add(Manifest.permission.BLUETOOTH_ADVERTISE)
            permissions.add(Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            permissions.add(Manifest.permission.BLUETOOTH)
            permissions.add(Manifest.permission.BLUETOOTH_ADMIN)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.NEARBY_WIFI_DEVICES)
        }

        permissions.add(Manifest.permission.ACCESS_FINE_LOCATION)
        permissions.add(Manifest.permission.ACCESS_COARSE_LOCATION)

        val needed = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (needed.isNotEmpty()) {
            permissionLauncher.launch(needed.toTypedArray())
        } else {
            meshService.startMesh("android-${Build.MODEL.replace("\\s+".toRegex(), "-").lowercase()}")
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        meshService.stopMesh()
    }
}
