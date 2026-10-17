import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { dashboard, delta, edge, impact } from './fixtures';
import { renderApp } from './render';
import { request, sessionId } from '../api/client';

const success = (data: unknown) =>
  new Response(JSON.stringify({ data, meta: { request_id: 'test-request', mode: 'local' } }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

describe('RegImpact review workflows', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string, init?: RequestInit) => {
        if (input.endsWith('/dashboard')) return success(dashboard);
        if (input.endsWith('/demo-catalog'))
          return success({
            origin: 'LOCAL_SEED',
            catalog: {
              title: 'One rulebook, one complete review journey',
              baseline: 'Previous baseline: MAS 2016',
              comparison: 'Comparison version: MAS 2023 consultation',
              notice: 'Historical baseline-to-proposal example.',
              steps: [{ label: '1. Inspect both source versions', path: '/sources' }],
            },
          });
        if (input.endsWith('/delta-review')) return success(delta);
        if (input.endsWith('/impact-assessments'))
          return success({ assessments: [], required_role: 'Policy Owner' });
        if (input.endsWith('/impact')) return success(impact);
        if (input.endsWith('/explain')) return success(edge);
        if (input.endsWith('/review') && init?.method === 'POST')
          return success({
            ...delta.assessments[0],
            reviewed_by: 'Demo reviewer',
            status: 'SCENARIO_APPROVED',
          });
        if (input.endsWith('/demo/reset')) return success({ reset: true });
        return new Response(
          JSON.stringify({
            error: { code: 'NOT_FOUND', message: 'Not found' },
            meta: { request_id: 'missing' },
          }),
          { status: 404 },
        );
      }),
    );
  });

  it('shows server-calculated metrics, proposal notice and honest seed status', async () => {
    renderApp();
    expect(
      await screen.findByRole('heading', { name: 'Review only what changed.' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Safety net engaged')).toBeInTheDocument();
    expect(screen.getByText('PROPOSED — NOT AN IN-FORCE REQUIREMENT')).toBeInTheDocument();
    expect(screen.getByText(/Live Gemini runs appear/)).toBeInTheDocument();
    expect(
      screen.getByText(/0 silent carry-forwards/),
    ).toBeInTheDocument();
    expect(screen.getByText(/synthetic hackathon data/)).toBeInTheDocument();
  });

  it('disables unsafe bulk reuse when no mapping passes safeguards', async () => {
    renderApp('/delta-review');
    expect(
      await screen.findByRole('button', { name: 'Acknowledge safe candidates' }),
    ).toBeDisabled();
    expect(screen.getByText(/Unsafe reuse blocked/)).toBeInTheDocument();
  });

  it('acknowledges an explicitly synthetic eligible batch through the API', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    const eligibleDelta = {
      ...delta,
      metrics: {
        ...delta.metrics,
        carry_forward_candidates: 3,
        individual_rechecks: 1,
        estimated_review_reduction: 50,
      },
      assessments: [
        {
          ...delta.assessments[0],
          classification: 'UNCHANGED',
          status: 'CARRY_FORWARD_PENDING_ACK',
          eligible_for_carry_forward: true,
        },
      ],
    };
    let acknowledged = false;
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      if (String(input).endsWith('/acknowledge-carry-forward')) {
        acknowledged = true;
        return success(eligibleDelta);
      }
      if (String(input).endsWith('/delta-review'))
        return success(
          acknowledged
            ? {
                ...eligibleDelta,
                metrics: {
                  ...eligibleDelta.metrics,
                  acknowledged_mappings: 3,
                  review_reduction: 50,
                },
              }
            : eligibleDelta,
        );
      return handler(input, init);
    });
    const user = userEvent.setup();
    renderApp('/delta-review');
    const acknowledge = await screen.findByRole('button', { name: 'Acknowledge safe candidates' });
    expect(acknowledge).toBeEnabled();
    await user.click(acknowledge);
    expect(await screen.findByRole('button', { name: 'Candidates acknowledged' })).toBeDisabled();
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith('/acknowledge-carry-forward'));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      role: 'Regulatory Specialist',
      reviewer: 'Demo reviewer',
    });
  });

  it('requires appropriate role and rationale then posts a real API decision', async () => {
    const user = userEvent.setup();
    renderApp('/delta-review');
    await user.click(await screen.findByRole('button', { name: 'Review mapping' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Approve scenario mapping' })).toBeDisabled();
    expect(
      within(dialog).getByText(/Switch the demo reviewer role to Policy Owner/),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Close dialog' }));
    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Policy Owner');
    await user.click(screen.getByRole('button', { name: 'Review mapping' }));
    expect(screen.getByRole('button', { name: 'Approve scenario mapping' })).toBeDisabled();
    await user.type(
      screen.getByLabelText('Your decision rationale'),
      'Policy covers the prospective gift safeguard scope.',
    );
    await user.click(screen.getByRole('button', { name: 'Approve scenario mapping' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith('/assessments/ASSESS-GIFT/review'));
    expect(call).toBeDefined();
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      decision: 'APPROVE',
      role: 'Policy Owner',
      reviewer: 'Demo reviewer',
    });
    expect((call?.[1]?.headers as Record<string, string>)['X-Demo-Session']).toMatch(
      /^[a-f\d-]{36}$/,
    );
  });

  it('exposes edge provenance with paraphrases and unavailable live rankings', async () => {
    const user = userEvent.setup();
    renderApp('/impact/CHANGE-GIFT');
    await user.click(
      await screen.findByRole('button', { name: 'Explain edge M-GIFT to PR-GIFT-01' }),
    );
    expect(
      await screen.findByText('Gift policy directly addresses the gift safeguard mandate.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Paraphrase')).toBeInTheDocument();
    expect(screen.getByText(/Curated by the team as a golden label/)).toBeInTheDocument();
    expect(
      screen.getByText('Golden label — no model run or retrieval ranks recorded'),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Close dialog' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('requires Risk Steward for risk mappings and submits the rejection rationale', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).endsWith('/delta-review')
        ? success({
            ...delta,
            assessments: [
              {
                ...delta.assessments[0],
                required_role: 'Risk Steward',
                target_id: 'RT-CONDUCT',
                relationship: 'CLASSIFIED_AS',
              },
            ],
          })
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/delta-review');
    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Policy Owner');
    await user.click(await screen.findByRole('button', { name: 'Review mapping' }));
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
    expect(screen.getByText(/Switch the demo reviewer role to Risk Steward/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Close dialog' }));
    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Risk Steward');
    await user.click(screen.getByRole('button', { name: 'Review mapping' }));
    await user.type(
      screen.getByLabelText('Your decision rationale'),
      'Risk classification requires a narrower scoped taxonomy.',
    );
    await user.click(screen.getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith('/assessments/ASSESS-GIFT/review'));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      decision: 'REJECT',
      role: 'Risk Steward',
    });
  });

  it('blocks unresolved mapping decisions until change effect is confirmed', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).endsWith('/delta-review')
        ? success({
            ...delta,
            assessments: [
              {
                ...delta.assessments[0],
                classification: 'UNRESOLVED',
                status: 'MANUAL_REVIEW_REQUIRED',
              },
            ],
          })
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/delta-review');
    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Policy Owner');
    await user.click(await screen.findByRole('button', { name: 'Review mapping' }));
    expect(screen.getByText(/Confirm change effect first/)).toBeInTheDocument();
    expect(screen.getByLabelText('Your decision rationale')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Approve scenario mapping' })).toBeDisabled();
  });

  it('shows an immutable recorded decision and its saved rationale', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).endsWith('/delta-review')
        ? success({
            ...delta,
            assessments: [
              {
                ...delta.assessments[0],
                status: 'SCENARIO_APPROVED',
                reviewed_by: 'Demo reviewer',
                rationale: 'Approved after reviewing scope and source evidence.',
              },
            ],
          })
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/delta-review');
    await user.click(await screen.findByRole('button', { name: 'Review decision' }));
    expect(screen.getByRole('dialog')).toHaveAccessibleName('Recorded scenario decision');
    expect(
      screen.getByText('Approved after reviewing scope and source evidence.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Approve scenario mapping' }),
    ).not.toBeInTheDocument();
  });

  it('shows a proposed unmapped mandate as a gap without claiming approved baseline', async () => {
    vi.mocked(fetch).mockImplementation(async (input) =>
      String(input).endsWith('/impact-assessments')
        ? success({ assessments: [], required_role: 'Policy Owner' })
        : String(input).endsWith('/dashboard')
          ? success(dashboard)
          : success({
              nodes: [
                {
                  id: 'M-CONSENT',
                  label: 'Consent safeguard',
                  type: 'MANDATE',
                  status: 'PROPOSED',
                },
              ],
              edges: [],
              controls: [],
              coverage: 'NO_POLICY_MAPPING',
              risk_tags: [],
            }),
    );
    renderApp('/impact/CHANGE-INTENT-CONSENT');
    expect(await screen.findByText('No approved policy mapping')).toBeInTheDocument();
    expect(screen.getByText('proposed')).toBeInTheDocument();
    expect(screen.queryByText('baseline approved')).not.toBeInTheDocument();
    expect(screen.getByText(/Zero downstream controls means a coverage gap/)).toBeInTheDocument();
  });

  it('resets the current session and refetches the dashboard', async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByRole('heading', { name: 'Review only what changed.' });
    await user.click(screen.getByRole('button', { name: 'Reset demo' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Your local scenario decisions have been reset.',
    );
    expect(
      vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith('/dashboard')).length,
    ).toBeGreaterThan(1);
  });

  it('renders recoverable API errors without stack traces', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('sensitive internal trace'));
    renderApp();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The local API is unreachable. Start the backend and try again.',
    );
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
    expect(screen.queryByText('sensitive internal trace')).not.toBeInTheDocument();
  });

  it('reuses a session UUID and preserves typed backend errors', async () => {
    expect(sessionId()).toBe(sessionId());
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { code: 'ROLE_FORBIDDEN', message: 'Policy Owner required.' },
          meta: { request_id: 'req-123' },
        }),
        { status: 403 },
      ),
    );
    await expect(request('/assessments/x/review', {})).rejects.toMatchObject({
      code: 'ROLE_FORBIDDEN',
      message: 'Policy Owner required.',
      requestId: 'req-123',
    });
  });
});
