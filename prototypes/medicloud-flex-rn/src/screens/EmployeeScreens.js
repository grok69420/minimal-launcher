import React, {useState} from 'react';
import {View, Text, StyleSheet, ScrollView, Pressable} from 'react-native';
import {C} from '../theme';
import {ACCOUNT, CLINICS, DISTRICTS, COMMISSION_PCT, FIGURES} from '../data/caseData';
import {Card, SectionTitle, Muted, Button, BlisterStrip, Row, Tag, ClinicGlyph, FakeQR} from '../components/ui';

export function WalletScreen({used, left, visits, onFind, onCard}) {
  const payroll = ACCOUNT.annual - ACCOUNT.employerTopUp;
  return (
    <ScrollView contentContainerStyle={st.pad}>
      <Card>
        <View style={st.rowBetween}>
          <Text style={st.capLabel}>Left to spend</Text>
          <Muted>S${used} of S${ACCOUNT.annual} used</Muted>
        </View>
        <Text style={st.bigAmount}>S${left}</Text>
        <BlisterStrip used={used} total={ACCOUNT.annual} />

        {/* Part B3: a flexible benefit is funded by payroll deduction from before-tax
            income. Calling it an employer allowance is the claim the briefing warns against. */}
        <View style={st.fundingBox}>
          <Text style={st.fundingTitle}>Where this money comes from</Text>
          <Row label="Your payroll deduction (pre-tax)" value={`S$${payroll}`} />
          <Row label="Employer contribution" value={`S$${ACCOUNT.employerTopUp}`} />
          <Row label="Plan year account" value={`S$${ACCOUNT.annual}`} bold />
          <View style={st.tagRow}>
            <Tag name="CASE" />
            <Muted style={st.tagNote}>
              Employees fund flexible benefits through payroll deductions from before-tax
              income, then withdraw for medical expenses. Most of this is your own salary,
              routed for tax efficiency — not a handout.
            </Muted>
          </View>
        </View>

        <Muted style={{marginTop: 10}}>
          Resets 31 Dec. No claim forms — the clinic bills Medicloud directly.
        </Muted>
      </Card>

      <View style={st.quickRow}>
        <Pressable onPress={onFind} style={[st.quick, {backgroundColor: C.teal}]}>
          <Text style={st.quickIcon}>◎</Text>
          <Text style={[st.quickLabel, {color: C.white}]}>Find a panel clinic</Text>
        </Pressable>
        <Pressable onPress={onCard} style={[st.quick, st.quickGhost]}>
          <Text style={[st.quickIcon, {color: C.ink}]}>▦</Text>
          <Text style={[st.quickLabel, {color: C.ink}]}>Show benefit card</Text>
        </Pressable>
      </View>

      <SectionTitle style={{marginTop: 20}}>Recent visits</SectionTitle>
      {visits.map(v => (
        <View key={v.id} style={st.visit}>
          <View style={{flex: 1, paddingRight: 10}}>
            <Text style={st.visitType}>{v.type}</Text>
            <Muted>{v.place} · {v.date}</Muted>
          </View>
          <Text style={st.visitAmt}>S${v.amt}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

export function ClinicsScreen({left, onBook}) {
  const [district, setDistrict] = useState('all');
  const shown = district === 'all' ? CLINICS : CLINICS.filter(c => c.district === district);
  return (
    <ScrollView contentContainerStyle={st.pad}>
      <Text style={st.h1}>Panel clinics near you</Text>
      <Muted style={{marginBottom: 12}}>
        Rates are negotiated for Medicloud members. You pay the actual negotiated cost from
        your account — S${left} available.
      </Muted>

      {/* Densification is recommendation 1 on slide 8: cluster clinics in SME-heavy districts. */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{marginBottom: 14}}>
        <Chip label="All" active={district === 'all'} onPress={() => setDistrict('all')} />
        {DISTRICTS.map(d => (
          <Chip key={d.id} label={`${d.name} · ${d.live}`} active={district === d.id}
            onPress={() => setDistrict(d.id)} />
        ))}
      </ScrollView>

      {shown.map(c => {
        const afford = c.rate <= left;
        return (
          <View key={c.id} style={st.clinic}>
            <View style={{flexDirection: 'row', gap: 12}}>
              <View style={st.badge}><ClinicGlyph kind={c.icon} size={18} /></View>
              <View style={{flex: 1}}>
                <Text style={st.clinicName}>{c.name}</Text>
                <Muted>{c.km} km · {c.wait} min wait</Muted>
                <View style={st.priceRow}>
                  <Text style={st.price}>S${c.rate}</Text>
                  <Text style={st.listPrice}>S${c.list}</Text>
                  <Text style={st.member}>member rate</Text>
                </View>
              </View>
            </View>
            <Button
              style={{marginTop: 12}}
              disabled={!afford}
              label={afford ? 'Book and pay from account' : 'Balance too low — you pay the difference'}
              onPress={() => onBook(c)}
            />
          </View>
        );
      })}

      <Muted style={{marginTop: 8}}>
        Case ranges: GP S${FIGURES.gpVisit.lo}–{FIGURES.gpVisit.hi}, dental S$
        {FIGURES.dental.lo}–{FIGURES.dental.hi} without cover.
      </Muted>
    </ScrollView>
  );
}

function Chip({label, active, onPress}) {
  return (
    <Pressable onPress={onPress} style={[st.chip, active && {backgroundColor: C.ink, borderColor: C.ink}]}>
      <Text style={[st.chipText, active && {color: C.white}]}>{label}</Text>
    </Pressable>
  );
}

export function BookingScreen({clinic, left, onBack, onConfirm}) {
  const slots = ['09:30', '11:00', '14:15', '16:45'];
  const [slot, setSlot] = useState(slots[0]);
  const commission = Math.round(clinic.rate * (COMMISSION_PCT / 100));
  const clinicKeeps = clinic.rate - commission;
  const tpaWouldTake = Math.round(clinic.rate * (FIGURES.tpaTake.value / 100));
  const shortfall = Math.max(0, clinic.rate - left);

  return (
    <ScrollView contentContainerStyle={st.pad}>
      <Pressable onPress={onBack}><Text style={st.back}>‹ Back</Text></Pressable>
      <Text style={st.h1}>{clinic.name}</Text>
      <Muted style={{marginBottom: 16}}>{clinic.type} · Today</Muted>

      <View style={st.slots}>
        {slots.map(sl => (
          <Pressable key={sl} onPress={() => setSlot(sl)}
            style={[st.slot, slot === sl && {backgroundColor: C.teal, borderColor: C.teal}]}>
            <Text style={[st.slotText, slot === sl && {color: C.white}]}>{sl}</Text>
          </Pressable>
        ))}
      </View>

      <Card style={{marginTop: 4}}>
        <Row label="Negotiated member rate" value={`S$${clinic.rate}`} />
        <Row label="Paid from your account" value={`S$${Math.min(clinic.rate, left)}`} />
        {shortfall > 0 && (
          <Row label="You pay at the clinic" value={`S$${shortfall}`} valueColor={C.rose} />
        )}
        <View style={st.divider} />
        <Row label={`Medicloud commission (${COMMISSION_PCT}%)`} value={`S$${commission}`} />
        <Row label="Clinic keeps" value={`S$${clinicKeeps}`} bold />
        <Muted style={{marginTop: 6}}>
          Under a TPA the clinic would pay S${tpaWouldTake} of this visit and deliver the rest
          as care.
        </Muted>
        <View style={st.tagRow}>
          <Tag name="CASE" />
          <Muted style={st.tagNote}>{FIGURES.tpaTake.text}</Muted>
        </View>
      </Card>

      {/* Part E1 — the structure must be named, or the model reads as unlicensed insurance. */}
      <Card style={{marginTop: 12, backgroundColor: C.mint}}>
        <Text style={st.fundingTitle}>Who bears the cost risk</Text>
        <Muted>
          You pay the actual negotiated cost of care. Medicloud does not promise to cover
          future costs and bears no utilisation risk — it earns an administration fee. That is
          what keeps this a discount panel rather than an insurance product.
        </Muted>
        <View style={st.tagRow}><Tag name="ANALYSIS" /></View>
      </Card>

      <Button style={{marginTop: 16}} label={`Confirm ${slot} appointment`}
        onPress={() => onConfirm(slot)} />
    </ScrollView>
  );
}

export function ConfirmationScreen({rec, onDone}) {
  return (
    <ScrollView contentContainerStyle={[st.pad, {alignItems: 'center'}]}>
      <View style={st.checkCircle}><Text style={st.checkMark}>✓</Text></View>
      <Text style={[st.h1, {marginTop: 14}]}>Appointment booked</Text>
      <Muted style={{textAlign: 'center'}}>{rec.place} · Today {rec.slot}</Muted>
      <View style={{marginVertical: 22}}><FakeQR seed={rec.id} /></View>
      <Muted style={{textAlign: 'center', maxWidth: 300}}>
        Show this code at the counter. S${rec.amt} comes out of your account — nothing to
        claim back.
      </Muted>
      <Button style={{marginTop: 22, alignSelf: 'stretch'}} label="Done" onPress={onDone} />
    </ScrollView>
  );
}

export function CardScreen({left}) {
  return (
    <ScrollView contentContainerStyle={st.pad}>
      <View style={st.benefitCard}>
        <Text style={st.cardBrand}>BENEFIT CARD</Text>
        <Text style={st.cardAmount}>S${left}</Text>
        <Text style={st.cardHolder}>{ACCOUNT.holder} · •••• {ACCOUNT.cardLast4}</Text>
        <View style={st.cardQR}><FakeQR seed={`card-${ACCOUNT.cardLast4}`} cell={11} /></View>
      </View>
      <Muted style={{marginTop: 14}}>
        Works at every clinic on the panel. The clinic scans, Medicloud settles weekly and
        takes its commission from the clinic — not from you.
      </Muted>
    </ScrollView>
  );
}

const st = StyleSheet.create({
  pad: {padding: 20, paddingBottom: 40},
  rowBetween: {flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline'},
  capLabel: {fontSize: 11, letterSpacing: 1, textTransform: 'uppercase', color: C.slate, fontWeight: '600'},
  bigAmount: {fontSize: 38, fontWeight: '700', color: C.ink, marginTop: 2, marginBottom: 14},
  fundingBox: {marginTop: 16, backgroundColor: C.white, borderRadius: 12, padding: 12},
  fundingTitle: {fontSize: 13, fontWeight: '700', color: C.ink, marginBottom: 6},
  tagRow: {flexDirection: 'row', gap: 8, marginTop: 8, alignItems: 'flex-start'},
  tagNote: {flex: 1},
  quickRow: {flexDirection: 'row', gap: 12, marginTop: 16},
  quick: {flex: 1, borderRadius: 16, padding: 16, minHeight: 104, justifyContent: 'space-between'},
  quickGhost: {borderWidth: 1, borderColor: C.border},
  quickIcon: {fontSize: 20, color: C.white},
  quickLabel: {fontSize: 13, fontWeight: '600'},
  visit: {flexDirection: 'row', alignItems: 'center', paddingVertical: 12,
    borderTopWidth: 1, borderTopColor: C.lineSoft},
  visitType: {fontSize: 14, fontWeight: '600', color: C.ink},
  visitAmt: {fontSize: 14, fontWeight: '700', color: C.ink},
  h1: {fontSize: 19, fontWeight: '700', color: C.ink},
  chip: {paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1,
    borderColor: C.border, marginRight: 8},
  chipText: {fontSize: 12, fontWeight: '600', color: C.ink},
  clinic: {borderWidth: 1, borderColor: C.line, borderRadius: 16, padding: 14, marginBottom: 12},
  badge: {width: 40, height: 40, borderRadius: 12, backgroundColor: C.mint,
    alignItems: 'center', justifyContent: 'center'},
  clinicName: {fontSize: 14, fontWeight: '700', color: C.ink},
  priceRow: {flexDirection: 'row', alignItems: 'baseline', gap: 8, marginTop: 6},
  price: {fontSize: 16, fontWeight: '700', color: C.ink},
  listPrice: {fontSize: 12, color: C.slate, textDecorationLine: 'line-through'},
  member: {fontSize: 11, fontWeight: '600', color: C.teal},
  back: {fontSize: 14, color: C.slate, marginBottom: 12},
  slots: {flexDirection: 'row', gap: 8, marginBottom: 14},
  slot: {flex: 1, borderWidth: 1, borderColor: C.border, borderRadius: 12,
    paddingVertical: 10, alignItems: 'center'},
  slotText: {fontSize: 13, fontWeight: '600', color: C.ink},
  divider: {height: 1, backgroundColor: C.border, marginVertical: 8},
  checkCircle: {width: 56, height: 56, borderRadius: 999, backgroundColor: C.mint,
    alignItems: 'center', justifyContent: 'center', marginTop: 20},
  checkMark: {fontSize: 26, color: C.teal, fontWeight: '700'},
  benefitCard: {backgroundColor: C.ink, borderRadius: 22, padding: 20},
  cardBrand: {fontSize: 10, letterSpacing: 2, color: C.mint, fontWeight: '700'},
  cardAmount: {fontSize: 30, fontWeight: '700', color: C.white, marginTop: 8},
  cardHolder: {fontSize: 12, color: C.onInk, marginTop: 4},
  cardQR: {backgroundColor: C.white, borderRadius: 16, alignItems: 'center',
    paddingVertical: 14, marginTop: 18},
});
