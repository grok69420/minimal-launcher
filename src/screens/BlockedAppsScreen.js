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
  getPermissionStatus,
  hasPin,
  clearPin,
} from '../utils/nativeApi';
import {DEFAULT_BLOCKED_APPS} from '../utils/defaultBlockedApps';
import {colors, radius} from '../theme';

export default function BlockedAppsScreen({navigate}) {
  const [apps, setApps] = useState([]);
  const [blocked, setBlocked] = useState(new Set());
  const [enabled, setEnabled] = useState(true);
  const [coreReady, setCoreReady] = useState(true);
  const [pinSet, setPinSet] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadAll = useCallback(() => {
    Promise.all([
      getInstalledApps(),
      getBlockedApps(),
      isBlockingEnabled(),
      getPermissionStatus(),
      hasPin(),
    ])
      .then(([appList, blockedList, blockOn, perm, pin]) => {
        setApps(appList.sort((a, b) => a.appName.localeCompare(b.appName)));
        setBlocked(new Set(blockedList));
        setEnabled(blockOn);
        setCoreReady(!!(perm.usageStats && perm.overlay));
        setPinSet(pin);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadAll();
    const sub = AppState.addEventListener('change', state => {
      if (state === 'active') loadAll();
    });
    return () => sub.remove();
  }, [loadAll]);

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
        'Nothing to add',
        'The common distracting apps are either not installed or already blocked.',
      );
      return;
    }
    setBlocked(next);
    await setBlockedApps([...next]);
    Alert.alert(`Blocked ${added} app${added > 1 ? 's' : ''}`, 'Common distracting apps are now blocked.');
  }, [blocked, apps]);

  const handlePinAction = useCallback(() => {
    if (pinSet) {
      Alert.alert('Remove PIN lock?', 'Your blocklist will no longer be protected.', [
        {
          text: 'Remove',
          style: 'destructive',
          onPress: async () => {
            await clearPin().catch(() => {});
            setPinSet(false);
          },
        },
        {text: 'Cancel', style: 'cancel'},
      ]);
    } else {
      navigate('pinSet');
    }
  }, [pinSet, navigate]);

  const blockedApps = apps.filter(a => blocked.has(a.packageName));
  const unblockedApps = apps.filter(a => !blocked.has(a.packageName));

  const listData = [
    ...(blockedApps.length > 0
      ? [
          {type: 'header', id: 'h1', label: `Blocked  (${blockedApps.length})`},
          ...blockedApps.map(a => ({type: 'app', ...a, isBlocked: true})),
        ]
      : []),
    {type: 'header', id: 'h2', label: 'All apps'},
    ...unblockedApps.map(a => ({type: 'app', ...a, isBlocked: false})),
  ];

  const ListHeader = (
    <View>
      {!coreReady && (
        <TouchableOpacity
          style={styles.permBanner}
          onPress={() => navigate('permissions')}>
          <Text style={styles.permTitle}>⚠️  Blocking is inactive</Text>
          <Text style={styles.permBody}>
            Tap to grant the permissions blocking needs to work.
          </Text>
        </TouchableOpacity>
      )}

      <View style={styles.card}>
        <View style={styles.cardTextWrap}>
          <Text style={styles.cardLabel}>Blocking enabled</Text>
          <Text style={styles.cardSub}>
            {enabled ? 'Blocked apps are intercepted' : 'Blocking is paused'}
          </Text>
        </View>
        <Switch
          value={enabled}
          onValueChange={toggleEnabled}
          trackColor={{true: colors.accent, false: colors.border}}
          thumbColor="#fff"
        />
      </View>

      <TouchableOpacity
        style={styles.card}
        activeOpacity={0.7}
        onPress={handlePinAction}>
        <View style={styles.cardTextWrap}>
          <Text style={styles.cardLabel}>
            {pinSet ? '🔒  PIN lock is on' : '🔓  Set up PIN lock'}
          </Text>
          <Text style={styles.cardSub}>
            {pinSet
              ? 'Tap to remove protection'
              : 'Protect this screen from impulsive changes'}
          </Text>
        </View>
        <Text style={styles.chevron}>›</Text>
      </TouchableOpacity>

      <TouchableOpacity style={styles.defaultsBtn} onPress={blockDefaults}>
        <Text style={styles.defaultsBtnText}>🛡️  Block common distracting apps</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigate('home')} style={styles.backBtn}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Blocklist</Text>
      </View>

      {loading ? (
        <Text style={styles.loading}>Loading…</Text>
      ) : (
        <FlatList
          data={listData}
          ListHeaderComponent={ListHeader}
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
                  trackColor={{true: colors.accent, false: colors.border}}
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
  container: {flex: 1, backgroundColor: colors.bg, paddingTop: 56},
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    marginBottom: 16,
  },
  backBtn: {marginRight: 14, padding: 4},
  backText: {color: colors.textDim, fontSize: 15},
  title: {color: colors.text, fontSize: 22, fontWeight: '700'},
  permBanner: {
    backgroundColor: '#1F1A0A',
    borderColor: colors.warn,
    borderWidth: 1,
    borderRadius: radius.md,
    marginHorizontal: 16,
    marginBottom: 14,
    padding: 14,
  },
  permTitle: {color: colors.warn, fontWeight: '700', marginBottom: 4, fontSize: 14},
  permBody: {color: colors.textDim, fontSize: 13, lineHeight: 18},
  card: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    marginHorizontal: 16,
    borderRadius: radius.md,
    padding: 16,
    marginBottom: 12,
  },
  cardTextWrap: {flex: 1, marginRight: 12},
  cardLabel: {color: colors.text, fontSize: 16, fontWeight: '600'},
  cardSub: {color: colors.textDim, fontSize: 12, marginTop: 3},
  chevron: {color: colors.textFaint, fontSize: 24, fontWeight: '300'},
  defaultsBtn: {
    backgroundColor: colors.cardActive,
    borderColor: colors.accent,
    borderWidth: 1,
    borderRadius: radius.md,
    marginHorizontal: 16,
    padding: 14,
    marginBottom: 18,
    alignItems: 'center',
  },
  defaultsBtnText: {color: colors.accent, fontSize: 14, fontWeight: '700'},
  loading: {color: colors.textDim, textAlign: 'center', marginTop: 48},
  listContent: {paddingBottom: 40},
  sectionHeader: {
    color: colors.textFaint,
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
  appName: {color: colors.text, fontSize: 15, flex: 1, marginRight: 12},
  blockedText: {color: colors.danger},
});
