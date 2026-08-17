import React, {useState} from 'react';
import {View, Text, StyleSheet, ScrollView, Pressable} from 'react-native';
import {C, TAG} from '../theme';
import {FIGURES, STRUCTURES, COMPETITORS, COMMISSION_PCT} from '../data/caseData';
import {Card, SectionTitle, Muted, Bar, Tag, Row} from '../components/ui';

/* The defence screen. The pre-build briefing's point is that a group wins the Q and A by
   having already conceded the fair attacks and named the structure, not by arguing. This
   screen puts each attack next to what the prototype actually does about it. */
export function CaseScreen() {
  const [tab, setTab] = useState('structure');
  return (
    <View style={{flex: 1}}>
      <View style={st.tabs}>
        {[['structure', 'Structure'], ['economics', 'Economics'], ['attacks', 'Attacks']].map(([id, label]) => (
          <Pressable key={id} onPress={() => setTab(id)}
            style={[st.tab, tab === id && st.tabActive]}>
            <Text style={[st.tabText, tab === id && {color: C.ink, fontWeight: '700'}]}>{label}</Text>
          </Pressable>
        ))}
      </View>
      <ScrollView contentContainerStyle={st.pad}>
        {tab === 'structure' ? <Structure /> : tab === 'economics' ? <Economics /> : <Attacks />}
      </ScrollView>
    </View>
  );
}

function Structure() {
  return (
    <>
      <Text style={st.h1}>Is this insurance?</Text>
      <Muted style={{marginBottom: 14}}>
        The question that decides Option B. If a business takes a fixed periodic payment and
        in exchange bears the uncertain cost of future events, it is bearing risk — and that
        is what insurance regulation governs. Two structures fit "bypass insurance"; only one
        stays outside the perimeter.
      </Muted>

      {STRUCTURES.map(s => (
        <Card key={s.id} style={[st.structure, s.chosen
          ? {borderColor: C.teal, backgroundColor: C.mint}
          : {borderColor: C.border, backgroundColor: C.white}]}>
          <View style={st.structureHead}>
            <Text style={st.structureName}>{s.name}</Text>
            <View style={[st.pickPill, {backgroundColor: s.chosen ? C.teal : C.border}]}>
              <Text style={[st.pickText, {color: s.chosen ? C.white : C.slate}]}>
                {s.chosen ? 'BUILT' : 'REJECTED'}
              </Text>
            </View>
          </View>
          <Muted style={{marginTop: 6}}>{s.mechanics}</Muted>
          <Text style={st.riskLine}>{s.risk}</Text>
          <Muted style={{marginTop: 6, fontWeight: '600', color: C.ink}}>{s.verdict}</Muted>
          <View style={{marginTop: 8}}><Tag name={s.tag} /></View>
        </Card>
      ))}

      <Card style={{marginTop: 4, backgroundColor: C.bg}}>
        <Text style={st.cardTitle}>Why this screen exists</Text>
        <Muted>
          The membership analogy that inspired Option B is the rejected structure. A slide
          saying "subscription" without specifying who bears cost risk invites the question of
          whether an unlicensed start-up has just been told to write insurance. Naming the
          structure removes the attack.
        </Muted>
      </Card>
    </>
  );
}

