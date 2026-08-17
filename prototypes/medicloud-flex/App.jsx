import React, { useState, useMemo } from "react";
import { Wallet, MapPin, QrCode, Building2, ChevronLeft, Check, Clock, Stethoscope, Smile, Leaf, TrendingDown } from "lucide-react";

/* Medicloud Flex — prototype for Option B in the Medicloud Singapore case (Ivey W20043):
   bypass insurance, act as a flexible-benefit provider to SME employees using the clinic panel. */

const C = {
  ink: "#0A1A2F",
  teal: "#0E8F8B",
  mint: "#D8F2EF",
  amber: "#F5A623",
  slate: "#64748B",
  bg: "#EEF3F5",
};

const CLINICS = [
  { id: 1, name: "Bukit Merah Family Clinic", type: "GP", icon: Stethoscope, km: 0.4, wait: 10, cap: 38, list: 70 },
  { id: 2, name: "Tanjong Pagar Dental", type: "Dental", icon: Smile, km: 1.1, wait: 25, cap: 95, list: 150 },
  { id: 3, name: "Redhill TCM Wellness", type: "TCM", icon: Leaf, km: 1.6, wait: 15, cap: 45, list: 80 },
  { id: 4, name: "Chinatown Medical", type: "GP", icon: Stethoscope, km: 2.0, wait: 5, cap: 35, list: 65 },
];

const ALLOWANCE = 500;

export default function App() {
  const [role, setRole] = useState("employee");
  const [tab, setTab] = useState("wallet");
  const [claims, setClaims] = useState([
    { id: "c1", place: "Bukit Merah Family Clinic", type: "GP visit", amt: 38, date: "12 Aug" },
    { id: "c2", place: "Redhill TCM Wellness", type: "Acupuncture", amt: 45, date: "28 Jul" },
    { id: "c3", place: "Tanjong Pagar Dental", type: "Scaling", amt: 95, date: "09 Jul" },
  ]);
  const [booking, setBooking] = useState(null);
  const [confirmed, setConfirmed] = useState(null);

  const used = useMemo(() => claims.reduce((s, c) => s + c.amt, 0), [claims]);
  const left = ALLOWANCE - used;

  function confirmBooking(slot) {
    const c = booking;
    const rec = { id: "n" + Date.now(), place: c.name, type: c.type + " visit", amt: c.cap, date: "Today", slot };
    setClaims([rec, ...claims]);
    setConfirmed({ ...rec, clinic: c });
    setBooking(null);
  }

  return (
    <div style={{ background: C.bg, fontFamily: "ui-sans-serif, system-ui, -apple-system, sans-serif" }} className="min-h-screen w-full flex justify-center">
      <div className="w-full max-w-md flex flex-col min-h-screen bg-white shadow-xl relative">
        <Header role={role} setRole={setRole} />

        <main className="flex-1 overflow-y-auto pb-24">
          {role === "hr" ? (
            <HRDashboard />
          ) : confirmed ? (
            <Confirmation rec={confirmed} onDone={() => { setConfirmed(null); setTab("wallet"); }} />
          ) : booking ? (
            <BookingSheet clinic={booking} onBack={() => setBooking(null)} onConfirm={confirmBooking} />
          ) : tab === "wallet" ? (
            <WalletView used={used} left={left} claims={claims} onFind={() => setTab("clinics")} onPay={() => setTab("pay")} />
          ) : tab === "clinics" ? (
            <ClinicsView left={left} onBook={setBooking} />
          ) : (
            <PayView left={left} />
          )}
        </main>

        {role === "employee" && !booking && !confirmed && <TabBar tab={tab} setTab={setTab} />}
      </div>
    </div>
  );
}

function Header({ role, setRole }) {
  return (
    <header style={{ background: C.ink }} className="px-5 pt-6 pb-5 text-white">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[11px] tracking-[0.2em] uppercase" style={{ color: C.mint }}>Medicloud</div>
          <div className="text-2xl font-semibold -mt-0.5">Flex</div>
        </div>
        <div className="flex rounded-full p-0.5" style={{ background: "rgba(255,255,255,0.12)" }}>
          <button onClick={() => setRole("employee")} className="px-3 py-1.5 text-xs rounded-full font-medium"
            style={role === "employee" ? { background: C.teal } : {}}>Employee</button>
          <button onClick={() => setRole("hr")} className="px-3 py-1.5 text-xs rounded-full font-medium"
            style={role === "hr" ? { background: C.teal } : {}}>HR</button>
        </div>
      </div>
      <p className="text-xs mt-2" style={{ color: "#9FB3C2" }}>
        {role === "hr" ? "Tai Seng Logistics Pte Ltd · 42 employees" : "Wei Ling Tan · Tai Seng Logistics · Plan year 2026"}
      </p>
    </header>
  );
}

