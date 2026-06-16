import React, {useState, useEffect, useCallback} from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  Switch,
  StyleSheet,
  Alert,
  AppState,
} from 'react-native';
import {
  getInstalledApps,
  getBlockedApps,
  setBlockedApps,
  isBlockingEnabled,
  setBlockingEnabled,
  hasUsageStatsPermission,
  openUsageStatsSettings,
} from '../utils/nativeApi';
import {DEFAULT_BLOCKED_APPS} from '../utils/defaultBlockedApps';

export default function BlockedAppsScreen({navigate}) {
  const [apps, setApps] = useState([]);
  const [blocked, setBlocked] = useState(new Set());
  const [enabled, setEnabled] = useState(true);
  const [hasPermission, setHasPermission] = useState(false);
  const [loading, setLoading] = useState(true);

  const checkPermission = useCallback(() => {
    hasUsageStatsPermission()
      .then(p => setHasPermission(p))
      .catch(() => {});
  }, []);

  useEffect(() => {
    Promise.all([
      getInstalledApps(),
      getBlockedApps(),
      isBlockingEnabled(),
      hasUsageStatsPermission(),
    ])
      .then(([appList, blockedList, blockOn, perm]) => {
        setApps(appList.sort((a, b) => a.appName.localeCompare(b.appName)));
        setBlocked(new Set(blockedList));
        setEnabled(blockOn);
        setHasPermission(perm);
        setLoading(false);
      })
      .catch(() => setLoading(false));

    const sub = AppState.addEventListener('change', state => {
      if (state === 'active') checkPermission();
    });
    return () => sub.remove();
  }, [checkPermission]);

  const toggleApp = useCallback(
    async pkg => {
      const next = new Set(blocked);
      if (next.has(pkg)) next.delete(pkg);
      else next.add(pkg);
      setBlocked(next);
      await setBlockedApps([...next]);
    },
    [blocked],
  );

  const toggleEnabled = useCallback(async val => {
    setEnabled(val);
    await setBlockingEnabled(val);
  }, []);

  const blockDefaults = useCallback(async () => {
    const installedPkgs = new Set(apps.map(a => a.packageName));
    const next = new Set(blocked);
    let added = 0;
    DEFAULT_BLOCKED_APPS.forEach(pkg => {
      if (installedPkgs.has(pkg) && !next.has(pkg)) {
        next.add(pkg);
        added++;
      }
    });
    if (added === 0) {
      Alert.alert(
        'No new apps to block',
        'Either they are not installed or already blocked.',
      );
      return;
    }
    setBlocked(next);
    await setBlockedApps([...next]);
    Alert.alert(`Blocked ${added} apps`, 'Common addictive apps have been blocked.');
  }, [blocked, apps]);

  const blockedApps = apps.filter(a => blocked.has(a.packageName));
  const unblockedApps = apps.filter(a => !blocked.has(a.packageName));

  const listData = [
    ...(blockedApps.length > 0
      ? [
          {type: 'header', id: 'h1', label: `Blocked  (${blockedApps.length})`},
          ...blockedApps.map(a => ({type: 'app', ...a, isBlocked: true})),
        ]
      : []),
    {type: 'header', id: 'h2', label: 'All Apps'},
    ...unblockedApps.map(a => ({type: 'app', ...a, isBlocked: false})),
  ];

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigate('home')} style={styles.backBtn}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Block Apps</Text>
      </View>

      {!hasPermission && (
        <TouchableOpacity
          style={styles.permBanner}
          onPress={openUsageStatsSettings}>
          <Text style={styles.permTitle}>⚠  Permission Required</Text>
          <Text style={styles.permBody}>
            Tap to grant Usage Access — needed for app blocking to work.
          </Text>
        </TouchableOpacity>
      )}

      <View style={styles.card}>
        <View>
          <Text style={styles.cardLabel}>Blocking Enabled</Text>
          <Text style={styles.cardSub}>
            {enabled ? 'Blocked apps are intercepted' : 'Blocking is paused'}
          </Text>
        </View>
        <Switch
          value={enabled}
          onValueChange={toggleEnabled}
          trackColor={{true: '#e53935', false: '#2a2a2a'}}
          thumbColor="#fff"
        />
      </View>

      <TouchableOpacity style={styles.defaultsBtn} onPress={blockDefaults}>
        <Text style={styles.defaultsBtnText}>
          🚫  Block Common Addictive Apps
        </Text>
      </TouchableOpacity>

      {loading ? (
        <Text style={styles.loading}>Loading...</Text>
      ) : (
        <FlatList
          data={listData}
          keyExtractor={(item, i) =>
            item.type === 'header' ? item.id : item.packageName
          }
          renderItem={({item}) => {
            if (item.type === 'header') {
              return <Text style={styles.sectionHeader}>{item.label}</Text>;
            }
            return (
              <View style={styles.row}>
                <Text
                  style={[styles.appName, item.isBlocked && styles.blockedText]}
                  numberOfLines={1}>
                  {item.appName}
                </Text>
                <Switch
                  value={item.isBlocked}
                  onValueChange={() => toggleApp(item.packageName)}
                  trackColor={{true: '#e53935', false: '#2a2a2a'}}
                  thumbColor="#fff"
                />
              </View>
            );
          }}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.listContent}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: '#080808', paddingTop: 52},
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    marginBottom: 18,
  },
  backBtn: {marginRight: 14, padding: 4},
  backText: {color: '#555', fontSize: 15},
  title: {color: '#fff', fontSize: 20, fontWeight: '700'},
  permBanner: {
    backgroundColor: '#160000',
    borderColor: '#e53935',
    borderWidth: 1,
    borderRadius: 12,
    marginHorizontal: 16,
    marginBottom: 14,
    padding: 14,
  },
  permTitle: {color: '#e53935', fontWeight: '700', marginBottom: 4, fontSize: 14},
  permBody: {color: '#888', fontSize: 13, lineHeight: 18},
  card: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#141414',
    marginHorizontal: 16,
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
  },
  cardLabel: {color: '#fff', fontSize: 16, fontWeight: '600'},
  cardSub: {color: '#555', fontSize: 12, marginTop: 3},
  defaultsBtn: {
    backgroundColor: '#160000',
    borderRadius: 12,
    marginHorizontal: 16,
    padding: 14,
    marginBottom: 18,
    alignItems: 'center',
  },
  defaultsBtnText: {color: '#e53935', fontSize: 14, fontWeight: '600'},
  loading: {color: '#444', textAlign: 'center', marginTop: 48},
  listContent: {paddingBottom: 40},
  sectionHeader: {
    color: '#333',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    paddingHorizontal: 20,
    paddingTop: 18,
    paddingBottom: 8,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 9,
  },
  appName: {color: '#fff', fontSize: 15, flex: 1, marginRight: 12},
  blockedText: {color: '#e53935'},
});
