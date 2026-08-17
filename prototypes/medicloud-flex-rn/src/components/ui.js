import React from 'react';
import {View, Text, StyleSheet, Pressable} from 'react-native';
import {C, TAG} from '../theme';

/* A provenance chip. Per the briefing (Part I3), the point is not to win an argument about
   whether a number is real, but to have already made clear what kind of number it is. */
export function Tag({name, style}) {
  const t = TAG[name];
  if (!t) return null;
  return (
    <View style={[s.tag, {backgroundColor: t.bg}, style]}>
      <Text style={[s.tagText, {color: t.color}]}>{t.label}</Text>
    </View>
  );
}

export function Card({children, style}) {
  return <View style={[s.card, style]}>{children}</View>;
}

export function SectionTitle({children, style}) {
  return <Text style={[s.sectionTitle, style]}>{children}</Text>;
}

export function Muted({children, style}) {
  return <Text style={[s.muted, style]}>{children}</Text>;
}

export function Button({label, onPress, disabled, variant = 'dark', style}) {
  const bg = disabled ? C.border : variant === 'teal' ? C.teal : C.ink;
  return (
    <Pressable
      onPress={disabled ? undefined : onPress}
      accessibilityRole="button"
      accessibilityState={{disabled: !!disabled}}
      style={({pressed}) => [
        s.btn,
        {backgroundColor: bg, opacity: pressed && !disabled ? 0.85 : 1},
        style,
      ]}>
      <Text style={[s.btnText, disabled && {color: C.slate}]}>{label}</Text>
    </Pressable>
  );
}

/* Allowance as a blister-pack strip — one capsule per S$25 of the account. */
export function BlisterStrip({used, total}) {
  const cells = Math.round(total / 25);
  const spent = Math.round(used / 25);
  return (
    <View style={s.strip}>
      {Array.from({length: cells}).map((_, i) => (
        <View
          key={i}
          style={[
            s.pill,
            i < spent
              ? {backgroundColor: C.border, borderColor: C.border}
              : {backgroundColor: C.mint, borderColor: C.teal},
          ]}
        />
      ))}
    </View>
  );
}

export function Bar({pct, color = C.teal, track = C.lineSoft, height = 8}) {
  const w = Math.max(0, Math.min(100, pct));
  return (
    <View style={{height, borderRadius: 999, backgroundColor: track, overflow: 'hidden'}}>
      <View style={{height, borderRadius: 999, width: `${w}%`, backgroundColor: color}} />
    </View>
  );
}

export function Row({label, value, bold, valueColor}) {
  return (
    <View style={s.row}>
      <Text style={s.rowLabel}>{label}</Text>
      <Text style={[s.rowValue, bold && {fontWeight: '700'}, valueColor && {color: valueColor}]}>
        {value}
      </Text>
    </View>
  );
}

/* RN has no icon library here, so glyphs are drawn from primitives — keeps the app
   dependency-free rather than pulling in a vector-icon package and its font assets. */
export function ClinicGlyph({kind, size = 20, color = C.teal}) {
  if (kind === 'dental') {
    return (
      <View style={{width: size, height: size, alignItems: 'center', justifyContent: 'center'}}>
        <View style={{width: size * 0.8, height: size * 0.55, borderTopLeftRadius: size * 0.4,
          borderTopRightRadius: size * 0.4, borderWidth: 2, borderBottomWidth: 0, borderColor: color}} />
        <View style={{flexDirection: 'row', gap: size * 0.16}}>
          <View style={{width: 2, height: size * 0.26, backgroundColor: color, borderRadius: 1}} />
          <View style={{width: 2, height: size * 0.26, backgroundColor: color, borderRadius: 1}} />
        </View>
      </View>
    );
  }
  // GP: a cross
  return (
    <View style={{width: size, height: size, alignItems: 'center', justifyContent: 'center'}}>
      <View style={{position: 'absolute', width: size * 0.8, height: size * 0.26,
        backgroundColor: color, borderRadius: 2}} />
      <View style={{position: 'absolute', width: size * 0.26, height: size * 0.8,
        backgroundColor: color, borderRadius: 2}} />
    </View>
  );
}

/* Deterministic placeholder QR — the same seed always draws the same pattern. */
export function FakeQR({seed = 'medicloud', cell = 12}) {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  const cells = [];
  for (let i = 0; i < 121; i++) {
    h = (Math.imul(h, 1103515245) + 12345 + i) >>> 0;
    cells.push((h >>> 16) % 2 === 0);
  }
  return (
    <View style={[s.qrWrap, {width: cell * 11 + 24}]}>
      <View style={s.qrGrid}>
        {cells.map((on, i) => (
          <View key={i} style={{width: cell, height: cell, borderRadius: 2,
            backgroundColor: on ? C.ink : 'transparent'}} />
        ))}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  tag: {paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, alignSelf: 'flex-start'},
  tagText: {fontSize: 9, fontWeight: '800', letterSpacing: 0.6},
  card: {backgroundColor: C.bg, borderRadius: 16, padding: 16},
  sectionTitle: {fontSize: 14, fontWeight: '700', color: C.ink, marginBottom: 8},
  muted: {fontSize: 12, color: C.slate, lineHeight: 17},
  btn: {borderRadius: 12, paddingVertical: 13, alignItems: 'center', justifyContent: 'center'},
  btnText: {color: C.white, fontWeight: '600', fontSize: 14},
  strip: {flexDirection: 'row', flexWrap: 'wrap', gap: 6},
  pill: {width: '8.2%', height: 22, borderRadius: 999, borderWidth: 1},
  row: {flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3},
  rowLabel: {fontSize: 13, color: C.slate, flexShrink: 1, paddingRight: 8},
  rowValue: {fontSize: 13, color: C.ink, fontWeight: '500'},
  qrWrap: {padding: 12, borderRadius: 16, borderWidth: 1, borderColor: C.border,
    backgroundColor: C.white},
  qrGrid: {flexDirection: 'row', flexWrap: 'wrap', gap: 2},
});
