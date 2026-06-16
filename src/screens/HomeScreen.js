import React, {useState, useEffect, useRef, useCallback} from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  PanResponder,
  StyleSheet,
  AppState,
} from 'react-native';
import {getBlockedApps} from '../utils/nativeApi';

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
        {h}:{m}
      </Text>
      <Text style={styles.date}>{dateStr}</Text>
    </View>
  );
}

export default function HomeScreen({navigate}) {
  const [blockedCount, setBlockedCount] = useState(0);

  const refresh = useCallback(() => {
    getBlockedApps()
      .then(list => setBlockedCount(list.length))
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

  return (
    <View style={styles.container} {...pan.panHandlers}>
      <Clock />

      <Text style={styles.swipeHint}>swipe up for apps</Text>

      <View style={styles.bottomRow}>
        <TouchableOpacity
          style={styles.btn}
          onPress={() => navigate('blocked')}>
          <Text style={styles.btnIcon}>🚫</Text>
          <Text style={styles.btnLabel}>
            {blockedCount > 0 ? `${blockedCount} Blocked` : 'Block Apps'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.btn} onPress={() => navigate('drawer')}>
          <Text style={styles.btnIcon}>⊞</Text>
          <Text style={styles.btnLabel}>All Apps</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
    paddingHorizontal: 28,
  },
  clockWrap: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  clock: {
    fontSize: 88,
    fontWeight: '100',
    color: '#fff',
    letterSpacing: -4,
  },
  date: {
    fontSize: 15,
    color: '#555',
    marginTop: 10,
    letterSpacing: 0.5,
  },
  swipeHint: {
    color: '#222',
    fontSize: 11,
    textAlign: 'center',
    letterSpacing: 2,
    textTransform: 'uppercase',
    paddingBottom: 28,
  },
  bottomRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingBottom: 44,
  },
  btn: {
    alignItems: 'center',
    padding: 16,
    minWidth: 90,
  },
  btnIcon: {
    fontSize: 26,
    marginBottom: 6,
  },
  btnLabel: {
    color: '#555',
    fontSize: 12,
    letterSpacing: 0.5,
  },
});
