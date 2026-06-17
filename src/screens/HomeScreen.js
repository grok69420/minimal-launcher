import React, {useState, useEffect, useRef, useCallback} from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  PanResponder,
  StyleSheet,
  AppState,
} from 'react-native';
import {
  getBlockedApps,
  isBlockingEnabled,
  getPermissionStatus,
  startBlockerService,
} from '../utils/nativeApi';
import {colors, radius} from '../theme';

function Clock() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  const dateStr = now.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });

  return (
    <View style={styles.clockWrap}>
      <Text style={styles.clock}>
        {h}
        <Text style={styles.colon}>:</Text>
        {m}
      </Text>
      <Text style={styles.date}>{dateStr}</Text>
    </View>
  );
}

export default function HomeScreen({navigate}) {
  const [blockedCount, setBlockedCount] = useState(0);
  const [enabled, setEnabled] = useState(true);
  const [coreReady, setCoreReady] = useState(true);

  const refresh = useCallback(() => {
    getBlockedApps()
      .then(list => setBlockedCount(list.length))
      .catch(() => {});
    isBlockingEnabled()
      .then(setEnabled)
      .catch(() => {});
    getPermissionStatus()
      .then(s => {
        const ready = !!(s.usageStats && s.overlay);
        setCoreReady(ready);
        if (ready) startBlockerService().catch(() => {});
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

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) =>
        Math.abs(g.dy) > 15 && Math.abs(g.dy) > Math.abs(g.dx),
      onPanResponderRelease: (_, g) => {
        if (g.dy < -60) navigate('drawer');
      },
    }),
  ).current;

  const active = enabled && coreReady;

  return (
    <View style={styles.container} {...pan.panHandlers}>
      <View style={styles.topBar}>
        <View
          style={[
            styles.statusPill,
            active ? styles.pillActive : styles.pillIdle,
          ]}>
          <View
            style={[styles.statusDot, active ? styles.dotActive : styles.dotIdle]}
          />
          <Text style={styles.statusText}>
            {active
              ? `Focus on · ${blockedCount} blocked`
              : enabled
              ? 'Setup needed'
              : 'Blocking paused'}
          </Text>
        </View>
      </View>

      <Clock />

      {!coreReady ? (
        <TouchableOpacity
          style={styles.warnBanner}
          onPress={() => navigate('permissions')}>
          <Text style={styles.warnEmoji}>⚠️</Text>
          <Text style={styles.warnText}>
            Blocking is inactive. Tap to finish setup.
          </Text>
          <Text style={styles.warnChevron}>›</Text>
        </TouchableOpacity>
      ) : (
        <Text style={styles.swipeHint}>swipe up for apps</Text>
      )}

      <View style={styles.bottomRow}>
        <TouchableOpacity style={styles.btn} onPress={() => navigate('drawer')}>
          <Text style={styles.btnIcon}>⊞</Text>
          <Text style={styles.btnLabel}>Apps</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.btn} onPress={() => navigate('blocked')}>
          <Text style={styles.btnIcon}>🛡️</Text>
          <Text style={styles.btnLabel}>Blocklist</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.btn}
          onPress={() => navigate('permissions')}>
          <Text style={styles.btnIcon}>⚙️</Text>
          <Text style={styles.btnLabel}>Setup</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: 28,
    paddingTop: 56,
  },
  topBar: {alignItems: 'center'},
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radius.pill,
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderWidth: 1,
  },
  pillActive: {backgroundColor: colors.accentDim, borderColor: colors.accent},
  pillIdle: {backgroundColor: colors.card, borderColor: colors.border},
  statusDot: {width: 7, height: 7, borderRadius: 4, marginRight: 8},
  dotActive: {backgroundColor: colors.accent},
  dotIdle: {backgroundColor: colors.textFaint},
  statusText: {color: colors.text, fontSize: 12.5, fontWeight: '600'},
  clockWrap: {flex: 1, justifyContent: 'center', alignItems: 'center'},
  clock: {fontSize: 92, fontWeight: '200', color: colors.text, letterSpacing: -4},
  colon: {color: colors.accent, fontWeight: '200'},
  date: {fontSize: 15, color: colors.textDim, marginTop: 8, letterSpacing: 0.5},
  swipeHint: {
    color: colors.textFaint,
    fontSize: 11,
    textAlign: 'center',
    letterSpacing: 2,
    textTransform: 'uppercase',
    paddingBottom: 28,
  },
  warnBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F1A0A',
    borderColor: colors.warn,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: 14,
    paddingVertical: 13,
    marginBottom: 24,
  },
  warnEmoji: {fontSize: 16, marginRight: 10},
  warnText: {color: colors.text, fontSize: 13.5, flex: 1},
  warnChevron: {color: colors.warn, fontSize: 22, fontWeight: '300'},
  bottomRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingBottom: 44,
  },
  btn: {alignItems: 'center', padding: 14, minWidth: 80},
  btnIcon: {fontSize: 24, marginBottom: 6},
  btnLabel: {color: colors.textDim, fontSize: 12, letterSpacing: 0.3},
});
