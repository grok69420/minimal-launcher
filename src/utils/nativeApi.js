import {NativeModules} from 'react-native';

const {InstalledAppsModule, AppBlockerModule} = NativeModules;

export const getInstalledApps = () => InstalledAppsModule.getInstalledApps();
export const getBlockedApps = () => AppBlockerModule.getBlockedApps();
export const setBlockedApps = packages => AppBlockerModule.setBlockedApps(packages);
export const isBlockingEnabled = () => AppBlockerModule.isBlockingEnabled();
export const setBlockingEnabled = enabled => AppBlockerModule.setBlockingEnabled(enabled);
export const hasUsageStatsPermission = () => AppBlockerModule.hasUsageStatsPermission();
export const openUsageStatsSettings = () => AppBlockerModule.openUsageStatsSettings();
export const launchApp = packageName => AppBlockerModule.launchApp(packageName);
