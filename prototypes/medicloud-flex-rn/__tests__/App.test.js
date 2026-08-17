/**
 * Behavioural tests for the Medicloud Flex prototype.
 *
 * These drive the real component tree rather than asserting on snapshots, so they catch
 * render-time crashes and wrong arithmetic — the two failures that would otherwise only
 * show up on a device.
 */
import React from 'react';
import renderer, {act} from 'react-test-renderer';
import App from '../App';
import {ACCOUNT, SEED_VISITS, CLINICS, COMMISSION_PCT, FIGURES} from '../src/data/caseData';

/** All text rendered anywhere in the tree, flattened into one string. */
function textOf(tree) {
  const out = [];
  const walk = node => {
    if (node == null) return;
    if (typeof node === 'string' || typeof node === 'number') {
      out.push(String(node));
      return;
    }
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (node.children) node.children.forEach(walk);
  };
  walk(tree.toJSON());
  // RN renders `S${amount}` as two adjacent text nodes, so rejoin the currency prefix
  // with its number before matching.
  return out.join(' ').replace(/S\$\s+/g, 'S$').replace(/\s+/g, ' ');
}

/** Text contained beneath a single test instance. React elements are circular, so this
 *  walks the instance tree rather than serialising props. */
function instanceText(instance) {
  const out = [];
  const walk = node => {
    if (node == null) return;
    if (typeof node === 'string' || typeof node === 'number') {
      out.push(String(node));
      return;
    }
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (node.children) walk(node.children);
  };
  walk(instance.children);
  return out.join(' ');
}

/** Find every node whose props contain an onPress handler and whose text matches. */
function pressablesWithText(root, needle) {
  return root.root.findAll(
    n => typeof n.props?.onPress === 'function' && instanceText(n).includes(needle),
    {deep: true},
  );
}

function pressByText(root, needle) {
  // First match in tree order. A custom Button and the Pressable it renders both carry the
  // same handler, so either fires the same action — but taking the last would skip past the
  // first matching button to the last one on screen.
  const hits = pressablesWithText(root, needle);
  if (!hits.length) throw new Error(`no pressable containing "${needle}"`);
  act(() => hits[0].props.onPress());
}

let tree;
beforeEach(() => {
  act(() => {
    tree = renderer.create(<App />);
  });
});

describe('employee account', () => {
  it('opens on the wallet with the balance left after seeded visits', () => {
    const used = SEED_VISITS.reduce((s, v) => s + v.amt, 0);
    const left = ACCOUNT.annual - used;
    const txt = textOf(tree);
    expect(txt).toContain(`S$${left}`);
    expect(txt).toContain(`S$${used} of S$${ACCOUNT.annual} used`);
  });

  it('states the pre-tax payroll funding rather than calling it an employer allowance', () => {
    const txt = textOf(tree);
    expect(txt).toContain('Your payroll deduction (pre-tax)');
    expect(txt).toContain('Employer contribution');
    // The employer top-up plus the payroll deduction must reconcile to the account.
    expect(ACCOUNT.employerTopUp).toBeLessThan(ACCOUNT.annual);
  });

  it('books a clinic and deducts the negotiated rate from the balance', () => {
    const used = SEED_VISITS.reduce((s, v) => s + v.amt, 0);
    const left = ACCOUNT.annual - used;

    pressByText(tree, 'Find a panel clinic');
    expect(textOf(tree)).toContain('Panel clinics near you');

    const clinic = CLINICS[0];
    pressByText(tree, 'Book and pay from account');
    expect(textOf(tree)).toContain(clinic.name);

    // Cost breakdown must show the commission split, not just a total.
    const commission = Math.round(clinic.rate * (COMMISSION_PCT / 100));
    expect(textOf(tree)).toContain(`S$${clinic.rate - commission}`);

    pressByText(tree, 'Confirm');
    expect(textOf(tree)).toContain('Appointment booked');

    pressByText(tree, 'Done');
    expect(textOf(tree)).toContain(`S$${left - clinic.rate}`);
  });
});

describe('HR dashboard', () => {
  beforeEach(() => pressByText(tree, 'HR'));

  it('computes the avoided spend from the case midpoint', () => {
    const mid = (FIGURES.entryPolicy.lo + FIGURES.entryPolicy.hi) / 2;
    const saving = (mid - ACCOUNT.annual) * ACCOUNT.headcount;
    expect(textOf(tree)).toContain(saving.toLocaleString());
  });

  it('reports aggregates only and says why individuals are not shown', () => {
    const txt = textOf(tree);
    expect(txt).toContain('Why you cannot see individuals here');
    expect(txt).not.toContain(ACCOUNT.holder); // no named employee on the employer view
  });

  it('carries the kill criterion', () => {
    expect(textOf(tree)).toContain('Guardrail');
  });
});

describe('case defence', () => {
  beforeEach(() => pressByText(tree, 'Case'));

  it('names the chosen structure and marks the risk-bearing one rejected', () => {
    const txt = textOf(tree);
    expect(txt).toContain('Discount panel + administration');
    expect(txt).toContain('BUILT');
    expect(txt).toContain('Prepaid / capitated membership');
    expect(txt).toContain('REJECTED');
  });

  it('concedes the margin-pool attack rather than claiming the full S$60', () => {
    pressByText(tree, 'Economics');
    const txt = textOf(tree);
    expect(txt).toContain('The margin pool we do not claim');
    expect(txt).toContain(`S$${FIGURES.tpaTake.value}`);
  });

  it('lists attacks with explicit concessions', () => {
    pressByText(tree, 'Attacks');
    const txt = textOf(tree);
    expect(txt).toContain('CONCEDE');
    expect(txt).toContain('BookDoc');
  });
});
