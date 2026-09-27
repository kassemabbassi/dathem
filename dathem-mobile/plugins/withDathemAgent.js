const { withAndroidManifest } = require('expo/config-plugins');

const SERVICE_NAME = 'expo.modules.dathemagent.DathemAgentService';

module.exports = function withDathemAgent(config) {
  return withAndroidManifest(config, (modConfig) => {
    const application = modConfig.modResults.manifest.application?.[0];
    if (!application) {
      throw new Error('Dathem Agent: AndroidManifest.xml ne contient pas application.');
    }
    application.service ??= [];
    const existing = application.service.find(
      (service) => service.$?.['android:name'] === SERVICE_NAME,
    );
    if (!existing) {
      application.service.push({
        $: {
          'android:name': SERVICE_NAME,
          'android:exported': 'false',
          'android:foregroundServiceType': 'camera',
        },
      });
    }
    return modConfig;
  });
};
