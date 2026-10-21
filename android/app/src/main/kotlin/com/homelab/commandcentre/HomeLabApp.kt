package com.homelab.commandcentre

import android.app.Application
import com.homelab.commandcentre.work.AlertWorker

class HomeLabApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        AlertWorker.createChannel(this)
        if (container.prefs.alertNotifications) AlertWorker.schedule(this)
    }
}
