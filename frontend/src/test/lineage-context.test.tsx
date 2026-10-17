import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from './render';
import { dashboard, impact } from './fixtures';
import { changeDetail } from './extended-fixtures';
import type { Impact } from '../types/api';

const success = (data: unknown) =>
  new Response(JSON.stringify({ data, meta: { request_id: 'lineage-test' } }), { status: 200 });
// A bounded test graph includes a returned policy without a downstream control.
const graph: Impact = {
  ...impact,
  nodes: [
    ...impact.nodes,
    {
      id: 'PR-RECORD',
      label: 'Gift record policy',
      type: 'POLICY_REQUIREMENT',
      status: 'APPROVED',
    },
    { id: 'CO-RECORD', label: 'Gift record review', type: 'CONTROL_OBJECTIVE', status: 'APPROVED' },
    {
      id: 'PR-PARTIAL',
      label: 'Policy with missing control coverage',
      type: 'POLICY_REQUIREMENT',
      status: 'APPROVED',
    },
  ],
  edges: [
    ...impact.edges,
    {
      id: 'E-GIFT-CONTROL',
      source: 'PR-GIFT-01',
      target: 'CO-GIFT-01',
      label: 'IMPLEMENTED_BY',
      status: 'APPROVED',
    },
    {
      id: 'E-RECORD',
      source: 'M-GIFT',
      target: 'PR-RECORD',
      label: 'ADDRESSED_BY',
      status: 'APPROVED',
    },
    {
      id: 'E-RECORD-CONTROL',
      source: 'PR-RECORD',
      target: 'CO-RECORD',
      label: 'IMPLEMENTED_BY',
      status: 'APPROVED',
    },
    {
      id: 'E-PARTIAL',
      source: 'M-GIFT',
      target: 'PR-PARTIAL',
      label: 'ADDRESSED_BY',
      status: 'APPROVED',
    },
  ],
  controls: [
    ...impact.controls,
    { id: 'CO-RECORD', title: 'Gift record review', impact_type: 'PROSPECTIVE_REVIEW' },
  ],
  coverage: 'PARTIAL',
};
const detail = {
  ...changeDetail,
  proposal_evidence: [
    {
      ...changeDetail.proposal_evidence[0],
      source_id: 'MAS-2023',
      title: 'MAS consultation proposal',
      paragraph_ref: 'Paragraph 3.2',
      page: 4,
      text: 'Proposal paraphrase for the selected safeguard.',
    },
  ],
};

describe('Focused lineage context and view controls', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string) => {
        if (input.endsWith('/dashboard')) return success(dashboard);
        if (input.endsWith('/impact')) return success(graph);
        if (input.endsWith('/impact-assessments'))
          return success({ assessments: [], required_role: 'Policy Owner' });
        if (input.endsWith('/changes/CHANGE-GIFT')) return success(detail);
        return new Response('{}', { status: 404 });
      }),
    );
  });

  it('expands actual source locators and labelled evidence without adding graph relationships', async () => {
    const user = userEvent.setup();
    renderApp('/impact/CHANGE-GIFT');
    const expand = await screen.findByRole('button', {
      name: /Expand source and provision context/,
    });
    expect(expand).toHaveAttribute('aria-expanded', 'false');
    expect(
      vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/changes/CHANGE-GIFT')),
    ).toBe(false);
    expect(screen.getAllByRole('button', { name: /^Explain edge/ })).toHaveLength(5);
    await user.click(expand);
    const baseline = await screen.findByRole('region', { name: 'Baseline source / provision' });
    const proposal = screen.getByRole('region', { name: 'Proposal source / provision' });
    expect(within(baseline).getByText('MAS-2016')).toBeInTheDocument();
    expect(within(proposal).getByText('MAS-2023')).toBeInTheDocument();
    expect(within(proposal).getByText('Paragraph 3.2 · Page 4')).toBeInTheDocument();
    expect(within(proposal).getByText('Paraphrase')).toBeInTheDocument();
    expect(within(proposal).getByRole('link', { name: 'Public MAS source' })).toHaveAttribute(
      'href',
      'https://www.mas.gov.sg/',
    );
    expect(screen.getByText(/not additional approved graph relationships/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^Explain edge/ })).toHaveLength(5);
    await user.click(screen.getByRole('button', { name: /Collapse source and provision context/ }));
    expect(
      screen.queryByRole('region', { name: 'Proposal source / provision' }),
    ).not.toBeInTheDocument();
  });

  it('filters only returned impacted paths and retains authoritative partial coverage and review totals', async () => {
    const user = userEvent.setup();
    renderApp('/impact/CHANGE-GIFT');
    await user.click(await screen.findByLabelText('Impacted controls only'));
    expect(screen.queryByText('Policy with missing control coverage')).not.toBeInTheDocument();
    expect(screen.getByText(/Showing 4 of 5 returned relationships/)).toBeInTheDocument();
    expect(screen.getByText('Partial control coverage')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Controls to review if adopted' }),
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Focus an impacted control'), 'CO-RECORD');
    expect(screen.getByText(/Showing 2 of 5 returned relationships/)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Explain edge M-GIFT to PR-RECORD' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Explain edge PR-RECORD to CO-RECORD' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Explain edge M-GIFT to PR-GIFT-01' }),
    ).not.toBeInTheDocument();
    // The separate authoritative review list still contains both controls.
    expect(screen.getByText('Gift offer review')).toBeInTheDocument();
    await user.click(screen.getByLabelText('Impacted controls only'));
    expect(screen.getByText('Policy with missing control coverage')).toBeInTheDocument();
    expect(screen.getByText(/Showing 5 of 5 returned relationships/)).toBeInTheDocument();
  });

  it('does not turn an empty control path into a claim of no impact', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).endsWith('/impact')
        ? success({
            ...graph,
            nodes: [graph.nodes[0]],
            edges: [],
            controls: [],
            coverage: 'NO_POLICY_MAPPING',
          })
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/impact/CHANGE-GIFT');
    await user.click(await screen.findByLabelText('Impacted controls only'));
    expect(screen.getByText('Gift safeguard')).toBeInTheDocument();
    expect(screen.getByText(/No connected control impact path is available/)).toBeInTheDocument();
    expect(screen.getByText('No approved policy mapping')).toBeInTheDocument();
    expect(screen.getByText(/Zero downstream controls means a coverage gap/)).toBeInTheDocument();
  });

  it('keeps lineage usable when source expansion fails and supports a scoped retry', async () => {
    const handler = vi.mocked(fetch).getMockImplementation()!;
    let available = false;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      String(input).endsWith('/changes/CHANGE-GIFT') && !available
        ? new Response(
            JSON.stringify({ error: { message: 'Source context temporarily unavailable.' } }),
            { status: 503 },
          )
        : handler(input, init),
    );
    const user = userEvent.setup();
    renderApp('/impact/CHANGE-GIFT');
    await user.click(
      await screen.findByRole('button', { name: /Expand source and provision context/ }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Source context temporarily unavailable.',
    );
    expect(screen.getAllByRole('button', { name: /^Explain edge/ })).toHaveLength(5);
    available = true;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(
      await screen.findByRole('region', { name: 'Proposal source / provision' }),
    ).toBeInTheDocument();
  });
});
