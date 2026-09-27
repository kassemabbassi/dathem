package expo.modules.dathemagent

import android.content.Intent
import android.os.Build
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class DathemAgentModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("DathemAgent")

    AsyncFunction("start") {
      val context = appContext.reactContext
        ?: throw IllegalStateException("Le contexte Android de Dathem est indisponible.")
      val intent = Intent(context, DathemAgentService::class.java).apply {
        action = DathemAgentService.ACTION_START
      }
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        context.startForegroundService(intent)
      } else {
        context.startService(intent)
      }
      true
    }

    AsyncFunction("stop") {
      val context = appContext.reactContext
        ?: throw IllegalStateException("Le contexte Android de Dathem est indisponible.")
      val intent = Intent(context, DathemAgentService::class.java).apply {
        action = DathemAgentService.ACTION_STOP
      }
      context.startService(intent)
      true
    }
  }
}
