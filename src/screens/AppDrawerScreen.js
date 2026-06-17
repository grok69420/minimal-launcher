import React, {useState, useEffect, useCallback, useRef} from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  Alert,
  PanResponder,
} from 'react-native';
import {
  getInstalledApps,
  getBlockedApps,
  setBlockedApps,
  launchApp,
} from '../utils/nativeApi';
import {colors, radius, badgeColor} from '../theme';

function AppBadge({name}) {
  return (
    <View style={[styles.badge, {backgroundColor: badgeColor(name)}]}>
      <Text style={styles.badgeLetter}>{(name[0] || '?').toUpperCase()}</Text>
    </View>
  );
}

export default function AppDrawerScreen({navigate}) {
  const [apps, setApps] = useState([]);
  const [blocked, setBlocked] = useState(new Set());
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getInstalledApps(), getBlockedApps()])
      .then(([appList, blockedList]) => {
        setApps(appList.sort((a, b) => a.appName.localeCompare(b.appName)));
        setBlocked(new Set(blockedList));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const filtered = search
    ? apps.filter(a => a.appName.toLowerCase().includes(search.toLowerCase()))
    : apps;

  const toggleBlock = useCallback(
    app => {
      const isBlocked = blocked.has(app.packageName);
      Alert.alert(
        app.appName,
        isBlocked
          ? 'Unblock this app?'
          : 'Block this app? It will be intercepted whenever you open it.',
        [
          {
            text: isBlocked ? 'Unblock' : 'Block',
            style: isBlocked ? 'default' : 'destructive',
            onPress: async () => {
              const next = new Set(blocked);
              if (isBlocked) next.delete(app.packageName);
              else next.add(app.packageName);
              setBlocked(next);
              await setBlockedApps([...next]);
            },
          },
          {text: 'Cancel', style: 'cancel'},
        ],
      );
    },
    [blocked],
  );

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) =>
        Math.abs(g.dy) > 15 && Math.abs(g.dy) > Math.abs(g.dx),
      onPanResponderRelease: (_, g) => {
        if (g.dy > 80) navigate('home');
      },
    }),
  ).current;

  const renderItem = useCallback(
    ({item}) => {
      const isBlocked = blocked.has(item.packageName);
      return (
        <TouchableOpacity
          style={styles.row}
          activeOpacity={0.6}
          onPress={() => {
            if (isBlocked) {
              Alert.alert(
                'App blocked',
                `${item.appName} is blocked. Open the Blocklist to allow it again.`,
              );
            } else {
              launchApp(item.packageName).catch(() => {});
            }
          }}
          onLongPress={() => toggleBlock(item)}>
          <AppBadge name={item.appName} />
          <Text style={[styles.appName, isBlocked && styles.blockedText]}>
            {item.appName}
          </Text>
          {isBlocked && (
            <View style={styles.blockedTag}>
              <Text style={styles.blockedTagText}>BLOCKED</Text>
            </View>
          )}
        </TouchableOpacity>
      );
    },
    [blocked, toggleBlock],
  );

  return (
    <View style={styles.container} {...pan.panHandlers}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigate('home')} style={styles.backBtn}>
          <Text style={styles.backText}>↓  Home</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => navigate('blocked')}>
          <Text style={styles.manageText}>Manage blocklist</Text>
        </TouchableOpacity>
      </View>

      <TextInput
        style={styles.search}
        placeholder="Search apps…"
        placeholderTextColor={colors.textFaint}
        value={search}
        onChangeText={setSearch}
        autoCorrect={false}
        autoCapitalize="none"
      />

      <Text style={styles.hint}>Long-press an app to block or unblock it</Text>

      {loading ? (
        <Text style={styles.loading}>Loading apps…</Text>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={item => item.packageName}
          renderItem={renderItem}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.list}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: colors.bg, paddingTop: 56},
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    marginBottom: 14,
  },
  backBtn: {padding: 6},
  backText: {color: colors.textDim, fontSize: 14},
  manageText: {color: colors.accent, fontSize: 13, padding: 6, fontWeight: '600'},
  search: {
    backgroundColor: colors.card,
    color: colors.text,
    marginHorizontal: 16,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 16,
    paddingVertical: 11,
    fontSize: 15,
  },
  hint: {
    color: colors.textFaint,
    fontSize: 11,
    paddingHorizontal: 22,
    paddingTop: 10,
    paddingBottom: 2,
  },
  loading: {color: colors.textDim, textAlign: 'center', marginTop: 48, fontSize: 14},
  list: {paddingBottom: 32, paddingTop: 6},
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 9,
  },
  badge: {
    width: 42,
    height: 42,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  badgeLetter: {color: '#fff', fontSize: 18, fontWeight: '700'},
  appName: {color: colors.text, fontSize: 16, flex: 1},
  blockedText: {color: colors.textFaint},
  blockedTag: {
    backgroundColor: '#2A0E18',
    borderRadius: radius.sm,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  blockedTagText: {
    color: colors.danger,
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
});
