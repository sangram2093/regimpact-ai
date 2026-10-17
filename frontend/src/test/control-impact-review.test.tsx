import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from './render';
import { dashboard, impact } from './fixtures';
import type { ControlImpactAssessment } from '../types/workflows';

const assessment: ControlImpactAssessment = {
  id: 'IA-GIFT-01',
  change_id: 'CHANGE-GIFT',
  control_id: 'CO-GIFT-01',
  title: 'Gift offer review',
  status: 'PENDING_REVIEW',
  impact_type: 'PROSPECTIVE_REVIEW',
  scope_note: 'Assess gift review scope if the proposed telemarketing safeguards are adopted.',
  review: null,
};
const success = (data: unknown) =>
  new Response(JSON.stringify({ data, meta: { request_id: 'impact-review-test' } }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

describe('Gate 6 prospective control impact review', () => {
  beforeEach(() => {
    let current = assessment;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string, init?: RequestInit) => {
        if (input.endsWith('/dashboard')) return success(dashboard);
        if (input.endsWith('/impact')) return success(impact);
        if (input.endsWith('/impact-assessments'))
          return success({ assessments: [current], required_role: 'Policy Owner' });
        if (input.endsWith('/review') && init?.method === 'POST') {
          const body = JSON.parse(String(init.body));
          current = {
            ...current,
            status:
              body.decision === 'APPROVE'
                ? 'APPROVED'
                : body.decision === 'REJECT'
                  ? 'REJECTED'
                  : 'MODIFIED',
            scope_note: body.scope_note ?? assessment.scope_note,
            review: {
              ...body,
              reviewed_at: '2026-10-17T11:00:00Z',
              previous_output: { scope_note: assessment.scope_note },
              final_output:
                body.decision === 'REJECT'
                  ? null
                  : { scope_note: body.scope_note ?? assessment.scope_note },
            },
          };
          return success(current);
        }
        return new Response('{}', { status: 404 });
      }),
    );
  });

  it('requires the demo Policy Owner and records a separate prospective impact approval', async () => {
    const user = userEvent.setup();
    renderApp('/impact/CHANGE-GIFT');
    await user.click(await screen.findByRole('button', { name: 'Review control impact' }));
    let dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Confirm control impact' })).toBeDisabled();
    expect(within(dialog).getByText(/does not edit the control objective/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Close dialog' }));
    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Policy Owner');
    await user.click(screen.getByRole('button', { name: 'Review control impact' }));
    dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Confirm control impact' })).toBeDisabled();
    await user.type(
      within(dialog).getByLabelText('Control impact rationale'),
      'Review scope is appropriate if the proposal is adopted.',
    );
    await user.click(within(dialog).getByRole('button', { name: 'Confirm control impact' }));
    expect(
      await screen.findByRole('dialog', { name: 'Recorded control impact review' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Confirm control impact' }),
    ).not.toBeInTheDocument();
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith('/impact-assessments/IA-GIFT-01/review'));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      decision: 'APPROVE',
      role: 'Policy Owner',
    });
    expect(JSON.parse(String(call?.[1]?.body))).not.toHaveProperty('scope_note');
    await user.click(screen.getByRole('button', { name: 'Close dialog' }));
    expect(await screen.findByRole('button', { name: 'View impact decision' })).toBeInTheDocument();
  });

  it('records revised assessment scope without sending a control catalog mutation', async () => {
    const user = userEvent.setup();
    renderApp('/impact/CHANGE-GIFT');
    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Policy Owner');
    await user.click(await screen.findByRole('button', { name: 'Review control impact' }));
    await user.selectOptions(screen.getByLabelText('Control impact decision'), 'MODIFY');
    await user.type(
      screen.getByLabelText('Control impact rationale'),
      'Narrowed this prospective assessment to telemarketing gift approvals.',
    );
    expect(screen.getByRole('button', { name: 'Save reviewed impact scope' })).toBeDisabled();
    await user.clear(screen.getByLabelText('Reviewed impact scope'));
    await user.type(
      screen.getByLabelText('Reviewed impact scope'),
      'Review gift approval checkpoints specifically for telemarketing.',
    );
    await user.click(screen.getByRole('button', { name: 'Save reviewed impact scope' }));
    expect(
      await screen.findByRole('dialog', { name: 'Recorded control impact review' }),
    ).toBeInTheDocument();
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith('/impact-assessments/IA-GIFT-01/review'));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      decision: 'MODIFY',
      scope_note: 'Review gift approval checkpoints specifically for telemarketing.',
    });
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(
          ([url, init]) => String(url).includes('/controls/') && init?.method === 'POST',
        ),
    ).toBe(false);
  });

  it('records rejected prospective impact as an immutable decision', async () => {
    const user = userEvent.setup();
    renderApp('/impact/CHANGE-GIFT');
    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Policy Owner');
    await user.click(await screen.findByRole('button', { name: 'Review control impact' }));
    await user.selectOptions(screen.getByLabelText('Control impact decision'), 'REJECT');
    await user.type(
      screen.getByLabelText('Control impact rationale'),
      'The proposed control impact is not supported by the reviewed scope.',
    );
    await user.click(screen.getByRole('button', { name: 'Reject control impact' }));
    expect(
      await screen.findByRole('dialog', { name: 'Recorded control impact review' }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole('dialog')).getByRole('heading', { name: 'rejected' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reject control impact' })).not.toBeInTheDocument();
  });
});
