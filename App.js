import React, {useState} from 'react';
import {StyleSheet, View} from 'react-native';
import HomeScreen from './src/screens/HomeScreen';
import AppDrawerScreen from './src/screens/AppDrawerScreen';
import BlockedAppsScreen from './src/screens/BlockedAppsScreen';

export default function App() {
  const [screen, setScreen] = useState('home');
  const navigate = s => setScreen(s);

  return (
    <View style={styles.root}>
      {screen === 'home' && <HomeScreen navigate={navigate} />}
      {screen === 'drawer' && <AppDrawerScreen navigate={navigate} />}
      {screen === 'blocked' && <BlockedAppsScreen navigate={navigate} />}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: '#000'},
});
