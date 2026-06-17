import React, {useState, useEffect, useCallback} from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  AppState,
} from 'react-native';
import FadeInView from '../components/FadeInView';
import {colors, radius} from '../theme';
import {
  getPermissionStatus,
  startBlockerService,
  openUsageStatsSettings,
  openOverlaySettings,
  openHomeSettings,
  requestIgnoreBatteryOptimization,
  requestNotificationPermission,
} from '../utils/nativeApi';

const PERMISSIONS = [
  {
    key: 'usageStats',
    icon: '📊',
    title: 'Usage Access',
    desc: 'Lets the launcher detect which app is open so it can block it.',
    required: true,
    open: openUsageStatsSettings,
  },
  {
    key: 'overlay',
    icon: '🪟',
    title: 'Display Over Other Apps',
    desc: 'Shows the block screen on top of distracting apps. Without this, blocking can’t work on modern Android.',
    required: true,
    open: openOverlaySettings,
  },
  {
    key: 'defaultLauncher',
    icon: '🏠',
    title: 'Set as Default Launcher',
    desc: 'Makes this your home screen so focus stays front and centre.',
    required: false,
    open: openHomeSettings,
  },
  {
    key: 'batteryOptIgnored',
    icon: '🔋',
    title: 'Ignore Battery Optimization',
    desc: 'Stops Android from killing the blocker in the background.',
    required: false,
    open: requestIgnoreBatteryOptimization,
  },
  {
    key: 'notifications',
    icon: '🔔',
    title: 'Notifications',
    desc: 'Shows the quiet focus-mode status notification.',
    required: false,
    open: requestNotificationPermission,
  },
];

export default function PermissionsScreen({navigate}) {
  const [status, setStatus] = useState({});

  const refresh = useCallback(() => {
    getPermissionStatus()
      .then(s => {
        setStatus(s);
        if (s.usageStats && s.overlay) {
          startBlockerService().catch(() => {});
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const sub = AppState.addEventListener('change', state => {
      if (state === 'active') refresh();
    });
    return () => sub.remove();
  }, [refresh]);

  const coreReady = status.usageStats && status.overlay;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigate('home')} style={styles.backBtn}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Permissions</Text>
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scroll}>
        <FadeInView>
          <View
            style={[styles.statusBanner, coreReady ? styles.bannerOk : styles.bannerWarn]}>
            <Text style={styles.statusEmoji}>{coreReady ? '✅' : '⚠️'}</Text>
            <Text style={styles.statusText}>
              {coreReady
                ? 'Blocking is fully active. You’re protected.'
                : 'Grant the two required permissions to turn on blocking.'}
            </Text>
          </View>

          {PERMISSIONS.map(p => {
            const granted = !!status[p.key];
            return (
              <View key={p.key} style={styles.card}>
                <Text style={styles.cardIcon}>{p.icon}</Text>
                <View style={styles.cardBody}>
                  <View style={styles.cardTitleRow}>
                    <Text style={styles.cardTitle}>{p.title}</Text>
                    {p.required && !granted ? (
                      <Text style={styles.requiredTag}>REQUIRED</Text>
                    ) : null}
                  </View>
                  <Text style={styles.cardDesc}>{p.desc}</Text>
                </View>
                {granted ? (
                  <View style={styles.grantedPill}>
                    <Text style={styles.grantedText}>✓</Text>
                  </View>
                ) : (
                  <TouchableOpacity
                    style={styles.grantBtn}
                    onPress={() => p.open().catch(() => {})}>
                    <Text style={styles.grantBtnText}>Grant</Text>
                  </TouchableOpacity>
                )}
              </View>
            );
          })}

          <Text style={styles.footnote}>
            Everything runs on your device. No data ever leaves your phone.
          </Text>
        </FadeInView>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: colors.bg, paddingTop: 56},
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    marginBottom: 14,
  },
  backBtn: {marginRight: 14, padding: 4},
  backText: {color: colors.textDim, fontSize: 15},
  title: {color: colors.text, fontSize: 22, fontWeight: '700'},
  scroll: {paddingHorizontal: 16, paddingBottom: 40},
  statusBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radius.md,
    padding: 14,
    marginBottom: 18,
    borderWidth: 1,
  },
  bannerOk: {backgroundColor: '#0E1F18', borderColor: colors.success},
  bannerWarn: {backgroundColor: '#1F1A0A', borderColor: colors.warn},
  statusEmoji: {fontSize: 18, marginRight: 10},
  statusText: {color: colors.text, fontSize: 13.5, flex: 1, lineHeight: 19},
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 16,
    marginBottom: 12,
  },
  cardIcon: {fontSize: 24, marginRight: 14},
  cardBody: {flex: 1, marginRight: 12},
  cardTitleRow: {flexDirection: 'row', alignItems: 'center'},
  cardTitle: {color: colors.text, fontSize: 15.5, fontWeight: '600'},
  requiredTag: {
    color: colors.warn,
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.8,
    marginLeft: 8,
    marginTop: 1,
  },
  cardDesc: {color: colors.textDim, fontSize: 12.5, lineHeight: 17, marginTop: 4},
  grantBtn: {
    backgroundColor: colors.accent,
    borderRadius: radius.pill,
    paddingHorizontal: 18,
    paddingVertical: 9,
  },
  grantBtnText: {color: '#fff', fontSize: 13, fontWeight: '700'},
  grantedPill: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.success,
    alignItems: 'center',
    justifyContent: 'center',
  },
  grantedText: {color: '#06281C', fontSize: 16, fontWeight: '900'},
  footnote: {
    color: colors.textFaint,
    fontSize: 12,
    textAlign: 'center',
    marginTop: 16,
    lineHeight: 17,
  },
});
