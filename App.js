import React, {useState, useEffect, useCallback} from 'react';
import {StyleSheet, View, StatusBar} from 'react-native';
import HomeScreen from './src/screens/HomeScreen';
import AppDrawerScreen from './src/screens/AppDrawerScreen';
import BlockedAppsScreen from './src/screens/BlockedAppsScreen';
import PermissionsScreen from './src/screens/PermissionsScreen';
import PinScreen from './src/screens/PinScreen';
import FadeInView from './src/components/FadeInView';
import {colors} from './src/theme';
import {
  hasPin,
  getPermissionStatus,
  startBlockerService,
} from './src/utils/nativeApi';

export default function App() {
  const [screen, setScreen] = useState('home');
  const [pendingAfterPin, setPendingAfterPin] = useState('blocked');

  // Start the blocker as soon as the launcher opens, if it's allowed to run.
  useEffect(() => {
    getPermissionStatus()
      .then(s => {
        if (s.usageStats && s.overlay) startBlockerService().catch(() => {});
      })
      .catch(() => {});
  }, []);

  // Navigation with a PIN gate in front of the blocklist.
  const navigate = useCallback(async target => {
    if (target === 'blocked') {
      const locked = await hasPin().catch(() => false);
      if (locked) {
        setPendingAfterPin('blocked');
        setScreen('pinVerify');
        return;
      }
    }
    setScreen(target);
  }, []);

  let content;
  if (screen === 'home') content = <HomeScreen navigate={navigate} />;
  else if (screen === 'drawer') content = <AppDrawerScreen navigate={navigate} />;
  else if (screen === 'blocked') content = <BlockedAppsScreen navigate={navigate} />;
  else if (screen === 'permissions')
    content = <PermissionsScreen navigate={navigate} />;
  else if (screen === 'pinVerify')
    content = (
      <PinScreen
        mode="verify"
        onSuccess={() => setScreen(pendingAfterPin)}
        onCancel={() => setScreen('home')}
      />
    );
  else if (screen === 'pinSet')
    content = (
      <PinScreen
        mode="set"
        onSuccess={() => setScreen('blocked')}
        onCancel={() => setScreen('blocked')}
      />
    );

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" backgroundColor={colors.bg} />
      <FadeInView key={screen} style={styles.fill}>
        {content}
      </FadeInView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.bg},
  fill: {flex: 1},
});