function Economics() {
  const tpa = FIGURES.tpaTake.value;             // 40 of 100
  const care = 100 - tpa;                        // 60 delivered as care
  const mc = COMMISSION_PCT;                     // 10
  return (
    <>
      <Text style={st.h1}>The S$100 visit</Text>
      <Muted style={{marginBottom: 14}}>
        Where each dollar of a clinic visit goes today, and under this model.
      </Muted>

      <Card>
        <Text style={st.cardTitle}>Today, through a TPA</Text>
        <Bar pct={tpa} color={C.rose} height={12} />
        <Row label="TPA administration fee" value={`S$${tpa}`} />
        <Row label="Delivered as care by the doctor" value={`S$${care}`} bold />
        <View style={st.tagRow}><Tag name="CASE" /></View>
        <Muted style={{marginTop: 6}}>{FIGURES.tpaTake.text}</Muted>
      </Card>

      <Card style={{marginTop: 12}}>
        <Text style={st.cardTitle}>Through Medicloud</Text>
        <Bar pct={mc} color={C.teal} height={12} />
        <Row label="Medicloud commission" value={`S$${mc}`} />
        <Row label="Retained by the clinic" value={`S$${100 - mc}`} bold />
        <View style={st.tagRow}><Tag name="ANALYSIS" /></View>
      </Card>

      {/* Part G1 #3 — the sharpest arithmetic attack available. Concede it up front. */}
      <Card style={{marginTop: 12, backgroundColor: C.mint}}>
        <Text style={st.cardTitle}>The margin pool we do not claim</Text>
        <Muted>
          It is tempting to call the whole S${care} that does not reach the doctor a margin
          pool. It is not — part of it is risk premium and claims cost, not administrative
          fat. The defensible claim is against the S${tpa} the case attributes specifically to
          TPA fees, which is administration.
        </Muted>
        <View style={st.tagRow}><Tag name="ANALYSIS" /></View>
      </Card>

      <SectionTitle style={{marginTop: 20}}>The affordability gap</SectionTitle>
      <Card>
        <GapRow label="Entry insurance policy" lo={FIGURES.entryPolicy.lo} hi={FIGURES.entryPolicy.hi} max={2000} color={C.rose} />
        <GapRow label="MNC flexi-benefit" lo={FIGURES.mncFlexi.lo} hi={FIGURES.mncFlexi.hi} max={2000} color={C.inkSoft} />
        <GapRow label="Outpatient need per worker" lo={FIGURES.outpatientAnnual.lo} hi={FIGURES.outpatientAnnual.hi} max={2000} color={C.amber} />
        <GapRow label="SME flexi-benefit" lo={FIGURES.smeFlexi.lo} hi={FIGURES.smeFlexi.hi} max={2000} color={C.teal} />
        <View style={st.tagRow}><Tag name="CASE" /></View>
        <Muted style={{marginTop: 6}}>
          An entry policy costs roughly three times what an SME allocates. Actual outpatient
          need sits close to what SMEs already budget — which is why the product is priced
          into the budget rather than against the policy.
        </Muted>
      </Card>

      <SectionTitle style={{marginTop: 20}}>What the first two years cost</SectionTitle>
      <Card>
        <Row label="Outsourced development" value={`S$${FIGURES.devSpend.value.toLocaleString()}`} />
        <Row label="Salaries, 24 months" value="S$360,000" />
        <Row label="Identified spend" value={`S$${FIGURES.twoYearSpend.value.toLocaleString()}`} bold />
        <Row label="Per clinic recruited" value={`S$${FIGURES.costPerClinic.value.toLocaleString()}`} />
        <View style={st.tagRow}><Tag name="ARITHMETIC" /></View>
        <Muted style={{marginTop: 6}}>
          The case gives no closing cash balance, so any specific runway figure would be
          invented. Order of magnitude remaining is a few hundred thousand against
          S${FIGURES.salaries.value.toLocaleString()}/month of salary alone.
        </Muted>
      </Card>
    </>
  );
}

function GapRow({label, lo, hi, max, color}) {
  const mid = (lo + hi) / 2;
  return (
    <View style={{marginBottom: 12}}>
      <View style={st.barHead}>
        <Text style={st.barLabel}>{label}</Text>
        <Muted>S${lo}–{hi}</Muted>
      </View>
      <Bar pct={(mid / max) * 100} color={color} />
    </View>
  );
}

