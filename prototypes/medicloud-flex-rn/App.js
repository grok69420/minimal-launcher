import React, {useState, useMemo} from 'react';
import {View, Text, StyleSheet, StatusBar, Pressable, SafeAreaView} from 'react-native';
import {C} from './src/theme';
import {ACCOUNT, SEED_VISITS} from './src/data/caseData';
import {
  WalletScreen, ClinicsScreen, BookingScreen, ConfirmationScreen, CardScreen,
} from './src/screens/EmployeeScreens';
import {HRScreen} from './src/screens/HRScreen';
import {CaseScreen} from './src/screens/CaseScreen';

/* Medicloud Flex — Option B prototype for the Medicloud Singapore case (Ivey W20043):
   bypass insurance and act as a flexible-benefit provider on Medicloud's own clinic panel.

   Figures come from the case, from arithmetic on case figures, or are flagged as argument
   or unverified. See src/data/caseData.js. */

const ROLES = [
  {id: 'employee', label: 'Employee'},
  {id: 'hr', label: 'HR'},
  {id: 'case', label: 'Case'},
];

export default function App() {
  const [role, setRole] = useState('employee');
  const [tab, setTab] = useState('wallet');
  const [visits, setVisits] = useState(SEED_VISITS);
  const [booking, setBooking] = useState(null);
  const [confirmed, setConfirmed] = useState(null);

  const used = useMemo(() => visits.reduce((sum, v) => sum + v.amt, 0), [visits]);
  const left = Math.max(0, ACCOUNT.annual - used);

  function confirmBooking(slot) {
    const clinic = booking;
    const rec = {
      id: 'n' + Date.now(),
      place: clinic.name,
      type: `${clinic.type} visit`,
      amt: clinic.rate,
      date: 'Today',
      slot,
    };
    setVisits([rec, ...visits]);
    setConfirmed(rec);
    setBooking(null);
  }

  function selectRole(next) {
    setRole(next);
    setBooking(null);
    setConfirmed(null);
  }

  let body;
  if (role === 'hr') {
    body = <HRScreen />;
  } else if (role === 'case') {
    body = <CaseScreen />;
  } else if (confirmed) {
    body = <ConfirmationScreen rec={confirmed} onDone={() => {
      setConfirmed(null);
      setTab('wallet');
    }} />;
  } else if (booking) {
    body = <BookingScreen clinic={booking} left={left} onBack={() => setBooking(null)}
      onConfirm={confirmBooking} />;
  } else if (tab === 'wallet') {
    body = <WalletScreen used={used} left={left} visits={visits}
      onFind={() => setTab('clinics')} onCard={() => setTab('card')} />;
  } else if (tab === 'clinics') {
    body = <ClinicsScreen left={left} onBook={setBooking} />;
  } else {
    body = <CardScreen left={left} />;
  }

  const showTabBar = role === 'employee' && !booking && !confirmed;

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor={C.ink} />

      <View style={s.header}>
        <View style={s.headerTop}>
          <View>
            <Text style={s.brand}>MEDICLOUD</Text>
            <Text style={s.brandName}>Flex</Text>
          </View>
          <View style={s.roleSwitch}>
            {ROLES.map(r => (
              <Pressable key={r.id} onPress={() => selectRole(r.id)}
                style={[s.roleBtn, role === r.id && {backgroundColor: C.teal}]}>
                <Text style={s.roleText}>{r.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
        <Text style={s.headerSub}>
          {role === 'hr'
            ? `${ACCOUNT.employer} · ${ACCOUNT.headcount} employees`
            : role === 'case'
            ? 'Ivey W20043 · defending Option B'
            : `${ACCOUNT.holder} · ${ACCOUNT.employer} · Plan year ${ACCOUNT.planYear}`}
        </Text>
      </View>

      <View style={s.body}>{body}</View>

      {showTabBar && (
        <View style={s.tabBar}>
          {[['wallet', 'Account'], ['clinics', 'Clinics'], ['card', 'Card']].map(([id, label]) => (
            <Pressable key={id} onPress={() => setTab(id)} style={s.tabItem}>
              <Text style={[s.tabLabel, tab === id && {color: C.teal, fontWeight: '700'}]}>
                {label}
              </Text>
            </Pressable>
          ))}
        </View>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: {flex: 1, backgroundColor: C.white},
  header: {backgroundColor: C.ink, paddingHorizontal: 20, paddingTop: 18, paddingBottom: 16},
  headerTop: {flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start'},
  brand: {fontSize: 10, letterSpacing: 2, color: C.mint, fontWeight: '700'},
  brandName: {fontSize: 24, fontWeight: '700', color: C.white, marginTop: -1},
  roleSwitch: {flexDirection: 'row', backgroundColor: 'rgba(255,255,255,0.12)',
    borderRadius: 999, padding: 3},
  roleBtn: {paddingHorizontal: 11, paddingVertical: 6, borderRadius: 999},
  roleText: {fontSize: 11, color: C.white, fontWeight: '600'},
  headerSub: {fontSize: 11, color: C.onInk, marginTop: 8},
  body: {flex: 1},
  tabBar: {flexDirection: 'row', borderTopWidth: 1, borderTopColor: C.lineSoft,
    backgroundColor: C.white},
  tabItem: {flex: 1, paddingVertical: 14, alignItems: 'center'},
  tabLabel: {fontSize: 12, color: C.slate, fontWeight: '600'},
});
