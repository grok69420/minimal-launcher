import React, {useState, useEffect, useRef, useCallback} from 'react';
import {View, Text, TouchableOpacity, StyleSheet, Animated} from 'react-native';
import {colors, radius} from '../theme';

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', '⌫'];
const PIN_LENGTH = 4;

export default function PinPad({title, subtitle, error, onComplete, resetSignal}) {
  const [digits, setDigits] = useState('');
  const shake = useRef(new Animated.Value(0)).current;

  // Clear the entry whenever the parent bumps resetSignal (e.g. wrong PIN).
  useEffect(() => {
    setDigits('');
  }, [resetSignal]);

  useEffect(() => {
    if (error) {
      Animated.sequence([
        Animated.timing(shake, {toValue: 10, duration: 50, useNativeDriver: true}),
        Animated.timing(shake, {toValue: -10, duration: 50, useNativeDriver: true}),
        Animated.timing(shake, {toValue: 6, duration: 50, useNativeDriver: true}),
        Animated.timing(shake, {toValue: 0, duration: 50, useNativeDriver: true}),
      ]).start();
    }
  }, [error, shake, resetSignal]);

  const press = useCallback(
    key => {
      if (key === '⌫') {
        setDigits(d => d.slice(0, -1));
        return;
      }
      if (key === '') return;
      setDigits(d => {
        if (d.length >= PIN_LENGTH) return d;
        const next = d + key;
        if (next.length === PIN_LENGTH) {
          // Defer so the last dot renders before the parent reacts.
          setTimeout(() => onComplete(next), 80);
        }
        return next;
      });
    },
    [onComplete],
  );

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>{title}</Text>
      {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}

      <Animated.View style={[styles.dots, {transform: [{translateX: shake}]}]}>
        {Array.from({length: PIN_LENGTH}).map((_, i) => (
          <View
            key={i}
            style={[
              styles.dot,
              i < digits.length && styles.dotFilled,
              error && styles.dotError,
            ]}
          />
        ))}
      </Animated.View>

      <Text style={styles.error}>{error || ' '}</Text>

      <View style={styles.pad}>
        {KEYS.map((key, i) => (
          <TouchableOpacity
            key={i}
            activeOpacity={key ? 0.6 : 1}
            style={styles.key}
            onPress={() => press(key)}>
            <Text style={styles.keyText}>{key}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {alignItems: 'center', width: '100%'},
  title: {color: colors.text, fontSize: 22, fontWeight: '700'},
  subtitle: {color: colors.textDim, fontSize: 14, marginTop: 8, textAlign: 'center'},
  dots: {flexDirection: 'row', marginTop: 32},
  dot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 1.5,
    borderColor: colors.textFaint,
    marginHorizontal: 10,
  },
  dotFilled: {backgroundColor: colors.accent, borderColor: colors.accent},
  dotError: {borderColor: colors.danger},
  error: {color: colors.danger, fontSize: 13, marginTop: 14, height: 18},
  pad: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    width: 280,
    justifyContent: 'space-between',
    marginTop: 12,
  },
  key: {
    width: 80,
    height: 72,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  keyText: {color: colors.text, fontSize: 28, fontWeight: '400'},
});
