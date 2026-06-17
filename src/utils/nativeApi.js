import {NativeModules} from 'react-native';

const {InstalledAppsModule, AppBlockerModule} = NativeModules;

// ---- Apps -----------------------------------------------------------------
export const getInstalledApps = () => InstalledAppsModule.getInstalledApps();
export const launchApp = packageName => AppBlockerModule.launchApp(packageName);

// ---- Blocklist ------------------------------------------------------------
export const getBlockedApps = () => AppBlockerModule.getBlockedApps();
export const setBlockedApps = packages => AppBlockerModule.setBlockedApps(packages);
export const isBlockingEnabled = () => AppBlockerModule.isBlockingEnabled();
export const setBlockingEnabled = enabled =>
  AppBlockerModule.setBlockingEnabled(enabled);
export const startBlockerService = () => AppBlockerModule.startBlockerService();

// ---- Permissions ----------------------------------------------------------
export const getPermissionStatus = () => AppBlockerModule.getPermissionStatus();

export const hasUsageStatsPermission = () =>
  AppBlockerModule.hasUsageStatsPermission();
export const openUsageStatsSettings = () =>
  AppBlockerModule.openUsageStatsSettings();

export const hasOverlayPermission = () => AppBlockerModule.hasOverlayPermission();
export const openOverlaySettings = () => AppBlockerModule.openOverlaySettings();

export const hasNotificationPermission = () =>
  AppBlockerModule.hasNotificationPermission();
export const requestNotificationPermission = () =>
  AppBlockerModule.requestNotificationPermission();

export const isBatteryOptimizationIgnored = () =>
  AppBlockerModule.isBatteryOptimizationIgnored();
export const requestIgnoreBatteryOptimization = () =>
  AppBlockerModule.requestIgnoreBatteryOptimization();

export const isDefaultLauncher = () => AppBlockerModule.isDefaultLauncher();
export const openHomeSettings = () => AppBlockerModule.openHomeSettings();

// ---- Security PIN ---------------------------------------------------------
export const hasPin = () => AppBlockerModule.hasPin();
export const setPin = pin => AppBlockerModule.setPin(pin);
export const verifyPin = pin => AppBlockerModule.verifyPin(pin);
export const clearPin = () => AppBlockerModule.clearPin();
