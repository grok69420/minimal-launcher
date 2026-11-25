package com.abhi.startuplaw.data

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Live "is there a working internet connection" signal. */
class Connectivity(context: Context) {
    private val cm = context.getSystemService(ConnectivityManager::class.java)
    private val _online = MutableStateFlow(current())
    val online: StateFlow<Boolean> = _online.asStateFlow()
    private val networks = HashMap<Network, Boolean>()

    private val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
            synchronized(networks) { networks[network] = caps.usable(); publish() }
        }
        override fun onLost(network: Network) {
            synchronized(networks) { networks.remove(network); publish() }
        }
    }

    init {
        runCatching { cm?.registerDefaultNetworkCallback(callback) }
    }

    private fun publish() { _online.value = networks.values.any { it } }

    private fun current(): Boolean = runCatching {
        val n = cm?.activeNetwork ?: return false
        cm.getNetworkCapabilities(n)?.usable() == true
    }.getOrDefault(false)

    private fun NetworkCapabilities.usable() =
        hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
}
