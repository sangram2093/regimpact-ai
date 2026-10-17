import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from './render';
import { dashboard } from './fixtures';
import {
  askConfig,
  askResponse,
  changeDetail,
  localRun,
  mandate,
  policyCandidates,
  sourceRecords,
} from './extended-fixtures';

const success = (data: unknown) =>
  new Response(JSON.stringify({ data, meta: { request_id: 'extended-test', mode: 'local' } }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

describe('Source, interpretation and grounded Ask workflows', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string) => {
        if (input.endsWith('/dashboard')) return success(dashboard);
        if (input.endsWith('/impact-assessments'))
          return success({ assessments: [], required_role: 'Policy Owner' });
        if (input.endsWith('/sources')) return success(sourceRecords);
        if (input.endsWith('/changes/CHANGE-GIFT')) return success(changeDetail);
        if (input.endsWith('/classify')) return success(changeDetail);
        if (input.endsWith('/mandates')) return success({ mandates: [mandate] });
        if (input.endsWith('/policy-candidates')) return success(policyCandidates);
        if (input.endsWith('/policy-mapping'))
          return success({ ...policyCandidates, review_status: 'SCENARIO_APPROVED' });
        if (input.endsWith('/ask/config')) return success(askConfig);
        if (input.endsWith('/ask')) return success(askResponse);
        if (input.endsWith('/workflows/runs')) return success({ runs: [] });
        if (input.includes('/workflows/runs/'))
          return success({
            run: localRun,
            output: { mandate_id: 'M-GIFT', proposal: true },
            status: 'SUCCEEDED',
            validation_errors: [],
          });
        if (input.endsWith('/run'))
          return success({
            ...localRun,
            status: 'NOT_CONFIGURED',
            validation_status: 'NOT_RUN',
            label: 'Cloud model is not configured.',
          });
        return new Response('{}', { status: 404 });
      }),
    );
  });

  it('shows unavailable source hashes honestly and disables ingestion until an artifact exists', async () => {
    renderApp('/sources');
    expect(
      await screen.findByRole('heading', { name: 'Public MAS baseline guidelines' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Unavailable — no verified downloaded artifact')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ingest downloaded document' })).toBeDisabled();
    expect(screen.getByRole('link', { name: 'Open official source' })).toHaveAttribute(
      'href',
      'https://www.mas.gov.sg/',
    );
  });

  it('ingests only a known source ID and refreshes its register', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      if (String(input).endsWith('/sources'))
        return success({
          ...sourceRecords,
          sources: [
            { ...sourceRecords.sources[0], can_ingest: true, ingestion_status: 'DOWNLOADED' },
          ],
        });
      if (String(input).endsWith('/ingest'))
        return success({
          ...sourceRecords.sources[0],
          ingestion_status: 'INGESTED',
          segment_count: 3,
          sha256: 'a'.repeat(64),
        });
      return handler(input, init);
    });
    const user = userEvent.setup();
    renderApp('/sources');
    await user.click(await screen.findByRole('button', { name: 'Ingest downloaded document' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Source ingestion finished.');
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith('/sources/MAS-2016/ingest'));
    expect(call?.[1]?.body).toBe('{}');
  });

  it('requires rationale and evidence acknowledgement before recording classification', async () => {
    const user = userEvent.setup();
    renderApp('/changes/CHANGE-GIFT');
    const confirm = await screen.findByRole('button', { name: 'Confirm change effect' });
    expect(confirm).toBeDisabled();
    await user.type(
      screen.getByLabelText('Specialist rationale'),
      'Scope and proposed legal force both change this safeguard.',
    );
    expect(confirm).toBeDisabled();
    await user.click(
      screen.getByLabelText('I reviewed the baseline and proposal evidence displayed above.'),
    );
    await user.click(confirm);
    expect(await screen.findByRole('status')).toHaveTextContent('Specialist judgment recorded');
    const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/classify'));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      role: 'Regulatory Specialist',
      classification: 'MODIFIED',
      evidence_ids: ['EV-BASE', 'EV-PROPOSAL'],
    });
  });

  it('keeps unsafe unchanged confirmation blocked when backend safeguards reject it', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).endsWith('/classify')
        ? new Response(
            JSON.stringify({
              error: {
                code: 'UNSAFE_CARRY_FORWARD',
                message: 'Global legal-force changes prevent unchanged confirmation.',
              },
              meta: { request_id: 'safety-check' },
            }),
            { status: 409 },
          )
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/changes/CHANGE-GIFT');
    await screen.findByRole('button', { name: 'Confirm change effect' });
    await user.selectOptions(screen.getByLabelText('Classification'), 'UNCHANGED');
    await user.type(
      screen.getByLabelText('Specialist rationale'),
      'Unchanged based on the selected evidence.',
    );
    await user.click(
      screen.getByLabelText('I reviewed the baseline and proposal evidence displayed above.'),
    );
    await user.click(screen.getByRole('button', { name: 'Confirm change effect' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Global legal-force changes prevent unchanged confirmation.',
    );
    expect(screen.queryByText(/Specialist judgment recorded/)).not.toBeInTheDocument();
  });

  it('shows recorded classification as read-only with specialist rationale', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).endsWith('/changes/CHANGE-GIFT')
        ? success({
            ...changeDetail,
            classification_review: {
              classification: 'MODIFIED',
              reviewer: 'Demo reviewer',
              rationale: 'Confirmed scope change against both sources.',
              reviewed_at: '2026-10-17T10:00:00Z',
            },
          })
        : handler(input, init),
    );
    renderApp('/changes/CHANGE-GIFT');
    expect(
      await screen.findByRole('heading', { name: 'Change effect confirmed' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Confirmed scope change against both sources.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm change effect' })).not.toBeInTheDocument();
  });

  it('submits only a retrieved policy candidate after Policy Owner review', async () => {
    const user = userEvent.setup();
    renderApp('/mandates/M-GIFT');
    await user.click(await screen.findByRole('radio'));
    await user.type(
      screen.getByLabelText('Mapping decision rationale'),
      'The retrieved policy covers this prospective gift scope.',
    );
    expect(screen.getByRole('button', { name: 'Approve prospective mapping' })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Policy Owner');
    await user.click(screen.getByRole('button', { name: 'Approve prospective mapping' }));
    await waitFor(() =>
      expect(
        vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/policy-mapping')),
      ).toBe(true),
    );
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith('/policy-mapping'));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      policy_id: 'PR-GIFT-01',
      decision: 'APPROVE',
      role: 'Policy Owner',
    });
    expect(screen.getByText('Not run')).toBeInTheDocument();
  });

  it('fails closed for prospective mapping until classification prerequisites pass', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).endsWith('/policy-candidates')
        ? success({
            ...policyCandidates,
            mapping_allowed: false,
            mapping_block_reason: 'Specialist change effect confirmation is required.',
          })
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/mandates/M-GIFT');
    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Policy Owner');
    await user.click(await screen.findByRole('radio'));
    await user.type(
      screen.getByLabelText('Mapping decision rationale'),
      'Suitable candidate after specialist review.',
    );
    expect(screen.getByRole('button', { name: 'Approve prospective mapping' })).toBeDisabled();
    expect(
      screen.getByText('Specialist change effect confirmation is required.'),
    ).toBeInTheDocument();
  });

  it('uses the preloaded graph question and exposes run-specific verified citations', async () => {
    const user = userEvent.setup();
    renderApp('/ask');
    expect(await screen.findByLabelText('Question for RegImpact')).toHaveValue(
      askConfig.suggested_questions[0],
    );
    await user.click(screen.getByRole('button', { name: 'Ask RegImpact' }));
    expect(await screen.findByText('Grounded · 2 / 2 references verified')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '[M-GIFT]' })).toHaveAttribute('href', '#cite-M-GIFT');
    expect(screen.getByText('get_change_impact')).toBeInTheDocument();
    expect(screen.getByText('No model call')).toBeInTheDocument();
  });

  it('withholds ungrounded answer content and citations instead of presenting it as trustworthy', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).endsWith('/ask')
        ? success({
            ...askResponse,
            answer: 'Unsupported claim must not appear.',
            grounded: false,
            verified_references: 0,
          })
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/ask');
    await user.click(await screen.findByRole('button', { name: 'Ask RegImpact' }));
    expect(
      await screen.findByText("I couldn't ground a complete answer in approved graph data."),
    ).toBeInTheDocument();
    expect(screen.queryByText('Unsupported claim must not appear.')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '[M-GIFT]' })).not.toBeInTheDocument();
  });

  it('shows unconfigured workflow status without an accepted model result', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).includes('/workflows/runs/')
        ? success({
            run: localRun,
            output: null,
            status: 'NOT_CONFIGURED',
            validation_errors: ['A project and live model must be configured.'],
          })
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/runs');
    await screen.findByText('No workflow runs yet');
    await user.click(screen.getByRole('button', { name: 'Run workflow' }));
    expect(await screen.findByText('not configured')).toBeInTheDocument();
    expect(screen.getByText('No model call')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Inspect structured output' }));
    expect(
      await screen.findByText('No accepted structured output is available for this run.'),
    ).toBeInTheDocument();
    expect(screen.getByText('A project and live model must be configured.')).toBeInTheDocument();
    expect(screen.getByText(/Generated objects are recommendations only/)).toBeInTheDocument();
  });

  it('opens successful structured workflow output as a read-only recommendation', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).endsWith('/workflows/runs')
        ? success({ runs: [localRun] })
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/runs');
    await user.click(await screen.findByRole('button', { name: 'Inspect structured output' }));
    expect(await screen.findByLabelText('Structured workflow output')).toHaveTextContent('M-GIFT');
    expect(screen.getByText('Read-only workflow result')).toBeInTheDocument();
  });

  it('keeps scenario mappings opt-in and still exposes missing control coverage', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    const baseline = {
      nodes: [{ id: 'M-CONSENT', label: 'Consent safeguard', type: 'MANDATE', status: 'PROPOSED' }],
      edges: [],
      controls: [],
      coverage: 'NO_POLICY_MAPPING',
      risk_tags: [],
    };
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      if (String(input).endsWith('/impact')) return success(baseline);
      if (String(input).endsWith('/impact?include_scenario=true'))
        return success({
          ...baseline,
          nodes: [
            ...baseline.nodes,
            {
              id: 'PR-CONSENT',
              label: 'Synthetic consent policy',
              type: 'POLICY_REQUIREMENT',
              status: 'SCENARIO_APPROVED',
            },
          ],
          edges: [
            {
              id: 'SCENARIO-EDGE',
              source: 'M-CONSENT',
              target: 'PR-CONSENT',
              label: 'ADDRESSED_BY',
              status: 'SCENARIO_APPROVED',
            },
          ],
          coverage: 'PARTIAL',
        });
      return handler(input, init);
    });
    const user = userEvent.setup();
    renderApp('/impact/CHANGE-INTENT-CONSENT');
    expect(await screen.findByText('No approved policy mapping')).toBeInTheDocument();
    expect(screen.getByLabelText('Approved baseline relationships only')).toBeChecked();
    await user.click(screen.getByLabelText('Approved baseline relationships only'));
    expect(await screen.findByText('Partial control coverage')).toBeInTheDocument();
    expect(screen.getByText('· Scenario approved')).toBeInTheDocument();
    expect(
      screen.getByText('No approved downstream controls are connected to this path.'),
    ).toBeInTheDocument();
    await user.click(screen.getByLabelText('Approved baseline relationships only'));
    expect(await screen.findByText('No approved policy mapping')).toBeInTheDocument();
    expect(screen.queryByText('Synthetic consent policy')).not.toBeInTheDocument();
  });
});
