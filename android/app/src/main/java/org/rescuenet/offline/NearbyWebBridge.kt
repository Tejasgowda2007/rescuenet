package org.rescuenet.offline

import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebView
import org.json.JSONArray
import org.json.JSONObject

/**
 * JavaScript Interface Bridge between RescueNet PWA Web Dashboard and
 * Android Native Google Nearby Connections mesh service.
 */
class NearbyWebBridge(
    private val webView: WebView,
    private val meshService: NearbyMeshService
) {
    companion object {
        private const val TAG = "NearbyWebBridge"
    }

    private val mainHandler = Handler(Looper.getMainLooper())

    init {
        // Wire up callbacks from meshService to trigger DOM custom events
        meshService.onPayloadReceived = { endpointId, rawBytes ->
            val base64 = Base64.encodeToString(rawBytes, Base64.NO_WRAP)
            val json = JSONObject().apply {
                put("endpointId", endpointId)
                put("payloadBase64", base64)
            }
            dispatchJsEvent("rescuenet-nearby-payload", json.toString())
        }

        meshService.onPeerConnected = { endpointId, name ->
            val json = JSONObject().apply {
                put("endpointId", endpointId)
                put("name", name)
            }
            dispatchJsEvent("rescuenet-peer-connected", json.toString())
        }

        meshService.onPeerDisconnected = { endpointId ->
            val json = JSONObject().apply {
                put("endpointId", endpointId)
            }
            dispatchJsEvent("rescuenet-peer-disconnected", json.toString())
        }
    }

    @JavascriptInterface
    fun isAvailable(): Boolean {
        return true
    }

    @JavascriptInterface
    fun startMesh(nodeId: String): Boolean {
        Log.i(TAG, "JS requested startMesh for: $nodeId")
        meshService.startMesh(nodeId)
        return true
    }

    @JavascriptInterface
    fun stopMesh() {
        Log.i(TAG, "JS requested stopMesh")
        meshService.stopMesh()
    }

    @JavascriptInterface
    fun getConnectedPeers(): String {
        val list = JSONArray()
        meshService.connectedPeers.keys.forEach { list.put(it) }
        return list.toString()
    }

    @JavascriptInterface
    fun broadcastPayload(base64Payload: String): Boolean {
        return try {
            val bytes = Base64.decode(base64Payload, Base64.NO_WRAP)
            meshService.broadcastBytes(bytes)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to decode base64 payload", e)
            false
        }
    }

    @JavascriptInterface
    fun sendToPeer(peerId: String, base64Payload: String): Boolean {
        return try {
            val bytes = Base64.decode(base64Payload, Base64.NO_WRAP)
            meshService.sendBytesToPeer(peerId, bytes)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send to peer $peerId", e)
            false
        }
    }

    private fun dispatchJsEvent(eventName: String, detailJson: String) {
        mainHandler.post {
            val script = "window.dispatchEvent(new CustomEvent('$eventName', { detail: $detailJson }));"
            webView.evaluateJavascript(script, null)
        }
    }
}
