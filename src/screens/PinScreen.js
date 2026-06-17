import React, {useState, useCallback} from 'react';
import {View, Text, TouchableOpacity, StyleSheet} from 'react-native';
import PinPad from '../components/PinPad';
import {colors} from '../theme';
import {verifyPin, setPin} from '../utils/nativeApi';

/**
 * mode = 'verify'  -> confirm the existing PIN, then onSuccess()
 * mode = 'set'     -> choose + confirm a new PIN, store it, then onSuccess()
 */
export default function PinScreen({mode, onSuccess, onCancel}) {
  const [error, setError] = useState('');
  const [reset, setReset] = useState(0);
  const [firstEntry, setFirstEntry] = useState(null); // for 'set' confirm step

  const bump = () => setReset(r => r + 1);

  const handleVerify = useCallback(
    async pin => {
      const ok = await verifyPin(pin).catch(() => false);
      if (ok) {
        setError('');
        onSuccess();
      } else {
        setError('Incorrect PIN');
        bump();
      }
    },
    [onSuccess],
  );

  const handleSet = useCallback(
    async pin => {
      if (firstEntry === null) {
        setFirstEntry(pin);
        setError('');
        bump();
        return;
      }
      if (pin !== firstEntry) {
        setError('PINs did not match');
        setFirstEntry(null);
        bump();
        return;
      }
      await setPin(pin).catch(() => {});
      setError('');
      onSuccess();
    },
    [firstEntry, onSuccess],
  );

  let title;
  let subtitle;
  if (mode === 'set') {
    title = firstEntry === null ? 'Create a PIN' : 'Confirm your PIN';
    subtitle =
      firstEntry === null
        ? 'This protects your blocklist from impulsive changes.'
        : 'Enter the same 4 digits again.';
  } else {
    title = 'Enter your PIN';
    subtitle = 'Unlock to manage blocked apps.';
  }

  return (
    <View style={styles.container}>
      <View style={styles.center}>
        <Text style={styles.lock}>🔒</Text>
        <PinPad
          title={title}
          subtitle={subtitle}
          error={error}
          resetSignal={reset}
          onComplete={mode === 'set' ? handleSet : handleVerify}
        />
      </View>

      {onCancel ? (
        <TouchableOpacity style={styles.cancel} onPress={onCancel}>
          <Text style={styles.cancelText}>Cancel</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: colors.bg, paddingTop: 60, paddingBottom: 30},
  center: {flex: 1, alignItems: 'center', justifyContent: 'center'},
  lock: {fontSize: 40, marginBottom: 12},
  cancel: {alignItems: 'center', padding: 16},
  cancelText: {color: colors.textDim, fontSize: 15},
});
