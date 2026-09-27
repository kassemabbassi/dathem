package expo.modules.dathemagent

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log

class DathemAgentService : Service() {
  private var screenReceiver: BroadcastReceiver? = null
  private var screenInteractive = true

  override fun onCreate() {
    super.onCreate()
    screenInteractive = (getSystemService(Context.POWER_SERVICE) as PowerManager).isInteractive
    createNotificationChannel()
    registerScreenReceiver()
  }

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    when (intent?.action) {
      ACTION_STOP -> {
        Log.i(TAG, "Agent arrêté par l'utilisateur")
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf(startId)
        return START_NOT_STICKY
      }
      ACTION_START, null -> {
        try {
          if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
              NOTIFICATION_ID,
              buildNotification(),
              ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA,
            )
          } else {
            startForeground(NOTIFICATION_ID, buildNotification())
          }
        } catch (error: Exception) {
          Log.e(TAG, "Impossible de démarrer le service caméra au premier plan", error)
          stopSelf(startId)
          return START_NOT_STICKY
        }
        Log.i(TAG, if (screenInteractive) "Agent actif; écran allumé" else "Agent en pause; écran éteint")
        return START_STICKY
      }
      else -> {
        stopSelf(startId)
        return START_NOT_STICKY
      }
    }
  }

  private fun registerScreenReceiver() {
    if (screenReceiver != null) return
    screenReceiver = object : BroadcastReceiver() {
      override fun onReceive(context: Context?, intent: Intent?) {
        when (intent?.action) {
          Intent.ACTION_SCREEN_OFF -> {
            screenInteractive = false
            Log.i(TAG, "Écran éteint; état caméra marqué en pause")
            refreshNotification()
          }
          Intent.ACTION_SCREEN_ON -> {
            screenInteractive = true
            Log.i(TAG, "Écran rallumé; agent prêt à reprendre")
            refreshNotification()
          }
        }
      }
    }
    val filter = IntentFilter().apply {
      addAction(Intent.ACTION_SCREEN_OFF)
      addAction(Intent.ACTION_SCREEN_ON)
    }
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
      registerReceiver(screenReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
    } else {
      @Suppress("DEPRECATION")
      registerReceiver(screenReceiver, filter)
    }
  }

  private fun createNotificationChannel() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
    val channel = NotificationChannel(
      CHANNEL_ID,
      "Agent Dathem",
      NotificationManager.IMPORTANCE_LOW,
    ).apply {
      description = "Indique lorsque l'agent Dathem est actif ou suspendu."
      setShowBadge(false)
    }
    getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
  }

  private fun buildNotification(): Notification {
    val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
    val pendingIntent = launchIntent?.let {
      PendingIntent.getActivity(
        this,
        0,
        it,
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
      )
    }
    val text = if (screenInteractive) {
      "Agent prêt · caméra ajoutée à l'étape suivante"
    } else {
      "Écran éteint · agent en pause"
    }
    return Notification.Builder(this, CHANNEL_ID)
      .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
      .setContentTitle("Dathem Guard")
      .setContentText(text)
      .setCategory(Notification.CATEGORY_SERVICE)
      .setOngoing(true)
      .setOnlyAlertOnce(true)
      .setContentIntent(pendingIntent)
      .build()
  }

  private fun refreshNotification() {
    getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, buildNotification())
  }

  override fun onDestroy() {
    screenReceiver?.let {
      try {
        unregisterReceiver(it)
      } catch (error: IllegalArgumentException) {
        Log.w(TAG, "Le récepteur écran était déjà désinscrit", error)
      }
    }
    screenReceiver = null
    Log.i(TAG, "Service terminé")
    super.onDestroy()
  }

  override fun onBind(intent: Intent?): IBinder? = null

  companion object {
    const val ACTION_START = "com.kassemabbassi.dathem.agent.START"
    const val ACTION_STOP = "com.kassemabbassi.dathem.agent.STOP"
    private const val TAG = "DathemAgent"
    private const val CHANNEL_ID = "dathem-guard-agent"
    private const val NOTIFICATION_ID = 7401
  }
}