/* Signature element: allowance shown as a blister-pack strip — one capsule per $25 of benefit. */
function BlisterStrip({ used, total }) {
  const cells = total / 25;
  const spent = Math.round(used / 25);
  return (
    <div className="grid grid-cols-10 gap-1.5">
      {Array.from({ length: cells }).map((_, i) => (
        <div key={i} className="h-6 rounded-full border"
          style={i < spent
            ? { background: "#E2E8F0", borderColor: "#E2E8F0" }
            : { background: C.mint, borderColor: C.teal }} />
      ))}
    </div>
  );
}

function WalletView({ used, left, claims, onFind, onPay }) {
  return (
    <div className="px-5 py-5 space-y-5">
      <section className="rounded-2xl p-5" style={{ background: C.bg }}>
        <div className="flex items-baseline justify-between">
          <span className="text-xs uppercase tracking-wider" style={{ color: C.slate }}>Left to spend</span>
          <span className="text-xs" style={{ color: C.slate }}>S${used} of S$500 used</span>
        </div>
        <div className="text-4xl font-semibold mt-1 mb-4" style={{ color: C.ink, fontVariantNumeric: "tabular-nums" }}>
          S${left}
        </div>
        <BlisterStrip used={used} total={500} />
        <p className="text-xs mt-3" style={{ color: C.slate }}>Resets 31 Dec. No claim forms — the clinic bills Medicloud directly.</p>
      </section>

      <div className="grid grid-cols-2 gap-3">
        <button onClick={onFind} className="rounded-2xl p-4 text-left text-white" style={{ background: C.teal }}>
          <MapPin size={20} />
          <div className="mt-6 font-medium text-sm">Find a panel clinic</div>
        </button>
        <button onClick={onPay} className="rounded-2xl p-4 text-left border" style={{ borderColor: "#E2E8F0", color: C.ink }}>
          <QrCode size={20} />
          <div className="mt-6 font-medium text-sm">Show benefit card</div>
        </button>
      </div>

      <section>
        <h2 className="text-sm font-semibold mb-2" style={{ color: C.ink }}>Recent visits</h2>
        <ul className="divide-y" style={{ borderColor: "#EEF2F5" }}>
          {claims.map((c) => (
            <li key={c.id} className="py-3 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium" style={{ color: C.ink }}>{c.type}</div>
                <div className="text-xs" style={{ color: C.slate }}>{c.place} · {c.date}</div>
              </div>
              <div className="text-sm font-semibold" style={{ color: C.ink, fontVariantNumeric: "tabular-nums" }}>S${c.amt}</div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function ClinicsView({ left, onBook }) {
  return (
    <div className="px-5 py-5">
      <h2 className="text-lg font-semibold" style={{ color: C.ink }}>Panel clinics near you</h2>
      <p className="text-xs mb-4" style={{ color: C.slate }}>Prices are capped for Medicloud members. S${left} of your benefit is available.</p>
      <ul className="space-y-3">
        {CLINICS.map((c) => {
          const Icon = c.icon;
          const afford = c.cap <= left;
          return (
            <li key={c.id} className="rounded-2xl border p-4" style={{ borderColor: "#E7EDF1" }}>
              <div className="flex gap-3">
                <div className="h-10 w-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: C.mint, color: C.teal }}>
                  <Icon size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold truncate" style={{ color: C.ink }}>{c.name}</div>
                  <div className="text-xs mt-0.5 flex items-center gap-3" style={{ color: C.slate }}>
                    <span>{c.km} km</span>
                    <span className="flex items-center gap-1"><Clock size={12} />{c.wait} min wait</span>
                  </div>
                  <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-base font-semibold" style={{ color: C.ink }}>S${c.cap}</span>
                    <span className="text-xs line-through" style={{ color: C.slate }}>S${c.list}</span>
                    <span className="text-[11px] font-medium" style={{ color: C.teal }}>member price</span>
                  </div>
                </div>
              </div>
              <button disabled={!afford} onClick={() => onBook(c)}
                className="mt-3 w-full rounded-xl py-2.5 text-sm font-medium text-white disabled:opacity-40"
                style={{ background: C.ink }}>
                {afford ? "Book and pay from benefit" : "Not enough benefit left"}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function BookingSheet({ clinic, onBack, onConfirm }) {
  const slots = ["09:30", "11:00", "14:15", "16:45"];
  const [slot, setSlot] = useState(slots[0]);
  return (
    <div className="px-5 py-5">
      <button onClick={onBack} className="flex items-center gap-1 text-sm mb-4" style={{ color: C.slate }}>
        <ChevronLeft size={16} /> Back
      </button>
      <h2 className="text-lg font-semibold" style={{ color: C.ink }}>{clinic.name}</h2>
      <p className="text-xs mb-5" style={{ color: C.slate }}>{clinic.type} · Today, 17 Aug</p>

      <div className="grid grid-cols-4 gap-2 mb-5">
        {slots.map((s) => (
          <button key={s} onClick={() => setSlot(s)} className="rounded-xl py-2.5 text-sm border font-medium"
            style={slot === s ? { background: C.teal, color: "#fff", borderColor: C.teal } : { borderColor: "#E2E8F0", color: C.ink }}>
            {s}
          </button>
        ))}
      </div>

      <div className="rounded-2xl p-4 mb-5" style={{ background: C.bg }}>
        <Row label="Consultation (capped)" value={`S$${clinic.cap}`} />
        <Row label="You pay at the clinic" value="S$0" />
        <Row label="Deducted from benefit" value={`S$${clinic.cap}`} bold />
        <p className="text-[11px] mt-2" style={{ color: C.slate }}>No third-party administrator. The clinic keeps S${Math.round(clinic.cap * 0.9)} of this visit.</p>
      </div>

      <button onClick={() => onConfirm(slot)} className="w-full rounded-xl py-3 text-white font-medium" style={{ background: C.ink }}>
        Confirm {slot} appointment
      </button>
    </div>
  );
}

function Row({ label, value, bold }) {
  return (
    <div className="flex justify-between py-1 text-sm">
      <span style={{ color: C.slate }}>{label}</span>
      <span style={{ color: C.ink, fontWeight: bold ? 600 : 400 }}>{value}</span>
    </div>
  );
}

function Confirmation({ rec, onDone }) {
  return (
    <div className="px-5 py-10 flex flex-col items-center text-center">
      <div className="h-14 w-14 rounded-full flex items-center justify-center" style={{ background: C.mint, color: C.teal }}>
        <Check size={28} />
      </div>
      <h2 className="text-xl font-semibold mt-4" style={{ color: C.ink }}>Appointment booked</h2>
      <p className="text-sm mt-1" style={{ color: C.slate }}>{rec.place} · Today {rec.slot}</p>
      <div className="my-6"><FakeQR seed={rec.id} /></div>
      <p className="text-xs max-w-xs" style={{ color: C.slate }}>Show this code at the counter. S${rec.amt} is deducted from your benefit — nothing to pay, nothing to claim back.</p>
      <button onClick={onDone} className="mt-6 w-full rounded-xl py-3 text-white font-medium" style={{ background: C.ink }}>Done</button>
    </div>
  );
}

function FakeQR({ seed = "medicloud" }) {
  const cells = useMemo(() => {
    let h = 0;
    for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
    return Array.from({ length: 121 }).map((_, i) => {
      h = (h * 1103515245 + 12345 + i) >>> 0;
      return (h >>> 16) % 2 === 0;
    });
  }, [seed]);
  return (
    <div className="p-3 rounded-2xl border" style={{ borderColor: "#E2E8F0" }}>
      <div className="grid grid-cols-11 gap-0.5" style={{ width: 176 }}>
        {cells.map((on, i) => (
          <div key={i} style={{ width: 14, height: 14, background: on ? C.ink : "transparent", borderRadius: 2 }} />
        ))}
      </div>
    </div>
  );
}

function PayView({ left }) {
  return (
    <div className="px-5 py-6">
      <div className="rounded-3xl p-5 text-white" style={{ background: C.ink }}>
        <div className="text-[11px] tracking-[0.2em] uppercase" style={{ color: C.mint }}>Benefit card</div>
        <div className="text-3xl font-semibold mt-2" style={{ fontVariantNumeric: "tabular-nums" }}>S${left}</div>
        <div className="text-xs mt-1" style={{ color: "#9FB3C2" }}>Wei Ling Tan · •••• 4417</div>
        <div className="mt-5 flex justify-center bg-white rounded-2xl py-4"><FakeQR seed="card-4417" /></div>
      </div>
      <p className="text-xs mt-4" style={{ color: C.slate }}>Works at all 50 panel clinics. The clinic scans, Medicloud settles the bill weekly.</p>
    </div>
  );
}

function HRDashboard() {
  const bars = [
    { label: "GP", pct: 46, amt: 8740 },
    { label: "Dental", pct: 31, amt: 5890 },
    { label: "TCM", pct: 14, amt: 2660 },
    { label: "Wellness", pct: 9, amt: 1710 },
  ];
  return (
    <div className="px-5 py-5 space-y-5">
      <section className="rounded-2xl p-5" style={{ background: C.ink }}>
        <div className="flex items-center gap-2 text-xs" style={{ color: C.mint }}>
          <TrendingDown size={14} /> Versus a group outpatient policy
        </div>
        <div className="text-3xl font-semibold text-white mt-2" style={{ fontVariantNumeric: "tabular-nums" }}>S$31,500</div>
        <div className="text-xs mt-1" style={{ color: "#9FB3C2" }}>saved this year across 42 employees</div>
        <div className="mt-4 space-y-2">
          <CostBar label="Insurance + TPA route" value="S$1,250 / employee" pct={100} color="#31485E" />
          <CostBar label="Medicloud Flex" value="S$500 / employee" pct={40} color={C.teal} />
        </div>
      </section>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Enrolled" value="42" />
        <Stat label="Activated" value="88%" />
        <Stat label="Benefit used" value="62%" />
      </div>

      <section>
        <h2 className="text-sm font-semibold mb-3" style={{ color: C.ink }}>Where the benefit goes</h2>
        <div className="space-y-3">
          {bars.map((b) => (
            <div key={b.label}>
              <div className="flex justify-between text-xs mb-1">
                <span style={{ color: C.ink }}>{b.label}</span>
                <span style={{ color: C.slate }}>S${b.amt.toLocaleString()}</span>
              </div>
              <div className="h-2 rounded-full" style={{ background: "#EEF2F5" }}>
                <div className="h-2 rounded-full" style={{ width: b.pct + "%", background: C.teal }} />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border p-4" style={{ borderColor: "#E7EDF1" }}>
        <div className="flex items-center gap-2 mb-1">
          <Building2 size={16} style={{ color: C.amber }} />
          <h3 className="text-sm font-semibold" style={{ color: C.ink }}>Revenue model</h3>
        </div>
        <p className="text-xs" style={{ color: C.slate }}>
          S$8 per employee per month platform fee, plus a 10% clinic commission — against the 40% a third-party
          administrator takes today. Break-even at roughly 3,000 covered employees.
        </p>
      </section>
    </div>
  );
}

function CostBar({ label, value, pct, color }) {
  return (
    <div>
      <div className="flex justify-between text-[11px] mb-1" style={{ color: "#9FB3C2" }}>
        <span>{label}</span><span>{value}</span>
      </div>
      <div className="h-2.5 rounded-full" style={{ background: "rgba(255,255,255,0.12)" }}>
        <div className="h-2.5 rounded-full" style={{ width: pct + "%", background: color }} />
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-2xl p-3 text-center" style={{ background: C.bg }}>
      <div className="text-xl font-semibold" style={{ color: C.ink }}>{value}</div>
      <div className="text-[11px]" style={{ color: C.slate }}>{label}</div>
    </div>
  );
}

function TabBar({ tab, setTab }) {
  const items = [
    { id: "wallet", label: "Benefit", Icon: Wallet },
    { id: "clinics", label: "Clinics", Icon: MapPin },
    { id: "pay", label: "Card", Icon: QrCode },
  ];
  return (
    <nav className="absolute bottom-0 left-0 right-0 bg-white border-t flex" style={{ borderColor: "#EEF2F5" }}>
      {items.map(({ id, label, Icon }) => (
        <button key={id} onClick={() => setTab(id)} className="flex-1 py-3 flex flex-col items-center gap-1"
          style={{ color: tab === id ? C.teal : C.slate }}>
          <Icon size={20} />
          <span className="text-[11px] font-medium">{label}</span>
        </button>
      ))}
    </nav>
  );
}
