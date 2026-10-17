import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from './render';
import { dashboard } from './fixtures';
import { localRun } from './extended-fixtures';
import type { WorkflowResult } from '../types/workflows';

const output = {
  classification: 'MODIFIED',
  no_effect_result: 'EFFECT_POSSIBLE',
  reason: 'The proposed scope requires a fresh interpretation.',
  evidence: [
    {
      source_id: 'SYNTHETIC-SOURCE',
      segment_id: 'SYNTHETIC-SEGMENT',
      excerpt: 'Synthetic workflow test only.',
    },
  ],
};
const run = {
  ...localRun,
  id: 'RUN-LIVE-TEST',
  workflow: 'change-effect',
  kind: 'LIVE_AI' as const,
  model: 'test-model',
  label: 'Synthetic network fixture for a validated live run',
};
const result: WorkflowResult = {
  run,
  output,
  status: 'HUMAN_REVIEW_REQUIRED',
  validation_errors: [],
  required_role: 'Regulatory Specialist',
  review_allowed: true,
  block_reason: null,
  review: null,
};
const success = (data: unknown) =>
  new Response(JSON.stringify({ data, meta: { request_id: 'human-review-test' } }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

describe('Human review of accepted workflow output', () => {
  beforeEach(() => {
    let current = result;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string, init?: RequestInit) => {
        if (input.endsWith('/dashboard')) return success(dashboard);
        if (input.endsWith('/workflows/runs')) return success({ runs: [current.run] });
        if (input.endsWith('/review') && init?.method === 'POST') {
          const body = JSON.parse(String(init.body));
          current = {
            ...current,
            review_allowed: false,
            review: {
              ...body,
              reviewed_at: '2026-10-17T10:30:00Z',
              previous_output: output,
              final_output: body.decision === 'REJECT' ? null : (body.final_output ?? output),
            },
          };
          return success(current);
        }
        if (input.includes('/workflows/runs/')) return success(current);
        return new Response('{}', { status: 404 });
      }),
    );
  });

  it('requires rationale and correct role then records an immutable approval', async () => {
    const user = userEvent.setup();
    renderApp('/runs');
    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Policy Owner');
    await user.click(await screen.findByRole('button', { name: 'Inspect structured output' }));
    await screen.findByRole('button', { name: 'Approve workflow output' });
    await user.type(
      screen.getByLabelText('Workflow decision rationale'),
      'Source evidence supports the proposed scope interpretation.',
    );
    expect(screen.getByRole('button', { name: 'Approve workflow output' })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Regulatory Specialist');
    await user.click(screen.getByRole('button', { name: 'Approve workflow output' }));
    expect(await screen.findByText('Recorded specialist decision')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Approve workflow output' }),
    ).not.toBeInTheDocument();
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith('/RUN-LIVE-TEST/review'));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      decision: 'APPROVE',
      role: 'Regulatory Specialist',
    });
    expect(JSON.parse(String(call?.[1]?.body))).not.toHaveProperty('final_output');
  });

  it('validates edited JSON and preserves both original and modified output', async () => {
    const user = userEvent.setup();
    renderApp('/runs');
    await user.click(await screen.findByRole('button', { name: 'Inspect structured output' }));
    await user.selectOptions(await screen.findByLabelText('Workflow review decision'), 'MODIFY');
    await user.type(
      screen.getByLabelText('Workflow decision rationale'),
      'Clarified scope after specialist evidence review.',
    );
    expect(screen.getByRole('button', { name: 'Save reviewed changes' })).toBeDisabled();
    await user.clear(screen.getByLabelText('Reviewed structured output'));
    await user.type(screen.getByLabelText('Reviewed structured output'), 'invalid JSON');
    expect(screen.getByRole('button', { name: 'Save reviewed changes' })).toBeDisabled();
    const modified = {
      ...output,
      reason: 'The revised explanation explicitly separates proposed scope from current guidance.',
    };
    await user.clear(screen.getByLabelText('Reviewed structured output'));
    await user.click(screen.getByLabelText('Reviewed structured output'));
    await user.paste(JSON.stringify(modified));
    await user.click(screen.getByRole('button', { name: 'Save reviewed changes' }));
    expect(await screen.findByText('Recorded specialist decision')).toBeInTheDocument();
    await user.click(screen.getByText('Compare original and reviewed output'));
    expect(screen.getByLabelText('Original workflow output')).toHaveTextContent(output.reason);
    expect(screen.getByLabelText('Final reviewed workflow output')).toHaveTextContent(
      modified.reason,
    );
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith('/RUN-LIVE-TEST/review'));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      decision: 'MODIFY',
      final_output: modified,
    });
  });

  it('rejects without accepting a final object', async () => {
    const user = userEvent.setup();
    renderApp('/runs');
    await user.click(await screen.findByRole('button', { name: 'Inspect structured output' }));
    await user.selectOptions(await screen.findByLabelText('Workflow review decision'), 'REJECT');
    await user.type(
      screen.getByLabelText('Workflow decision rationale'),
      'The explanation does not establish the claimed applicability.',
    );
    await user.click(screen.getByRole('button', { name: 'Reject workflow output' }));
    expect(await screen.findByText('Recorded specialist decision')).toBeInTheDocument();
    await user.click(screen.getByText('Compare original and reviewed output'));
    expect(screen.getByLabelText('Final reviewed workflow output')).toHaveTextContent(
      'Rejected — no accepted final output.',
    );
  });

  it('refuses to offer approval for local or unconfigured output', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).includes('/workflows/runs/')
        ? success({
            ...result,
            run: {
              ...run,
              kind: 'LOCAL_DETERMINISTIC',
              status: 'BLOCKED',
              validation_status: 'NOT_RUN',
            },
            output: null,
            status: 'AI_NOT_CONFIGURED',
            review_allowed: false,
            block_reason: 'A live AI result is required.',
          })
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/runs');
    await user.click(await screen.findByRole('button', { name: 'Inspect structured output' }));
    expect(await screen.findByText('A live AI result is required.')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Approve workflow output' }),
    ).not.toBeInTheDocument();
  });

  it('shows server evidence validation errors without recording the modification', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).endsWith('/review')
        ? new Response(
            JSON.stringify({
              error: {
                code: 'OUTPUT_VALIDATION_FAILED',
                message: 'The modified output contains an unsupported evidence ID.',
              },
              meta: { request_id: 'validation-test' },
            }),
            { status: 422 },
          )
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/runs');
    await user.click(await screen.findByRole('button', { name: 'Inspect structured output' }));
    await user.selectOptions(await screen.findByLabelText('Workflow review decision'), 'MODIFY');
    await user.clear(screen.getByLabelText('Reviewed structured output'));
    await user.click(screen.getByLabelText('Reviewed structured output'));
    await user.paste(JSON.stringify({ ...output, evidence: [{ source_id: 'UNKNOWN' }] }));
    await user.type(
      screen.getByLabelText('Workflow decision rationale'),
      'Changed source reference for validation test.',
    );
    await user.click(screen.getByRole('button', { name: 'Save reviewed changes' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('unsupported evidence ID');
    await waitFor(() =>
      expect(screen.queryByText('Recorded specialist decision')).not.toBeInTheDocument(),
    );
  });
});