function Attacks() {
  const items = [
    {q: 'You recommend bypassing insurance. Under what structure, and who bears the cost of an employee who consumes more care than they paid for?',
     a: 'The employee does. It is a discount panel: they pay the negotiated cost of care and Medicloud never promises to cover future cost. See the Structure tab.', kind: 'answered'},
    {q: 'Your employer dashboard shows utilisation. Whose data is that, and who consented?',
     a: 'The dashboard reports aggregates only and never names an employee. The applicable data regime still needs verifying.', kind: 'answered'},
    {q: 'You claim the S$60 that does not reach the doctor as your margin pool.',
     a: 'Conceded. Only the S$40 TPA administration slice is claimed — the rest includes risk premium and claims cost.', kind: 'conceded'},
    {q: 'SG$265 is a consumer cost-per-download. It has no bearing on a B2B pivot.',
     a: 'Conceded at once. It is evidence the old model was broken, not a forward-looking metric, and appears nowhere in the projections.', kind: 'conceded'},
    {q: 'Teo says no player occupies this segment.',
     a: 'The case contradicts him. BookDoc already sells a corporate clinic panel with an employer dashboard. The difference is degree, not a vacant segment.', kind: 'conceded'},
    {q: 'You dismissed Option A as too regulated, but it has a known licence with a known cost. Yours has unknown regulatory status. Which is the higher legal risk?',
     a: 'Regulatory ambiguity is acceptable only when the structure is deliberately chosen to sit outside the perimeter — which is why the discount-panel structure is named explicitly rather than left vague.', kind: 'answered'},
    {q: 'Who owns the code you paid three hundred thousand dollars for?',
     a: 'The case never says. If the vendor owns it, that spend bought a licence rather than an asset and the pivot economics worsen.', kind: 'open'},
  ];
  return (
    <>
      <Text style={st.h1}>Attack surface</Text>
      <Muted style={{marginBottom: 14}}>
        Conceding a fair point costs one mark; defending an indefensible one costs the room.
      </Muted>
      {items.map((it, i) => (
        <Card key={i} style={{marginBottom: 12, backgroundColor: C.white,
          borderWidth: 1, borderColor: C.line}}>
          <Text style={st.attackQ}>“{it.q}”</Text>
          <Text style={st.attackA}>{it.a}</Text>
          <View style={[st.kindPill, {backgroundColor:
            it.kind === 'conceded' ? '#FDF0D5' : it.kind === 'open' ? '#FBE6E4' : C.mint}]}>
            <Text style={[st.kindText, {color:
              it.kind === 'conceded' ? '#8A6100' : it.kind === 'open' ? C.rose : C.teal}]}>
              {it.kind === 'conceded' ? 'CONCEDE' : it.kind === 'open' ? 'UNRESOLVED' : 'ANSWER'}
            </Text>
          </View>
        </Card>
      ))}

      <SectionTitle style={{marginTop: 8}}>Competitors the case already names</SectionTitle>
      {COMPETITORS.map(c => (
        <View key={c.name} style={st.compRow}>
          <Text style={st.compName}>{c.name}</Text>
          <Muted style={{flex: 1}}>{c.note}</Muted>
        </View>
      ))}

      <SectionTitle style={{marginTop: 20}}>Reading the tags</SectionTitle>
      <Card>
        {Object.keys(TAG).map(k => (
          <View key={k} style={st.legendRow}>
            <Tag name={k} />
            <Muted style={{flex: 1}}>{TAG[k].note}</Muted>
          </View>
        ))}
      </Card>
    </>
  );
}

const st = StyleSheet.create({
  pad: {padding: 20, paddingBottom: 40},
  tabs: {flexDirection: 'row', backgroundColor: C.bg, margin: 20, marginBottom: 0,
    borderRadius: 12, padding: 4},
  tab: {flex: 1, paddingVertical: 9, alignItems: 'center', borderRadius: 9},
  tabActive: {backgroundColor: C.white},
  tabText: {fontSize: 13, color: C.slate, fontWeight: '600'},
  h1: {fontSize: 19, fontWeight: '700', color: C.ink, marginBottom: 6},
  structure: {marginBottom: 12, borderWidth: 1},
  structureHead: {flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center'},
  structureName: {fontSize: 14, fontWeight: '700', color: C.ink, flex: 1, paddingRight: 8},
  pickPill: {paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6},
  pickText: {fontSize: 9, fontWeight: '800', letterSpacing: 0.6},
  riskLine: {fontSize: 12, color: C.ink, marginTop: 8, lineHeight: 17, fontWeight: '600'},
  cardTitle: {fontSize: 13, fontWeight: '700', color: C.ink, marginBottom: 8},
  tagRow: {flexDirection: 'row', gap: 8, marginTop: 10},
  barHead: {flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5},
  barLabel: {fontSize: 13, color: C.ink, fontWeight: '600'},
  attackQ: {fontSize: 13, color: C.ink, fontWeight: '600', lineHeight: 19, fontStyle: 'italic'},
  attackA: {fontSize: 12, color: C.slate, marginTop: 8, lineHeight: 18},
  kindPill: {alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: 6, marginTop: 10},
  kindText: {fontSize: 9, fontWeight: '800', letterSpacing: 0.6},
  compRow: {flexDirection: 'row', gap: 10, marginBottom: 10, alignItems: 'flex-start'},
  compName: {fontSize: 12, fontWeight: '700', color: C.ink, width: 78},
  legendRow: {flexDirection: 'row', gap: 10, marginBottom: 10, alignItems: 'flex-start'},
});
