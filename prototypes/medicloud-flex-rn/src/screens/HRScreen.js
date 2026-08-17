import React from 'react';
import {View, Text, StyleSheet, ScrollView} from 'react-native';
import {C} from '../theme';
import {ACCOUNT, DISTRICTS, FIGURES, METRICS, KILL_CRITERION} from '../data/caseData';
import {Card, SectionTitle, Muted, Bar, Tag, Row} from '../components/ui';

export function HRScreen() {
  const perEmployee = ACCOUNT.annual;
  const policyMid = (FIGURES.entryPolicy.lo + FIGURES.entryPolicy.hi) / 2; // 1250
  const saving = (policyMid - perEmployee) * ACCOUNT.headcount;

  const categories = [
    {label: 'GP', pct: 46, amt: 8740},
    {label: 'Dental', pct: 31, amt: 5890},
    {label: 'Wellness', pct: 14, amt: 2660},
    {label: 'Unused', pct: 9, amt: 1710},
  ];

  return (
    <ScrollView contentContainerStyle={st.pad}>
      <View style={st.hero}>
        <Text style={st.heroLabel}>VERSUS A GROUP OUTPATIENT POLICY</Text>
        <Text style={st.heroAmount}>S${saving.toLocaleString()}</Text>
        <Text style={st.heroSub}>
          avoided this plan year across {ACCOUNT.headcount} employees
        </Text>

        <View style={{marginTop: 16, gap: 10}}>
          <CostBar label="Entry policy (case midpoint)" value={`S$${policyMid} / employee`}
            pct={100} color={C.inkSoft} />
          <CostBar label="Medicloud Flex" value={`S$${perEmployee} / employee`}
            pct={(perEmployee / policyMid) * 100} color={C.teal} />
        </View>

        <View style={st.heroTagRow}>
          <Tag name="ARITHMETIC" />
          <Text style={st.heroNote}>
            (S${policyMid} − S${perEmployee}) × {ACCOUNT.headcount}. The S${policyMid} is the
            midpoint of the case's S${FIGURES.entryPolicy.lo}–{FIGURES.entryPolicy.hi} entry-policy band.
          </Text>
        </View>
        <View style={st.heroTagRow}>
          <Tag name="ANALYSIS" />
          <Text style={st.heroNote}>
            Not a like-for-like saving: an entry policy includes hospitalisation cover this
            does not replace. It is avoided outpatient spend, not equivalent cover.
          </Text>
        </View>
      </View>

      <SectionTitle style={{marginTop: 20}}>Metrics that decide whether this works</SectionTitle>
      <Card>
        {METRICS.map(m => <Row key={m.label} label={m.label} value={m.value} />)}
      </Card>

      <SectionTitle style={{marginTop: 20}}>Clinic density by district</SectionTitle>
      <Muted style={{marginBottom: 10}}>
        Recommendation 1: take the panel from {FIGURES.clinics.value} to 150+ clinics
        clustered in SME-heavy districts before selling hard.
      </Muted>
      {DISTRICTS.map(d => (
        <View key={d.id} style={{marginBottom: 12}}>
          <View style={st.barHead}>
            <Text style={st.barLabel}>{d.name}</Text>
            <Muted>{d.live} live / {d.target} target</Muted>
          </View>
          <Bar pct={(d.live / d.target) * 100} />
        </View>
      ))}

      <SectionTitle style={{marginTop: 12}}>Where the benefit goes</SectionTitle>
      {categories.map(b => (
        <View key={b.label} style={{marginBottom: 12}}>
          <View style={st.barHead}>
            <Text style={st.barLabel}>{b.label}</Text>
            <Muted>S${b.amt.toLocaleString()}</Muted>
          </View>
          <Bar pct={b.pct} color={b.label === 'Unused' ? C.border : C.teal} />
        </View>
      ))}

      {/* Parts E2 / F2: an employer dashboard naming which employee used which clinic is a
          consent and confidentiality problem regardless of statute. */}
      <Card style={{marginTop: 8, backgroundColor: C.mint}}>
        <Text style={st.cardTitle}>Why you cannot see individuals here</Text>
        <Muted>
          This dashboard reports aggregates only. Employer-visible utilisation tied to a named
          employee is a consent and confidentiality problem regardless of statute, so the
          product does not offer it — categories and totals, never who went where.
        </Muted>
        <View style={st.tagRow}>
          <Tag name="ANALYSIS" />
          <Tag name="VERIFY" />
        </View>
        <Muted style={{marginTop: 6}}>
          Applicable data regime (PDPA) and its requirements for health data still need
          confirming from a primary source.
        </Muted>
      </Card>

      <Card style={{marginTop: 12, borderWidth: 1, borderColor: C.line, backgroundColor: C.white}}>
        <Text style={st.cardTitle}>Guardrail — when to abandon this</Text>
        <Muted>{KILL_CRITERION}</Muted>
      </Card>
    </ScrollView>
  );
}

function CostBar({label, value, pct, color}) {
  return (
    <View>
      <View style={st.barHead}>
        <Text style={st.heroBarLabel}>{label}</Text>
        <Text style={st.heroBarLabel}>{value}</Text>
      </View>
      <Bar pct={pct} color={color} track="rgba(255,255,255,0.14)" height={10} />
    </View>
  );
}

const st = StyleSheet.create({
  pad: {padding: 20, paddingBottom: 40},
  hero: {backgroundColor: C.ink, borderRadius: 16, padding: 18},
  heroLabel: {fontSize: 10, letterSpacing: 1.4, color: C.mint, fontWeight: '700'},
  heroAmount: {fontSize: 30, fontWeight: '700', color: C.white, marginTop: 8},
  heroSub: {fontSize: 12, color: C.onInk, marginTop: 4},
  heroTagRow: {flexDirection: 'row', gap: 8, marginTop: 12, alignItems: 'flex-start'},
  heroNote: {flex: 1, fontSize: 11, color: C.onInk, lineHeight: 16},
  heroBarLabel: {fontSize: 11, color: C.onInk},
  barHead: {flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5},
  barLabel: {fontSize: 13, color: C.ink, fontWeight: '600'},
  cardTitle: {fontSize: 13, fontWeight: '700', color: C.ink, marginBottom: 6},
  tagRow: {flexDirection: 'row', gap: 8, marginTop: 8},
});
